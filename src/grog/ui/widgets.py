"""Small Textual widgets for the workstation (docs/02 §4-§8)."""

from __future__ import annotations

from collections.abc import Sequence

from rich.text import Text
from textual.markup import escape
from textual.widgets import DataTable, Static

from grog.ui.panels import Line, plain

PALETTE = {  # docs/02 §2 tokens; colour is never the only carrier of meaning
    "primary": "#E7EDF5",
    "muted": "#93A5B9",
    "gold": "bold #E6BA63",
    "buy": "bold #33C6A1",
    "sell": "bold #FF7D7D",
    "caution": "#F2BE60",
    "error": "bold #FF6666",
    "ok": "#33C6A1",
    # Chips/badges (docs/02 §2.1): filled, text always carries the meaning.
    "badge": "bold #0B111A on #E6BA63",
    "chip_ok": "bold #0B111A on #33C6A1",
    "chip_warn": "bold #0B111A on #F2BE60",
    "chip_err": "bold #FFFFFF on #A83232",
    "tab_on": "bold #0B111A on #E6BA63",
    "tab": "#93A5B9",
    "key": "bold #E6BA63",
}


def to_text(lines: Sequence[Line]) -> Text:
    out = Text(no_wrap=False, overflow="fold")
    for i, line in enumerate(lines):
        if i:
            out.append("\n")
        for segment, style in line:
            out.append(segment, style=PALETTE.get(style, ""))
    return out


class TextPanel(Static):
    """Static panel that remembers its plain text (for tests and screen snapshots).

    With the ``boxed`` class the first line becomes the panel's border title (docs/02 §2.1)
    and is not repeated in the body; :attr:`plain` still contains every line."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__("", *args, **kwargs)
        self.plain = ""
        self._key: tuple = ()

    def set_lines(self, lines: Sequence[Line]) -> None:
        key = tuple(tuple(line) for line in lines)  # styles matter too (active tab, chips)
        if key != self._key:
            self._key = key
            self.plain = plain(lines)
            if self.has_class("boxed") and lines:
                self.border_title = escape("".join(t for t, _ in lines[0]).strip())
                lines = lines[1:]
            self.update(to_text(lines))


class StateTable(DataTable):
    """DataTable whose rows are replaced in place while keeping the selected row key
    (docs/02 §2: never reset table focus/selection as quotes update)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, cursor_type="row", zebra_stripes=False, cell_padding=1, **kwargs)
        self._columns_now: tuple[str, ...] = ()
        self._rows_now: list[tuple[str, tuple[str, ...]]] = []

    @property
    def selected_key(self) -> str | None:
        if not self._rows_now or self.cursor_row is None:
            return None
        if 0 <= self.cursor_row < len(self._rows_now):
            return self._rows_now[self.cursor_row][0]
        return None

    def show(self, columns: tuple[str, ...], rows: list[tuple[str, tuple[str, ...]]]) -> None:
        if columns == self._columns_now and rows == self._rows_now:
            return
        keep = self.selected_key
        if columns != self._columns_now:
            self.clear(columns=True)
            self.add_columns(*columns)
            self._columns_now = columns
        else:
            self.clear()
        for key, cells in rows:
            self.add_row(*cells, key=key)
        self._rows_now = list(rows)
        if keep is not None:
            for i, (key, _) in enumerate(rows):
                if key == keep:
                    self.move_cursor(row=i, animate=False)
                    break
