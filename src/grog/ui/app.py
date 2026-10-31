"""Textual App shell: five views, replay controls and responsive layout (docs/02).

The app only renders :class:`grog.replay.session.Snapshot` objects and forwards playback
controls to :class:`grog.replay.session.ReplaySession`. It never writes market data, never
changes engine rules, and contains no broker/order code path.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import ContentSwitcher, DataTable, Input

from grog.domain.enums import SignalState
from grog.replay.session import Playback, ReplaySession, Snapshot
from grog.ui import panels
from grog.ui.screens import HELP, Overlay, QuitWarning
from grog.ui.widgets import StateTable, TextPanel

REDRAW_HZ = 4  # docs/02 §2 ui.max_refresh_hz (view only; engine never waits on it)
TICK_S = 0.05  # playback work slice; only decides how many quotes run per slice
VIEWS = ("live", "signals", "positions", "journal", "diagnostics")
FEED_ROWS_LIVE = 8
JOURNAL_ROWS = 50  # docs/02 §11 visible buffer


@dataclass(frozen=True, slots=True)
class PositionRow:
    """Read model of a manually recorded position (written only by the M08 journal)."""

    position_id: str
    signal_id: str | None
    side: str
    qty: str
    entry: str
    state: str


class PositionsSource(Protocol):
    def open_positions(self) -> Sequence[PositionRow]: ...


class NoPositions:
    """M07 has no local journal yet: nothing is ever assumed executed."""

    def open_positions(self) -> Sequence[PositionRow]:
        return ()


class GrogApp(App[None]):
    CSS_PATH = Path(__file__).with_name("grog.tcss")
    TITLE = "GROG / GOLD WORKSTATION"
    HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (80, "-normal"), (120, "-wide")]
    VERTICAL_BREAKPOINTS = [(0, "-short"), (24, "-tall")]
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("1", "view('live')", "Live", show=False),
        Binding("2", "view('signals')", "Signals", show=False),
        Binding("3", "view('positions')", "Positions", show=False),
        Binding("4", "view('journal')", "Journal", show=False),
        Binding("5", "view('diagnostics')", "Diagnostics", show=False),
        Binding("space", "play_pause", "Play/Pause", show=False),
        Binding("full_stop", "step", "Step", show=False),
        Binding("plus", "faster", "Faster", show=False),
        Binding("minus", "slower", "Slower", show=False),
        Binding("question_mark", "help", "Help", show=False),
        Binding("r", "refresh_panels", "Refresh", show=False),
        Binding("e", "record('entry')", "Record entry", show=False),
        Binding("s", "record('skip')", "Skip", show=False),
        Binding("p", "record('partial')", "Partial", show=False),
        Binding("m", "record('modify')", "Modify", show=False),
        Binding("x", "record('close')", "Close", show=False),
        Binding("n", "record('unlinked')", "Unlinked", show=False),
        Binding("q", "quit_app", "Quit", show=False),
    ]

    def __init__(
        self,
        session: ReplaySession,
        positions: PositionsSource | None = None,
        *,
        autoplay_timer: bool = True,
    ) -> None:
        super().__init__()
        self.session = session
        self.positions = positions or NoPositions()
        self.autoplay_timer = autoplay_timer
        self.current_view = "live"
        self.compact = False
        self.redraws = 0
        self._dirty = True
        self._last_tick = time.monotonic()
        self.snap: Snapshot = session.snapshot()

    # ------------------------------------------------------------------ layout

    def compose(self) -> ComposeResult:
        yield TextPanel(id="header")
        yield TextPanel(id="banner")
        yield TextPanel(id="notice")
        with ContentSwitcher(initial="live", id="views"):
            with VerticalScroll(id="live", classes="pane"):
                with Horizontal(id="live-top"):
                    yield TextPanel(id="context", classes="panel")
                    with Vertical(id="forming-box", classes="panel"):
                        yield TextPanel(id="forming-title", classes="title")
                        yield StateTable(id="forming")
                        yield TextPanel(id="lanes", classes="note")
                with Horizontal(id="live-mid"):
                    yield TextPanel(id="proposals", classes="panel")
                    yield TextPanel(id="positions-mini", classes="panel")
                yield TextPanel(id="feed")
            with VerticalScroll(id="signals", classes="pane"):
                yield TextPanel(id="dev-title", classes="title")
                yield StateTable(id="dev")
                yield TextPanel(id="ready-title", classes="title")
                yield StateTable(id="ready")
                yield TextPanel(id="signals-note", classes="note")
            with VerticalScroll(id="positions", classes="pane"):
                yield TextPanel(id="positions-body")
            with Vertical(id="journal", classes="pane"):
                yield Input(
                    placeholder="Filter: signal ID, date, state or mode", id="journal-filter"
                )
                yield TextPanel(id="journal-note", classes="note")
                yield StateTable(id="journal-table")
            with VerticalScroll(id="diagnostics", classes="pane"):
                yield TextPanel(id="diag")
        yield TextPanel(id="keys")

    def on_mount(self) -> None:
        self.set_interval(1 / REDRAW_HZ, self._redraw_tick)
        if self.autoplay_timer:
            self.set_interval(TICK_S, self._play_tick)
        self._render_all()
        self.query_one("#forming", StateTable).focus()

    def on_resize(self) -> None:
        compact = self.size.width < 120
        if compact != self.compact:
            self.compact = compact
        self._dirty = True
        self._render_all()

    # ------------------------------------------------------------------ timers

    def _play_tick(self) -> None:
        now = time.monotonic()
        elapsed, self._last_tick = now - self._last_tick, now
        if self.session.advance(min(elapsed, 0.5)):
            self._dirty = True

    def _redraw_tick(self) -> None:
        if self._dirty:
            self._render_all()

    # ------------------------------------------------------------------ rendering

    def _render_all(self) -> None:
        self._dirty = False
        self.redraws += 1
        snap = self.snap = self.session.snapshot()
        events = self.session.pipeline.signals.events
        q = self.query_one
        q("#header", TextPanel).set_lines(panels.header(snap, compact=self.compact))
        ban = panels.banner(snap)
        banner = q("#banner", TextPanel)
        banner.set_lines([ban] if ban else [])
        banner.set_class(ban is None, "-empty")
        q("#notice", TextPanel).set_lines(
            [
                [
                    (
                        f"Compact terminal {self.size.width}x{self.size.height}: "
                        "enlarge to >=80x24 "
                        "(>=120x34 full layout). Scroll with arrows/PgDn; Enter shows exact SL/TP.",
                        "caution",
                    )
                ]
            ]
        )
        # Live
        q("#context", TextPanel).set_lines(panels.context_panel(snap))
        q("#forming-title", TextPanel).set_lines([[("OPPORTUNITIES FORMING", "gold")]])
        cols = panels.FORMING_COLUMNS_COMPACT if self.compact else panels.FORMING_COLUMNS
        q("#forming", StateTable).show(cols, panels.forming_rows(snap, self.compact))
        lanes = [[(panels.lanes_summary(snap), "muted")]]
        if not snap.forming:
            lanes.insert(0, [("No developing opportunities", "muted")])
        q("#lanes", TextPanel).set_lines(lanes)
        q("#proposals", TextPanel).set_lines(panels.proposals_panel(snap, events))
        rows = self.positions.open_positions()
        q("#positions-mini", TextPanel).set_lines(panels.positions_panel(rows))
        q("#feed", TextPanel).set_lines(panels.feed_lines(snap, FEED_ROWS_LIVE))
        # Signals
        q("#dev-title", TextPanel).set_lines(
            [[("DEVELOPING / WATCHLIST — NOT TRADABLE YET", "gold")]]
        )
        q("#dev", StateTable).show(cols, panels.forming_rows(snap, self.compact))
        q("#ready-title", TextPanel).set_lines(
            [[("ACTIONABLE / READY — SIMULATED (REPLAY)", "gold")]]
        )
        rcols = panels.READY_COLUMNS_COMPACT if self.compact else panels.READY_COLUMNS
        q("#ready", StateTable).show(rcols, panels.ready_rows(snap, self.compact))
        note = [
            [
                (
                    "Duplicates suppressed: one immutable signal per frozen pair. "
                    "No numeric confidence score.",
                    "muted",
                )
            ]
        ]
        if not snap.ready:
            note.insert(
                0,
                [
                    (
                        "NO TRADE — conditions not met: " + panels.no_trade_reason(snap, events),
                        "caution",
                    )
                ],
            )
        q("#signals-note", TextPanel).set_lines(note)
        # Positions
        body = panels.positions_panel(rows)
        body.append(
            [
                ("Advisory events: none (no recorded positions).", "muted")
                if not rows
                else ("MANUAL BROKER VERIFICATION NEEDED", "caution")
            ]
        )
        q("#positions-body", TextPanel).set_lines(body)
        # Journal
        self._render_journal()
        # Diagnostics
        q("#diag", TextPanel).set_lines(panels.diagnostics_lines(snap))
        keys = (
            "1-5 Views  Space Play  . Step  +/- Pace  ? Help  q Quit  [No orders]"
            if self.compact
            else "1 Live 2 Signals 3 Positions 4 Journal 5 Diagnostics  "
            "Space Play . Step +/- Pace  ? Help  q Quit  [No orders]"
        )
        q("#keys", TextPanel).set_lines([[(keys, "muted")]])

    def _render_journal(self) -> None:
        version = self.session.pipeline.detector.params.strategy_version
        rows = panels.journal_rows(self.session.pipeline.signals.events, version, self.compact)
        needle = self.query_one("#journal-filter", Input).value
        shown = [r for r in rows if r.matches(needle)][-JOURNAL_ROWS:]
        note = (
            f"Session REPLAY signal events (SIMULATED, not persisted): {len(shown)} shown of "
            f"{len(rows)}. Local manual journal: no entries recorded."
        )
        if not rows:
            note = "No journal events yet"
        self.query_one("#journal-note", TextPanel).set_lines([[(note, "muted")]])
        cols = panels.JOURNAL_COLUMNS_COMPACT if self.compact else panels.JOURNAL_COLUMNS
        self.query_one("#journal-table", StateTable).show(
            cols, [(r.key, r.cells) for r in reversed(shown)]
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "journal-filter":
            self._render_journal()

    # ------------------------------------------------------------------ actions

    def action_view(self, name: str) -> None:
        self.current_view = name
        self.query_one("#views", ContentSwitcher).current = name
        focus = {
            "live": "#forming",
            "signals": "#ready",
            "positions": None,
            "journal": "#journal-table",
            "diagnostics": None,
        }[name]
        if focus:
            self.query_one(focus).focus()
        self._render_all()

    def action_play_pause(self) -> None:
        self._last_tick = time.monotonic()
        self.session.toggle_play()
        self._render_all()

    def action_step(self) -> None:
        if self.session.step():
            self._render_all()

    def action_faster(self) -> None:
        self.session.faster()
        self._render_all()

    def action_slower(self) -> None:
        self.session.slower()
        self._render_all()

    def action_refresh_panels(self) -> None:
        self._render_all()  # reads already-ingested state only

    def action_help(self) -> None:
        self.push_screen(Overlay(HELP, "help"))

    def action_quit_app(self) -> None:
        open_rows = [r for r in self.positions.open_positions() if r.state != "CLOSED"]
        if open_rows:
            self.push_screen(QuitWarning(len(open_rows)))
        else:
            self.exit()

    def _selection(self) -> tuple[str, str] | None:
        focused = self.focused
        if isinstance(focused, StateTable) and focused.selected_key:
            return focused.id or "", focused.selected_key
        return None

    def action_record(self, kind: str) -> None:
        """Manual-journal keys (docs/02 §3). M07 is view-only: explain, record nothing."""
        sel = self._selection()
        snap = self.snap
        msg: list[panels.Line]
        if kind in ("partial", "modify", "close"):
            msg = [
                [
                    (
                        "No manually confirmed position selected. Grog never changes broker "
                        "positions.",
                        "caution",
                    )
                ]
            ]
        elif kind == "unlinked":
            if self.current_view not in ("journal", "positions"):
                msg = [
                    [
                        (
                            "Unlinked manual entry (n) is available from Journal or Positions "
                            "only.",
                            "caution",
                        )
                    ]
                ]
            else:
                msg = [
                    [
                        (
                            "Local manual-journal recording is not available in this build; "
                            "nothing was recorded. No broker order is ever created.",
                            "caution",
                        )
                    ]
                ]
        elif sel is None:
            msg = [
                [("Select a READY signal first (2 Signals, arrows, Enter for details).", "caution")]
            ]
        elif sel[0] in ("forming", "dev"):
            msg = [
                [
                    (
                        f"NOT TRADABLE YET — {sel[1]} is FORMING; no on-plan local entry can be "
                        "recorded.",
                        "caution",
                    )
                ]
            ]
        else:
            view = next((v for v in snap.signals if v.record.signal_id == sel[1]), None)
            if view is None or view.status.state is not SignalState.READY:
                state = view.status.state.value if view else "UNKNOWN"
                msg = [
                    [
                        (
                            f"{sel[1]} is {state} — no on-plan entry or skip; terminal signals "
                            "are never resurrected.",
                            "caution",
                        )
                    ]
                ]
            else:
                action = "Record Entry" if kind == "entry" else "Skip"
                msg = [
                    [
                        (
                            f"{action} for {sel[1]}: local manual-journal recording is not "
                            "available in this build; nothing was recorded.",
                            "caution",
                        )
                    ],
                    [("No automatic broker order is created.", "muted")],
                ]
        self.push_screen(Overlay(msg, "notice-overlay"))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        table = event.data_table
        key = event.row_key.value
        snap = self.snap
        lines: list[panels.Line] | None = None
        if table.id in ("forming", "dev"):
            cand = next((c for c in snap.forming if c.candidate_id == key), None)
            if cand is not None:
                lines = panels.candidate_detail(snap, cand)
        elif table.id == "ready":
            view = next((v for v in snap.signals if v.record.signal_id == key), None)
            if view is not None:
                q = snap.quote
                lines = panels.signal_detail(snap, view, q.ask if q else None, q.bid if q else None)
        if lines is not None:
            self.push_screen(Overlay(lines, "detail"))

    @property
    def playback(self) -> Playback:
        return self.session.playback
