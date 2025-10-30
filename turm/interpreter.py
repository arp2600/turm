import sys
import os
import tty
import termios
import traceback
from codeop import CommandCompiler
import turm.escape_codes as escape_codes
from turm.chars import Chars
from turm.edit_field import EditField


class Interpreter:

    def __init__(self, locals=None):
        # Adding '' to sys.path allows us to import local modules.
        sys.path.insert(0, '')

        self._setup_tty()

        # Enable bracketed paste
        sys.stdout.write(escape_codes.enable_bracketed_paste())
        sys.stdout.flush()
        self._bracketed_paste = False

        if locals is None:
            locals = {}
        if 'exit' not in locals:
            # Override exit so we can do any shut down we need to after the interpreter has closed.
            def raise_system_exit(x=1):
                raise SystemExit(x)

            locals['exit'] = raise_system_exit
        self._locals = locals

        self._chars = ''
        self._reset_input_buffer()

        self._compile = CommandCompiler()

        self._run_generator = self._run()

    def _setup_tty(self):
        # Set cbreak and save the previous tty attributes to reset the program after exit.
        self._tty_attrs = tty.setcbreak(sys.stdin.fileno())

        # Disabling ISIG allows us to handle ctrl-c.
        tty_attrs = termios.tcgetattr(sys.stdin.fileno())
        tty_attrs[3] &= ~termios.ISIG
        tty_attrs = termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW,
                                      tty_attrs)

    def _reset_input_buffer(self):
        self._editor = EditField()

    def _handle_escape_code(self, code):
        match code:
            case escape_codes.MoveCursorLeft():
                self._editor.move_cursor_left(code.amount)
            case escape_codes.MoveCursorRight():
                self._editor.move_cursor_right(code.amount)
            case escape_codes.MoveCursorUp():
                self._editor.move_cursor_up(code.amount)
            case escape_codes.MoveCursorDown():
                self._editor.move_cursor_down(code.amount)
            case escape_codes.BracketedPasteStart():
                self._bracketed_paste = True
            case escape_codes.BracketedPasteEnd():
                self._bracketed_paste = False
            case _:
                raise Exception()

    def _handle_escape_sequence(self):
        sequence = '\x1b'
        while True:
            char = yield from self._get_char()
            sequence += char
            code = escape_codes.parse_escape_code(sequence)
            if code is not None:
                self._handle_escape_code(code)
                return

    def _get_char(self):
        while not self._chars:
            # Read from stdin without blocking
            os.set_blocking(sys.stdin.fileno(), False)
            self._chars = sys.stdin.read(100)
            os.set_blocking(sys.stdin.fileno(), True)

            if self._chars:
                break
            else:
                sys.stdout.flush()
                yield

        x = self._chars[0]
        self._chars = self._chars[1:]
        return x

    def _handle_ctrl_c(self):
        sys.stdout.write('\nKeyboardInterrupt\n')
        self._reset_input_buffer()

    def _handle_newline(self):
        if self._bracketed_paste:
            self._editor.newline()
        else:
            self._try_run_source()

    def _run(self):
        while True:
            char = yield from self._get_char()

            match char:
                case Chars.ESCAPE:
                    yield from self._handle_escape_sequence()
                case Chars.CTRL_C:
                    self._handle_ctrl_c()
                case Chars.BACKSPACE:
                    self._editor.backspace()
                case Chars.TAB:
                    for _ in range(4):
                        self._editor.insert(' ')
                case Chars.NEWLINE:
                    self._handle_newline()
                case _:
                    self._editor.insert(char)

    def _reset_term(self):
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSAFLUSH,
                          self._tty_attrs)

    def _try_run_source(self):
        source = str(self._editor)
        lines = source.splitlines()

        if len(lines) > 1 and not source.endswith('\n'):
            self._editor.newline()
            return

        try:
            symbol = 'single'
            if source.find('\n') != len(source) - 1:
                symbol = 'exec'

            code = self._compile(source, symbol=symbol)
            if code is None:
                self._editor.newline()
                return
        except (OverflowError, SyntaxError, ValueError) as e:
            self._showtraceback(e, None, source)
            self._reset_input_buffer()
            return

        sys.stdout.write('\n')
        try:
            exec(code, self._locals)
        except SystemExit as e:
            self._reset_term()
            raise e
        except Exception as e:
            self._showtraceback(e, e.__traceback__.tb_next)

        self._reset_input_buffer()

    def _showtraceback(self, e, tb, source=''):
        typ = type(e)
        sys.last_type = typ
        sys.last_traceback = tb
        e = e.with_traceback(tb)
        # Set the line of text that the exception refers to
        lines = source.splitlines()
        if (source and typ is SyntaxError and not e.text
                # if (source and typ is SyntaxError and not e.text
                and e.lineno is not None and len(lines) >= e.lineno):
            e.text = lines[e.lineno - 1]
        sys.last_exc = sys.last_value = e = e.with_traceback(tb)
        if sys.excepthook is sys.__excepthook__:
            self._excepthook(typ, e, tb)
        else:
            # If someone has set sys.excepthook, we let that take precedence
            # over self.write
            try:
                sys.excepthook(typ, e, tb)
            except SystemExit:
                raise
            except BaseException as e:
                e.__context__ = None
                e = e.with_traceback(e.__traceback__.tb_next)
                print('Error in sys.excepthook:', file=sys.stderr)
                sys.__excepthook__(type(e), e, e.__traceback__)
                print(file=sys.stderr)
                print('Original exception was:', file=sys.stderr)
                sys.__excepthook__(typ, e, tb)

    def _excepthook(self, typ, value, tb):
        lines = traceback.format_exception(typ, value, tb)
        sys.stderr.write(''.join(lines))

    def update(self):
        next(self._run_generator)


def main():
    import time

    x = Interpreter()
    while True:
        try:
            x.update()
        except SystemExit as e:
            break
        time.sleep(1 / 30)


if __name__ == '__main__':
    main()
