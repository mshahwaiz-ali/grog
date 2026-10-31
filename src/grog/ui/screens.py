"""Modal overlays: help, details, notices and quit warning (docs/02 §3, §5, §10)."""

from __future__ import annotations

from collections.abc import Sequence

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen

from grog.ui.panels import Line
from grog.ui.widgets import TextPanel

HELP: list[Line] = [
    [("GROG KEYS — no key can place, modify or close a broker order", "gold")],
    [("1 Live  2 Signals  3 Positions  4 Journal  5 Diagnostics", "primary")],
    [("Tab / Shift+Tab / arrows  move focus and table selection", "primary")],
    [("Enter  details of selected candidate or signal    Esc  close overlay", "primary")],
    [("Space  REPLAY play/pause    .  step one quote event (paused only)", "primary")],
    [("+ / -  playback pacing 50 ev/s, 500 ev/s, FAST (events per second)", "primary")],
    [("r  refresh panels from already-ingested state (no new market events)", "primary")],
    [("e / s  record your manual entry / skip on the selected READY signal (Signals)", "primary")],
    [
        (
            "p m x  record partial / modification / closure of the selected position (Positions)",
            "primary",
        )
    ],
    [("n  unlinked OFF_PLAN external trade (Journal/Positions)", "primary")],
    [
        (
            "   Every record needs Confirm; it is a LOCAL journal entry, never a broker order.",
            "muted",
        )
    ],
    [("?  this help    q  quit (recorded positions are never closed by Grog)", "primary")],
    [("Pacing never changes event order, timestamps, expiry or outcomes.", "muted")],
]


class Overlay(ModalScreen[None]):
    """Read-only overlay; Esc closes it with no side effects."""

    BINDINGS = [Binding("escape", "dismiss_overlay", "Close")]

    def __init__(self, lines: Sequence[Line], overlay_id: str) -> None:
        super().__init__(id=overlay_id)
        self.lines = list(lines)

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal"):
            panel = TextPanel(id=f"{self.id}-body")
            yield panel

    def on_mount(self) -> None:
        self.query_one(TextPanel).set_lines(
            [*self.lines, [("", "muted")], [("[Esc] Back", "muted")]]
        )

    @property
    def plain(self) -> str:
        return self.query_one(TextPanel).plain

    def action_dismiss_overlay(self) -> None:
        self.dismiss(None)


class QuitWarning(Overlay):
    """docs/02 §10 / UI-20: positions are untouched at the broker and persisted locally."""

    BINDINGS = [
        Binding("escape", "dismiss_overlay", "Stay"),
        Binding("q", "confirm_quit", "Quit"),
    ]

    def __init__(self, open_count: int) -> None:
        super().__init__(
            [
                [("QUIT GROG?", "gold")],
                [(f"{open_count} manually recorded position(s) are open.", "caution")],
                [
                    (
                        "Positions remain open at broker; Grog will not close them. "
                        "Reconcile on restart.",
                        "caution",
                    )
                ],
                [("Local records stay saved. No broker action is taken.", "muted")],
                [("[q] Quit    [Esc] Stay", "primary")],
            ],
            "quit-warning",
        )

    def action_confirm_quit(self) -> None:
        self.app.exit()
