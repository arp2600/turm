import turm.escape_codes as escape_codes

class Term:

    def __init__(self, istream, ostream):
        self._istream = istream
        self._ostream = ostream
        self._init_screen_dimensions()
        self._lines = [[' ' for _ in range(self.screen_width)] for _ in range(self.screen_height)]

    def _init_screen_dimensions(self):
        # save the current position
        self._update_cursor_position()
        saved_position = (self.row, self.column)

        # Move the cursor far left and down, it will only
        # move as far as the screen dimensions allow.
        self.move_cursor_to(9999, 9999)

        self._update_cursor_position()
        self.screen_height = self.row
        self.screen_width = self.column

        # restore the cursor position
        self.move_cursor_to(*saved_position)

    def _update_cursor_position(self):
        self._ostream.write(escape_codes.request_cursor_position())
        self._ostream.flush()
        chars = self._istream.read(2)
        assert chars == '\x1b['
        while True:
            chars += self._istream.read(1)
            code = escape_codes.parse_escape_code(chars)
            if code is not None:
                assert isinstance(code, escape_codes.ReportedCursorPosition)
                self.row = code.row
                self.column = code.column
                return

    def write(self, chars):
        for char in chars:
            self._lines[self.row - 1][self.column - 1] = char
            if char == '\n':
                self.column = 0
                self.row += 1
            else:
                self.column += 1

        self._ostream.write(chars)

    def flush(self):
        self._ostream.flush()

    def move_cursor_left(self, amount=1):
        assert amount > 0
        assert amount <= self.column
        self._ostream.write(escape_codes.move_cursor_left(amount))
        self.column -= amount

    def move_cursor_right(self, amount=1):
        assert amount > 0
        self._ostream.write(
            escape_codes.move_cursor_right(amount, self._ostream))
        self.column += amount

    def move_cursor_up(self, amount=1):
        assert amount > 0
        assert amount <= self.row
        self._ostream.write(escape_codes.move_cursor_up(amount, self._ostream))
        self.row -= amount

    def move_cursor_down(self, amount=1):
        assert amount > 0
        self._ostream.write(
            escape_codes.move_cursor_down(amount, self._ostream))
        self.row += amount

    def move_to_column(self, column):
        assert column >= 0
        self._ostream.write(escape_codes.move_cursor_to_column(column))

    def erase_line(self):
        self._ostream.write(escape_codes.erase_line())

    def move_cursor_to(self, row=None, column=None):
        if row is not None:
            self.row = row
        if column is not None:
            self.column = column
        self._ostream.write(escape_codes.move_cursor_to(self.row, self.column))

    def __str__(self):
        return ''.join([''.join(line) for line in self._lines])
