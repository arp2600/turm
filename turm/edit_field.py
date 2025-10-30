import tty
import sys
import termios
import os
import turm.escape_codes as escape_codes
from turm.text_editor import TextEditor
from turm.terminal import Term
from dataclasses import dataclass

@dataclass
class RowColumn:
    row: int = 0
    column: int = 0


class EditField:

    def __init__(self,
                 ps1='>>> ',
                 ps2='... ',
                 istream=sys.stdin,
                 ostream=sys.stdout):
        self.ps1 = ps1
        self.ps2 = ps2
        self._prompts = [ps1]
        self._text = TextEditor()
        self._term = Term(istream, ostream)
        self._term_offset = RowColumn(row=self._term.row,
                                      column=self._term.column)

        self._term.write(self.ps1)
        self._term.flush()

    def move_cursor_left(self, amount=1):
        assert amount > 0
        self._text.move_left(amount)
        self._reset_cursor_position()
        self._redraw()

    def move_cursor_right(self, amount=1):
        assert amount > 0
        self._text.move_right(amount)
        self._reset_cursor_position()
        self._redraw()

    def move_cursor_up(self, amount=1):
        assert amount > 0
        self._text.move_up(amount)
        self._reset_cursor_position()
        self._redraw()

    def move_cursor_down(self, amount=1):
        assert amount > 0
        self._text.move_down(amount)
        self._reset_cursor_position()
        self._redraw()

    def _reset_cursor_position(self):
        row, column = self._text.get_row_and_column()
        column += len(self._prompts[row])
        self._term.move_cursor_to(row + self._term_offset.row,
                                  column + self._term_offset.column)

    def _redraw_line(self, row=None):
        if row is None:
            self._term.move_cursor_to(None, self._term_offset.column)
        else:
            self._term.move_cursor_to(row + self._term_offset.row,
                                      self._term_offset.column)

        self._term.erase_line()

        if row is None:
            row, _ = self._text.get_row_and_column()

        prompt = self._prompts[row]
        self._term.write(prompt)

        line = self._text.get_line(row)
        if line.endswith('\n'):
            line = line[:-1]

        self._term.write(line)
        self._reset_cursor_position()
        self._term.flush()

    def _clear(self):
        for i in range(len(self._prompts)):
            term_line = self._term_offset.row + i
            if term_line > self._term.screen_height:
                break
            else:
                self._term.move_cursor_to(term_line, 1)
                self._term.erase_line()
        self._reset_cursor_position()

    def _redraw(self):
        # expand the edit field `window` if there are more lines to print than the number of rows allows
        if self._term_offset.row > 1:
            num_lines = len(self._prompts)
            term_lines = self._term.screen_height - (self._term_offset.row - 1)
            if term_lines < num_lines:
                self._term_offset.row -= 1

        # adjust the row offset so that the cursor always remains in the visible area
        row, column = self._text.get_row_and_column()
        if self._term_offset.row + row > self._term.screen_height:
            self._term_offset.row = self._term.screen_height - row
        elif self._term_offset.row + row < 1:
            self._term_offset.row = 1 - row

        # draw all the lines
        for i, (prompt,
                line) in enumerate(zip(self._prompts,
                                       self._text.iter_lines())):
            term_line = self._term_offset.row + i
            # skip lines that would draw off the top of the screen
            if term_line < 1:
                continue
            # break when lines would start to be drawn below the screen
            if term_line > self._term.screen_height:
                break

            self._term.move_cursor_to(term_line, self._term_offset.column)
            self._term.erase_line()
            self._term.write(prompt)
            if line.endswith('\n'):
                line = line[:-1]
            self._term.write(line)
        self._reset_cursor_position()

    def insert(self, char):
        assert 0x20 <= ord(char) <= 0x7e
        self._text.insert(char)
        # self._redraw_line()
        self._redraw()

    def backspace(self):
        self._text.move_left(1)
        char = self._text.pop()
        if char == '\n':
            self._clear()
            row, _ = self._text.get_row_and_column()
            self._prompts.pop(row + 1)

        # self._redraw_line()
        self._redraw()

    def newline(self):
        self._text.insert('\n')
        row, _ = self._text.get_row_and_column()

        # insert a new prompt for the newline
        self._prompts.insert(row, self.ps2)

        # write out enough newlines to display the rest of the lines
        # TODO this breaks given enough lines.
        # When trying to move_up past the top of the window, nothing happens and _redraw_line draws over the last line.
        # When trying to move_down past the bottom the same thing happens. We knew that already but didn't factor in actually moving down, not adding newlines.
        # self._term.write('\n' * (len(self._prompts) - row))
        # self._term.flush()
        # # Starting from the line the newline was added to, redraw every line going down.
        # for i in range(row - 1, len(self._prompts)):
        #     self._redraw_line(i)
        # self._reset_cursor_position()
        self._redraw()

    def __str__(self):
        return str(self._text)


class Interpreter:

    def __init__(self):
        self._setup_tty()

        self._chars = ''
        self._reset_input_buffer()

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
        if isinstance(code, escape_codes.MoveCursorLeft):
            self._editor.move_cursor_left(code.amount)
        elif isinstance(code, escape_codes.MoveCursorRight):
            self._editor.move_cursor_right(code.amount)
        elif isinstance(code, escape_codes.MoveCursorUp):
            self._editor.move_cursor_up(code.amount)
        elif isinstance(code, escape_codes.MoveCursorDown):
            self._editor.move_cursor_down(code.amount)
        else:
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

    def _run(self):
        while True:
            char = yield from self._get_char()

            if char == '\x1b':
                yield from self._handle_escape_sequence()
            elif char == '\x03':  # ctrl-c
                self._handle_ctrl_c()
            elif ord(char) == 0x7f:
                self._editor.backspace()
            elif char == '\t':
                for _ in range(4):
                    self._editor.insert(' ')
            elif char == '\n':
                if str(self._editor) == 'exit':
                    print('\nExiting...')
                    self._reset_term()
                    exit(0)
                self._editor.newline()
            else:
                self._editor.insert(char)

    def _reset_term(self):
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSAFLUSH,
                          self._tty_attrs)

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
