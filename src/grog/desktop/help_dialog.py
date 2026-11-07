"""Keyboard help overlay (D04, ``?`` / F1). Lists exactly the window's shortcut table, so
the help can never drift from the real bindings. Close is focused; Esc closes."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout

from grog.desktop.theme import SPACE, Card, label

TYPING_NOTE = (
    "Shortcuts never fire while you type in a search box, filter or form field; Tab / "
    "Shift+Tab move focus and Enter/Space press the focused button. In forms, Cancel is "
    "focused first, Esc cancels a clean form and asks before discarding typed input."
)


class HelpDialog(QDialog):
    def __init__(self, bindings: Sequence[tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gold — keyboard help")
        self.setObjectName("root")
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE[4], SPACE[4], SPACE[4], SPACE[3])
        outer.addWidget(label("KEYBOARD HELP", "cardTitle"))
        card = Card("Shortcuts (window-wide, never while typing)")
        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACE[3])
        for r, (keys, what) in enumerate(bindings):
            grid.addWidget(label(keys, "mono"), r, 0)
            grid.addWidget(label(what, "body", wrap=True), r, 1)
        card.body.addLayout(grid)
        outer.addWidget(card)
        outer.addWidget(label(TYPING_NOTE, "meta", wrap=True))
        outer.addWidget(
            label(
                "Grog records local journal entries only: it never sends orders or changes a "
                "broker position.",
                "meta",
                wrap=True,
            )
        )
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.close_button = QPushButton("Close")
        self.close_button.setAutoDefault(False)
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.close_button)
        outer.addLayout(buttons)
        self.close_button.setFocus()
        self.resize(560, 560)

    def text(self) -> str:
        return "\n".join(w.text() for w in self.findChildren(type(label(""))))
