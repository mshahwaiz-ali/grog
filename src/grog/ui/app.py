"""Textual App shell: five views, replay controls and responsive layout (docs/02).

The app renders :class:`grog.replay.session.Snapshot` objects, forwards playback controls
to :class:`grog.replay.session.ReplaySession` and records operator statements only through
the validated :class:`grog.journal.positions.PositionJournal` (M08). It never writes market
data, never changes engine rules or signals, and contains no broker/order code path.
"""

from __future__ import annotations

import time
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import ContentSwitcher, DataTable, Input

from grog.domain.enums import SignalState
from grog.journal.positions import ManualPosition, PositionJournal, TouchTracker
from grog.replay.session import Playback, ReplaySession, Snapshot
from grog.ui import manual, panels
from grog.ui.forms import PositionDetail
from grog.ui.screens import HELP, Overlay, QuitWarning
from grog.ui.widgets import StateTable, TextPanel

REDRAW_HZ = 4  # docs/02 §2 ui.max_refresh_hz (view only; engine never waits on it)
TICK_S = 0.05  # playback work slice; only decides how many quotes run per slice
VIEWS = ("live", "signals", "positions", "journal", "diagnostics")
FEED_ROWS_LIVE = 8
JOURNAL_ROWS = 50  # docs/02 §11 visible buffer


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
        journal: PositionJournal | None = None,
        *,
        autoplay_timer: bool = True,
    ) -> None:
        super().__init__()
        self.session = session
        self.journal = journal
        self.tracker = TouchTracker()
        session.quote_observers.append(self.tracker.on_quote)
        self._open: list[ManualPosition] = []
        self._reload_positions()
        self.autoplay_timer = autoplay_timer
        self.current_view = "live"
        self.compact = False
        self.redraws = 0
        self._dirty = True
        self._last_tick = time.monotonic()
        self.snap: Snapshot = session.snapshot()
        self.last_message: str | None = None

    # ------------------------------------------------------------------ layout

    def compose(self) -> ComposeResult:
        yield TextPanel(id="header")
        yield TextPanel(id="tabs")
        yield TextPanel(id="banner")
        yield TextPanel(id="notice")
        with ContentSwitcher(initial="live", id="views"):
            with VerticalScroll(id="live", classes="pane"):
                with Horizontal(id="live-top", classes="row"):
                    yield TextPanel(id="context", classes="panel boxed")
                    with Vertical(id="forming-box", classes="panel"):
                        yield StateTable(id="forming")
                        yield TextPanel(id="lanes", classes="note")
                with Horizontal(id="live-mid", classes="row"):
                    yield TextPanel(id="proposals", classes="panel boxed")
                    yield TextPanel(id="positions-mini", classes="panel boxed")
                yield TextPanel(id="feed", classes="panel boxed")
            with VerticalScroll(id="signals", classes="pane"):
                with Vertical(id="ready-box", classes="box"):
                    yield StateTable(id="ready")
                    yield TextPanel(id="signals-note", classes="note")
                with Vertical(id="dev-box", classes="box"):
                    yield StateTable(id="dev")
            with VerticalScroll(id="positions", classes="pane"):
                with Vertical(id="positions-box", classes="box"):
                    yield StateTable(id="positions-table")
                yield TextPanel(id="positions-body", classes="panel boxed")
            with Vertical(id="journal", classes="pane"):
                with Vertical(id="journal-box", classes="box"):
                    yield Input(
                        placeholder="Filter: signal ID, date, state or mode", id="journal-filter"
                    )
                    yield TextPanel(id="journal-note", classes="note")
                    yield StateTable(id="journal-table")
            with VerticalScroll(id="diagnostics", classes="pane"):
                yield TextPanel(id="diag", classes="panel boxed")
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
        narrow = self.size.width < 80
        q("#header", TextPanel).set_lines(panels.header(snap, compact=self.compact))
        unverified = sum(1 for p in self._open if p.state.value == "RECONCILIATION_REQUIRED")
        live_ready = sum(1 for v in snap.ready if not v.pre_roll)
        q("#tabs", TextPanel).set_lines(
            [
                panels.tabs_line(
                    self.current_view,
                    ready=live_ready,
                    open_positions=len(self._open),
                    unverified=unverified,
                    narrow=self.compact,
                )
            ]
        )
        ban = panels.banner(snap)
        banner = q("#banner", TextPanel)
        banner.set_lines([ban] if ban else [])
        banner.set_class(ban is None, "-empty")
        q("#notice", TextPanel).set_lines(
            [
                [
                    (
                        f"Compact {self.size.width}x{self.size.height}: enlarge to >=80x24 "
                        "(>=120x34 full). PgDn scrolls; Enter shows exact SL/TP.",
                        "caution",
                    )
                ]
            ]
        )
        # Live
        q("#context", TextPanel).set_lines(panels.context_panel(snap))
        q("#forming-box").border_title = "OPPORTUNITIES FORMING"
        cols = panels.FORMING_COLUMNS_COMPACT if self.compact else panels.FORMING_COLUMNS
        q("#forming", StateTable).show(cols, panels.forming_rows(snap, self.compact))
        lanes = [[(panels.lanes_summary(snap, len(self._open)), "muted")]]
        if not snap.forming:
            lanes.insert(0, [("No developing opportunities", "muted")])
        q("#lanes", TextPanel).set_lines(lanes)
        overlay = self._overlay()
        q("#proposals", TextPanel).set_lines(
            panels.proposals_panel(snap, events, overlay, self._open)
        )
        rows = self._open
        q("#positions-mini", TextPanel).set_lines(manual.live_positions_panel(rows, snap))
        q("#feed", TextPanel).set_lines(panels.feed_lines(snap, FEED_ROWS_LIVE))
        # Signals
        q("#dev-box").border_title = "DEVELOPING / WATCHLIST — NOT TRADABLE YET"
        q("#dev", StateTable).show(cols, panels.forming_rows(snap, self.compact))
        q("#ready-box").border_title = "ACTIONABLE / READY — SIMULATED (REPLAY)"
        rcols = panels.READY_COLUMNS_COMPACT if self.compact else panels.READY_COLUMNS
        q("#ready", StateTable).show(rcols, panels.ready_rows(snap, self.compact, overlay))
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
                        "NO TRADE — conditions not met: "
                        + panels.no_trade_reason(snap, events, overlay),
                        "caution",
                    )
                ],
            )
        q("#signals-note", TextPanel).set_lines(note)
        # Positions
        title = "ACTIVE MANUAL POSITIONS — local journal, not broker positions"
        if self.journal is None:
            title += " (journal unavailable: no writable local state)"
        if manual.marks_note(rows, snap):
            title += " · MARKS NOT FRESH (*)"
        q("#positions-box").border_title = title
        pcols = (
            manual.POSITION_COLUMNS_NARROW
            if narrow
            else manual.POSITION_COLUMNS_COMPACT
            if self.compact
            else manual.POSITION_COLUMNS
        )
        q("#positions-table", StateTable).show(
            pcols, manual.position_rows(rows, snap, self.tracker, self.compact, narrow)
        )
        q("#positions-body", TextPanel).set_lines(
            [
                [("ADVISORY EVENTS & RECONCILIATION — observations, not advice", "gold")],
                *manual.positions_strip(rows, snap, self.tracker),
            ]
        )
        # Journal
        self._render_journal()
        # Diagnostics
        q("#diag", TextPanel).set_lines(panels.diagnostics_lines(snap))
        q("#keys", TextPanel).set_lines(
            [panels.key_bar(self.current_view, narrow=self.size.width < 110)]
        )

    def _render_journal(self) -> None:
        version = self.session.pipeline.detector.params.strategy_version
        session_rows = panels.journal_rows(
            self.session.pipeline.signals.events, version, self.compact
        )
        timed = [
            (e.decision_time_ms, r)
            for e, r in zip(self.session.pipeline.signals.events, session_rows, strict=True)
        ]
        local = manual.manual_journal_rows(self.journal, self.compact) if self.journal else []
        timed += local
        timed.sort(key=lambda t: t[0])
        rows = [r for _, r in timed]
        needle = self.query_one("#journal-filter", Input).value
        shown = [r for r in rows if r.matches(needle)][-JOURNAL_ROWS:]
        stored = "unavailable (read-only)" if self.journal is None else f"{len(local)} saved"
        note = (
            f"{len(shown)} shown of {len(rows)}. Session REPLAY signal events: SIMULATED, not "
            f"persisted. Local manual journal: {stored}."
        )
        if not rows:
            note = "No journal events yet"
        self.query_one("#journal-note", TextPanel).set_lines([[(note, "muted")]])
        self.query_one(
            "#journal-box"
        ).border_title = "JOURNAL — local manual records + session REPLAY events"
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
            "positions": "#positions-table",
            "journal": "#journal-table",
            "diagnostics": "#diagnostics",  # scroll pane; never leave focus in a hidden input
        }[name]
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
        self._reload_positions()
        if self._open:
            self.push_screen(QuitWarning(len(self._open)))
        else:
            self.exit()

    def _selection(self) -> tuple[str, str] | None:
        focused = self.focused
        if isinstance(focused, StateTable) and focused.selected_key:
            return focused.id or "", focused.selected_key
        return None

    # ------------------------------------------------------------------ manual journal

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """docs/02 §3: global keys never fire while a modal/form is open."""
        if isinstance(self.screen, ModalScreen):
            return False
        return True

    def _reload_positions(self) -> None:
        self._open = self.journal.open_positions() if self.journal else []
        self.tracker.track(self._open)

    def _overlay(self) -> dict[str, tuple[str, str | None]]:
        """First local journal action per signal (overlay only; signals never change)."""
        if self.journal is None:
            return {}
        return self.journal.signal_actions(self.session.source.source_id)

    def _notice(self, text: str, style: str = "caution") -> None:
        self.push_screen(
            Overlay(
                [[(text, style)], [("No broker order is ever created.", "muted")]], "notice-overlay"
            )
        )

    def _after_form(self, message: str | None) -> None:
        if message:
            self._reload_positions()
            self.last_message = message
            self._render_all()
            self._notice(message, "ok")

    def _selected_position(self) -> ManualPosition | None:
        table = self.query_one("#positions-table", StateTable)
        if self.current_view != "positions" or table.selected_key is None:
            return None
        return next((p for p in self._open if p.position_id == table.selected_key), None)

    def action_record(self, kind: str) -> None:
        """Manual-journal keys (docs/02 §3, §9): open a confirm-before-save local form."""
        snap = self.snap = self.session.snapshot()
        if self.journal is None and kind in ("partial", "modify", "close", "unlinked"):
            self._notice("Local journal unavailable (no writable local state); nothing recorded.")
            return
        if kind in ("partial", "modify", "close"):
            pos = self._selected_position()
            if pos is None:
                self._notice(
                    "Select a recorded open position first (3 Positions, arrows). Grog never "
                    "changes broker positions."
                )
                return
            build = {
                "partial": manual.partial_form,
                "modify": manual.modify_form,
                "close": manual.close_form,
            }[kind]
            self.push_screen(build(self.journal, snap, pos), self._after_form)
            return
        if kind == "unlinked":
            if self.current_view not in ("journal", "positions"):
                self._notice(
                    "Unlinked manual entry (n) is available from Journal or Positions only."
                )
                return
            self.push_screen(manual.unlinked_form(self.journal, snap), self._after_form)
            return
        sel = self._selection()
        if sel is None or sel[0] not in ("ready", "forming", "dev"):
            self._notice("Select a READY signal first (2 Signals, arrows, Enter for details).")
            return
        if sel[0] in ("forming", "dev"):
            self._notice(
                f"NOT TRADABLE YET — {sel[1]} is FORMING; no on-plan local entry can be recorded."
            )
            return
        view = next((v for v in snap.signals if v.record.signal_id == sel[1]), None)
        if view is None or view.status.state is not SignalState.READY:
            state = view.status.state.value if view else "UNKNOWN"
            self._notice(
                f"{sel[1]} is {state} — no on-plan entry or skip; terminal signals are never "
                "resurrected. Use n (Journal/Positions) for an OFF_PLAN external trade."
            )
            return
        if self.journal is None:
            self._notice("Local journal unavailable (no writable local state); nothing recorded.")
            return
        status = self.journal.signal_status(view.record.original_source_id, sel[1])
        if status is not None:
            self._notice(f"{sel[1]} is already {status} in the local journal.")
            return
        if kind == "entry":
            self._reload_positions()
            form = manual.entry_form(self.journal, snap, view, self._open)
        else:
            form = manual.skip_form(self.journal, snap, view)
        self.push_screen(form, self._after_form)

    def _confirm_open(self, position_id: str):
        journal = self.journal
        assert journal is not None

        def run(action_id: str) -> str:
            eff = self.snap.virtual_time_ms or journal.store.now_ms()
            journal.confirm_open(action_id, position_id, effective_ms=eff)
            return f"Saved locally: {position_id} verified open — MONITORING."

        return run

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
                lines = panels.signal_detail(
                    snap,
                    view,
                    q.ask if q else None,
                    q.bid if q else None,
                    self._overlay(),
                    self._open,
                )
        elif table.id == "positions-table" and self.journal is not None:
            pos = next((p for p in self._open if p.position_id == key), None)
            if pos is not None:
                confirm = (
                    self._confirm_open(pos.position_id)
                    if pos.state.value == "RECONCILIATION_REQUIRED"
                    else None
                )
                detail = manual.position_detail(
                    pos, self.journal.events(pos.position_id), snap, self.tracker
                )
                self.push_screen(PositionDetail(detail, confirm), self._after_form)
                return
        if lines is not None:
            self.push_screen(Overlay(lines, "detail"))

    @property
    def playback(self) -> Playback:
        return self.session.playback
