"""Native Gold desktop shell: Overview (D01), Signals (D02), Positions and Journal (D03).

Qt GUI thread only: this module renders detached frames published by the replay worker
and the journal owner and sends user intents back through queued signals. It never
touches the ``ReplaySession`` or SQLite, performs no trading arithmetic and places no
orders. Manual local records (D03) go through :class:`ManualController`, which pauses the
replay, revalidates at save time and lets only the journal owner thread write.
Diagnostics stays disabled until D04.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QSettings, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QKeySequence, QResizeEvent, QShortcut
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from grog.desktop import theme
from grog.desktop.diagnostics_page import DiagnosticsPage
from grog.desktop.display_preferences import DisplayPreferences
from grog.desktop.frames import (
    REPLAY_LABELS,
    ModeLabels,
    OverviewFrame,
    PauseAck,
    Phase,
    StatusFrame,
)
from grog.desktop.help_dialog import HelpDialog
from grog.desktop.loading import LoadRequest
from grog.desktop.manual_controller import ManualController
from grog.desktop.presentation import view_time_text
from grog.desktop.records_pages import JournalPage, PositionsPage
from grog.desktop.replay_worker import ReplayWorker
from grog.desktop.settings_page import SettingsPage
from grog.desktop.signals_model import ActionFacts
from grog.desktop.signals_page import SignalsPage
from grog.desktop.theme import SPACE, Card, Metric, label, pill, set_tone
from grog.replay.session import Playback

WIDE = 1440  # docs/02 §16.1 width contract (logical px of the window)
MEDIUM = 1100
MIN_WIDTH, MIN_HEIGHT = 820, 620

# Exactly the bindings installed in GoldWindow._install_shortcuts (a test enforces it).
SHORTCUT_HELP = (
    ("1 … 5", "Overview · Signals · Positions · Journal · Diagnostics"),
    ("Space", "Play / pause the replay"),
    (".", "Step one quote (when paused)"),
    ("+ / = / -", "Faster / slower replay pace"),
    ("R", "Refresh: re-read the journal, never moves the replay"),
    ("E / S", "Signals: record entry / skip for the selected READY signal"),
    ("P / X / M", "Positions: partial close / close / modify stop-target of the selection"),
    ("N", "Positions or Journal: record an external OFF_PLAN fill"),
    ("? / F1", "This help"),
    ("Q", "Quit (refused while a form is open)"),
)

PAGES = (
    ("Overview", None),
    ("Signals", None),
    ("Positions", None),
    ("Journal", None),
    ("Diagnostics", None),
)

TONE_FOR_HEALTH = {"FRESH": "ok", "UNKNOWN": "warning", "STALE": "warning", "DEGRADED": "warning"}


class GoldWindow(QMainWindow):
    """Shell (sidebar, status strip, safety banner, page, replay toolbar) + Overview."""

    load_requested = Signal(object, int)
    toggle_requested = Signal()
    step_requested = Signal()
    faster_requested = Signal()
    slower_requested = Signal()
    refresh_requested = Signal()
    shutdown_requested = Signal()
    # Worker-bound intents carry the generation they were issued for (stale ones are ignored).
    _toggle_to_owner = Signal(int)
    _step_to_owner = Signal(int)
    _faster_to_owner = Signal(int)
    _slower_to_owner = Signal(int)
    _pause_to_owner = Signal(int, int)

    def __init__(
        self,
        request: LoadRequest,
        *,
        worker: QObject | None = None,
        journal_worker: QObject | None = None,
        on_startup_failure: Callable[[int, str], None] | None = None,
        ui_settings: QSettings | None = None,
    ) -> None:
        super().__init__()
        self._labels: ModeLabels = REPLAY_LABELS
        self._generation = 0
        self._last_sequence = 0
        self._pending: OverviewFrame | StatusFrame | None = None
        self._apply_scheduled = False
        self._has_engine_frame = False
        self._pause_token = 0
        self._pause_waiting: int | None = None
        self._pause_callbacks: dict[int, Callable[[PauseAck], None]] = {}
        self._on_startup_failure = on_startup_failure
        self._closed = False
        self._closing = False
        self._refresh_after: int | None = None
        self._source_id = request.source_id
        self._request = request
        self._journal_generation = 0
        self.frame: OverviewFrame | StatusFrame | None = None  # last applied frame
        self.frames_received = 0
        self.frames_applied = 0
        self.dropped_stale = 0
        self.last_ack: PauseAck | None = None
        self._layout_mode = ""

        self.preferences = DisplayPreferences(settings=ui_settings, parent=self)
        theme.activate(self.preferences.effective_theme)
        self.setWindowTitle("Gold — XAUUSD Decision Workstation")
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self.resize(1366, 768)
        self.setStyleSheet(theme.STYLESHEET)
        self._build()
        self.preferences.changed.connect(self._on_preferences_changed)
        self._apply_status(None)

        self.worker = worker if worker is not None else ReplayWorker()
        self.thread = QThread(self)
        self.thread.setObjectName("gold-replay-owner")
        self.worker.moveToThread(self.thread)
        self.worker.frame.connect(self._on_frame)
        self.worker.pause_acknowledged.connect(self._on_pause_ack)
        self.load_requested.connect(self.worker.load)
        self.toggle_requested.connect(lambda: self._relay(self._toggle_to_owner))
        self.step_requested.connect(lambda: self._relay(self._step_to_owner))
        self.faster_requested.connect(lambda: self._relay(self._faster_to_owner))
        self.slower_requested.connect(lambda: self._relay(self._slower_to_owner))
        self._toggle_to_owner.connect(self.worker.toggle_play)
        self._step_to_owner.connect(self.worker.step)
        self._faster_to_owner.connect(self.worker.faster)
        self._slower_to_owner.connect(self.worker.slower)
        self.refresh_requested.connect(self.worker.refresh)
        self._pause_to_owner.connect(self.worker.request_pause)
        self.shutdown_requested.connect(self.worker.shutdown)
        self.thread.finished.connect(self._owner_finished)
        self.thread.start()
        # D03: the journal owner (only writer). Without one the window stays read-only.
        self.manual: ManualController | None = None
        if journal_worker is not None:
            self.manual = ManualController(
                journal_worker,
                self.worker,
                parent_widget=self,
                request_pause=self.request_pause,
                frame=lambda: self.frame if isinstance(self.frame, OverviewFrame) else None,
                generation=lambda: self._generation,
            )
            self.manual.snapshot_changed.connect(self._on_journal_snapshot)
            self.manual.busy_changed.connect(lambda _b: self._sync_controls())
            self.manual.notice.connect(self._set_notice)
            self.manual.thread.finished.connect(self._owner_finished)
        for page in (self.signals_page, self.positions_page, self.journal_page):
            page.action_requested.connect(self._on_action_requested)
        self.signals_page.set_action_gate(self._signal_gate)
        self.positions_page.set_gate(self._record_gate)
        self.journal_page.set_gate(self._record_gate)
        self.load_source(request)

    # ================================================================ structure

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_status_strip())
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self._build_overview())
        self.signals_page = SignalsPage()
        self.signals_scroll = QScrollArea()
        self.signals_scroll.setWidgetResizable(True)
        self.signals_scroll.setWidget(self.signals_page)
        self.positions_page = PositionsPage()
        self.journal_page = JournalPage()
        self.diagnostics_page = DiagnosticsPage()
        self.pages = QStackedWidget()
        self.pages.addWidget(self.scroll)
        self.pages.addWidget(self.signals_scroll)
        for page in (self.positions_page, self.journal_page, self.diagnostics_page):
            holder = QScrollArea()
            holder.setWidgetResizable(True)
            holder.setWidget(page)
            self.pages.addWidget(holder)
        self.settings_page = SettingsPage(self.preferences)
        settings_holder = QScrollArea()
        settings_holder.setWidgetResizable(True)
        settings_holder.setWidget(self.settings_page)
        self.pages.addWidget(settings_holder)
        column.addWidget(self.pages, 1)
        column.addWidget(self._build_toolbar())
        outer.addLayout(column, 1)
        self._install_shortcuts()

    def _build_sidebar(self) -> QFrame:
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(SPACE[3], SPACE[4], SPACE[3], SPACE[3])
        side.setSpacing(SPACE[0])
        side.addWidget(label("GROG", "brand"))
        self.brand_sub = label("XAUUSD decision workstation", "brandSub", wrap=True)
        side.addWidget(self.brand_sub)
        side.addSpacing(SPACE[4])
        self.nav: list[QPushButton] = []
        self.nav_counts: list[QLabel] = []
        for index, (title, phase) in enumerate(PAGES):
            button = QPushButton(f"{index + 1}   {title}")
            button.setObjectName("navActive" if index == 0 else "nav")
            button.setAccessibleName(f"{title} page")
            if phase is not None:
                button.setEnabled(False)
                button.setToolTip(f"{title} arrives in {phase}.")
            else:
                button.setToolTip(f"Show {title} ({index + 1})")
                button.clicked.connect(lambda _checked=False, i=index: self.show_page(i))
            side.addWidget(button)
            count = label("", "navCount")
            count.setContentsMargins(SPACE[3] + 2, 0, 0, SPACE[1])
            side.addWidget(count)
            self.nav.append(button)
            self.nav_counts.append(count)
        self.later_note = label(
            "Manual records are local journal entries only. Press ? for keyboard help.",
            "meta",
            wrap=True,
        )
        self.later_note.setContentsMargins(SPACE[1], SPACE[2], 0, 0)
        side.addWidget(self.later_note)
        side.addStretch()
        self.settings_button = QPushButton("Settings")
        self.settings_button.setObjectName("nav")
        self.settings_button.setAccessibleName("Settings view")
        self.settings_button.setToolTip("Appearance and time display preferences")
        self.settings_button.clicked.connect(self.show_settings)
        side.addWidget(self.settings_button)
        self.safety_foot = label("Manual decisions only\nNo broker orders", "meta", wrap=True)
        side.addWidget(self.safety_foot)
        return self.sidebar

    def _build_status_strip(self) -> QFrame:
        strip = QFrame()
        strip.setObjectName("statusStrip")
        rows = QVBoxLayout(strip)
        rows.setContentsMargins(SPACE[4], SPACE[2], SPACE[4], SPACE[2])
        rows.setSpacing(SPACE[0])
        self.strip_top = QHBoxLayout()
        self.strip_top.setSpacing(SPACE[1])
        self.strip_top.addWidget(label("XAUUSD", "cardTitle"))
        self.mode_pill = pill("", "info")
        self.fidelity_pill = pill("", "warning")
        self.health_pill = pill("", "warning")
        self.playback_pill = pill("", "info")
        for p in (self.mode_pill, self.fidelity_pill, self.health_pill, self.playback_pill):
            self.strip_top.addWidget(p)
        self.strip_top.addStretch(1)
        self.clock_text = label("", "meta", select=True)
        self.clock_text.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.strip_top.addWidget(self.clock_text)
        rows.addLayout(self.strip_top)
        self.strip_bottom = QHBoxLayout()
        self.strip_bottom.setSpacing(SPACE[2])
        self.source_text = label("", "meta", select=True)
        self.source_text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.strip_bottom.addWidget(self.source_text, 1)
        rows.addLayout(self.strip_bottom)
        self.mode_pill.setAccessibleName("Data mode")
        self.fidelity_pill.setAccessibleName("Execution fidelity")
        self.health_pill.setAccessibleName("Source health")
        self.playback_pill.setAccessibleName("Replay playback state")
        return strip

    def _build_overview(self) -> QWidget:
        page = QWidget()
        body = QVBoxLayout(page)
        body.setContentsMargins(SPACE[4], SPACE[4] - 4, SPACE[4], SPACE[4])
        body.setSpacing(SPACE[3])

        body.addWidget(label("Overview", "pageTitle"))
        body.addWidget(
            label("Can I act now, why or why not, and at what sourced price?", "pagePurpose")
        )

        self.banner = Card()
        self.banner_text = label("", "body", wrap=True, select=True)
        self.banner.body.addWidget(self.banner_text)
        self.banner.setVisible(False)
        body.addWidget(self.banner)

        # Read from the journal snapshot when available, never from inferred broker state.
        self.record_alert = Card()
        self.record_alert_text = label("", "body", wrap=True, select=True)
        self.record_alert.body.addWidget(self.record_alert_text)
        self.record_alert.setVisible(False)
        body.addWidget(self.record_alert)

        self.decision = Card()
        self.decision_eyebrow = label("", "eyebrow")
        self.headline = label("", "overviewHeadline", wrap=True, select=True)
        self.description = label("", "body", wrap=True, select=True)
        self.lanes = label("", "meta", wrap=True)
        self.signal_ids = label("", "mono", wrap=True, select=True)
        self.signal_ids.setAccessibleName("Full signal IDs")
        self.signal_ids.setVisible(False)
        for w in (
            self.decision_eyebrow,
            self.headline,
            self.description,
            self.signal_ids,
            self.lanes,
        ):
            self.decision.body.addWidget(w)
        self.decision.body.setSpacing(SPACE[1] + 2)
        self.pending_condition = QFrame()
        self.pending_condition.setObjectName("overviewCondition")
        pending_layout = QVBoxLayout(self.pending_condition)
        pending_layout.setContentsMargins(SPACE[3], SPACE[2], SPACE[3], SPACE[2])
        pending_layout.setSpacing(SPACE[1])
        self.pending_title = label("PENDING ENGINE CONDITION · NOT TRADABLE", "eyebrow")
        self.pending_text = label("", "overviewConditionText", wrap=True, select=True)
        pending_layout.addWidget(self.pending_title)
        pending_layout.addWidget(self.pending_text)
        self.pending_condition.setVisible(False)
        self.decision.body.addWidget(self.pending_condition)
        self.review_signals = QPushButton("Review signals and exact plans")
        self.review_signals.setObjectName("overviewAction")
        self.review_signals.setAccessibleName("Review signals without selecting a trade")
        self.review_signals.setToolTip("Open Signals; no proposal is selected or executed")
        self.review_signals.clicked.connect(lambda: self.show_page(1))
        self.review_signals.setVisible(False)
        self.decision.body.addWidget(self.review_signals)
        body.addWidget(self.decision)

        self.quotes = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.quotes.setSpacing(SPACE[2])
        self.bid = Metric("Bid", "quote", "SELL entry side · XAUUSD price units")
        self.ask = Metric("Ask", "quote", "BUY entry side · XAUUSD price units")
        self.spread = Metric("Spread", "quote", "Ask minus bid · XAUUSD price units")
        for m in (self.bid, self.ask, self.spread):
            self.quotes.addWidget(m, 1)
        body.addLayout(self.quotes)
        self.quote_meta = label("", "meta", wrap=True, select=True)
        body.addWidget(self.quote_meta)

        self.columns = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.columns.setSpacing(SPACE[3])
        left = QVBoxLayout()
        left.setSpacing(SPACE[3])
        right = QVBoxLayout()
        right.setSpacing(SPACE[3])

        self.structure = Card("Market structure · confirmed bars")
        self.context_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.context_row.setSpacing(SPACE[2])
        self.h1 = Metric("1 hour · trend", caption="Last finalized H1")
        self.m15 = Metric("15 min · structure", caption="Buy / sell context")
        self.m5 = Metric("5 min · trigger", caption="Setup state")
        for m in (self.h1, self.m15, self.m5):
            m.setProperty("grogRaised", "true")
            self.context_row.addWidget(m, 1)
        self.structure.body.addLayout(self.context_row)
        self.context_note = label("", "meta", wrap=True)
        self.provisional = label("", "meta", wrap=True)
        self.structure.body.addWidget(self.context_note)
        self.structure.body.addWidget(self.provisional)
        left.addWidget(self.structure)

        self.watch = Card("Developing setups · not tradable")
        self.watch_text = label("", "body", wrap=True, select=True)
        self.watch.body.addWidget(self.watch_text)
        left.addWidget(self.watch)

        self.positions = Card("Manual positions · not broker-synced")
        self.positions_summary = label("", "overviewSummary", wrap=True)
        self.positions_detail = label("", "meta", wrap=True, select=True)
        self.positions_expand = QPushButton("Show local record details")
        self.positions_expand.setObjectName("overviewAction")
        self.positions_expand.setCheckable(True)
        self.positions_expand.setAccessibleName("Toggle local position details")
        self.positions_expand.toggled.connect(self._toggle_position_details)
        self.positions.body.addWidget(self.positions_summary)
        self.positions.body.addWidget(self.positions_expand)
        self.positions.body.addWidget(self.positions_detail)
        self.positions_detail.setVisible(False)
        right.addWidget(self.positions)

        self.recent = Card("Recent changes")
        self.recent_text = label("", "meta", wrap=True, select=True)
        self.recent.body.addWidget(self.recent_text)
        right.addWidget(self.recent)

        left.addStretch()
        right.addStretch()
        self.columns.addLayout(left, 3)
        self.columns.addLayout(right, 2)
        body.addLayout(self.columns)

        # Keep technical evidence available, but out of the ordinary decision path.
        self.evidence_toggle = QPushButton("Show advanced engine evidence")
        self.evidence_toggle.setObjectName("overviewAction")
        self.evidence_toggle.setCheckable(True)
        self.evidence_toggle.setAccessibleName("Toggle advanced engine evidence")
        self.evidence_toggle.toggled.connect(self._toggle_evidence)
        body.addWidget(self.evidence_toggle)
        self.diag = Card("Advanced engine evidence · read-only")
        self.diag_text = label("", "meta", wrap=True, select=True)
        self.diag.body.addWidget(self.diag_text)
        self.diag.setVisible(False)
        body.addWidget(self.diag)
        body.addStretch()
        return page

    def _toggle_position_details(self, expanded: bool) -> None:
        self.positions_detail.setVisible(expanded)
        self.positions_expand.setText(
            "Hide local record details" if expanded else "Show local record details"
        )

    def _toggle_evidence(self, expanded: bool) -> None:
        self.diag.setVisible(expanded)
        self.evidence_toggle.setText(
            "Hide advanced engine evidence" if expanded else "Show advanced engine evidence"
        )

    def _render_record_attention(self, frame: OverviewFrame) -> None:
        """Use actual local-journal readability and reconciliation facts only."""
        snapshot = self.manual.snapshot if self.manual is not None else None
        if snapshot is not None:
            readable = snapshot.readable
            pending = len(snapshot.needs_reconciliation()) if readable else 0
        else:
            readable = frame.positions.journal_ok
            pending = frame.positions.reconciliation_required or 0

        if not readable:
            self.record_alert.set_accent("error")
            self.record_alert_text.setText(
                "Local journal UNVERIFIED — records cannot be trusted or saved "
                "until the journal is available. Grog is not broker-synced."
            )
        elif pending:
            self.record_alert.set_accent("warning")
            self.record_alert_text.setText(
                f"{pending} local position(s) require reconciliation. Verify the actual "
                "broker state before confirming a local record. No broker orders are sent."
            )
        else:
            self.record_alert_text.setText("")
        self.record_alert.setVisible(not readable or pending > 0)

    def _build_toolbar(self) -> QFrame:
        self.toolbar = QFrame()
        self.toolbar.setObjectName("toolbar")
        rows = QVBoxLayout(self.toolbar)
        rows.setContentsMargins(SPACE[4], SPACE[2], SPACE[4], SPACE[2])
        rows.setSpacing(SPACE[0])
        self.bar_top = QHBoxLayout()
        self.bar_top.setSpacing(SPACE[1])
        self.play = QPushButton("Play")
        self.play.setObjectName("primary")
        self.play.setToolTip("Play or pause the replay (Space)")
        self.play.clicked.connect(self.toggle_play)
        self.step = QPushButton("Step 1 quote")
        self.step.setToolTip("Process exactly one quote while paused (.)")
        self.step.clicked.connect(self.step_once)
        self.slower = QPushButton("Slower")
        self.slower.setToolTip("Slower replay pace (-)")
        self.slower.clicked.connect(self.slower_requested.emit)
        self.pace = label("", "meta")
        self.faster = QPushButton("Faster")
        self.faster.setToolTip("Faster replay pace (+)")
        self.faster.clicked.connect(self.faster_requested.emit)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip(
            "Re-read the current engine snapshot; refresh never steps the replay (R)"
        )
        self.refresh_button.clicked.connect(self.refresh)
        for w in (self.play, self.step, self.slower, self.pace, self.faster, self.refresh_button):
            self.bar_top.addWidget(w)
        self.bar_top.addSpacing(SPACE[2])
        self.progress = label("", "meta", wrap=True)
        self.bar_top.addWidget(self.progress, 1)
        self.toolbar_safety = label("No broker orders", "meta")
        self.toolbar_safety.setMinimumWidth(self.toolbar_safety.sizeHint().width())
        self.bar_top.addWidget(self.toolbar_safety)
        rows.addLayout(self.bar_top)
        self.bar_bottom = QHBoxLayout()
        self.bar_bottom.setSpacing(SPACE[2])
        self.notice = label("", "meta", wrap=True)
        self.notice.setAccessibleName("Last action result")
        self.notice.setVisible(False)
        rows.addLayout(self.bar_bottom)
        rows.addWidget(self.notice)
        return self.toolbar

    def _install_shortcuts(self) -> None:
        self.shortcuts: list[QShortcut] = []
        self.help_dialog: HelpDialog | None = None
        for key, action in (
            ("5", lambda: self.show_page(4)),
            ("?", self.show_help),
            ("F1", self.show_help),
            ("Space", self.toggle_play),
            (".", self.step_once),
            ("+", self.faster_requested.emit),
            ("=", self.faster_requested.emit),
            ("-", self.slower_requested.emit),
            ("R", self.refresh),
            ("Q", self.close),
            ("1", lambda: self.show_page(0)),
            ("2", lambda: self.show_page(1)),
            ("3", lambda: self.show_page(2)),
            ("4", lambda: self.show_page(3)),
            ("E", lambda: self._shortcut_action("entry")),
            ("S", lambda: self._shortcut_action("skip")),
            ("P", lambda: self._shortcut_action("partial")),
            ("M", lambda: self._shortcut_action("modify")),
            ("X", lambda: self._shortcut_action("close")),
            ("N", lambda: self._shortcut_action("offplan")),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(action)
            self.shortcuts.append(shortcut)

    def show_help(self) -> HelpDialog:
        """Keyboard help (``?`` / F1) generated from SHORTCUT_HELP; Esc or Close returns."""
        if self.help_dialog is None:
            self.help_dialog = HelpDialog(SHORTCUT_HELP, self)
        self.help_dialog.open()
        self.help_dialog.close_button.setFocus()
        return self.help_dialog

    # ================================================================ pages

    def show_page(self, index: int) -> None:
        """Switch one of the five numbered trading pages; no replay mutation."""
        if PAGES[index][1] is not None:
            return
        self.pages.setCurrentIndex(index)
        self._sync_navigation()

    def show_settings(self) -> None:
        """Settings is an unnumbered utility view, not a sixth trading screen."""
        self.pages.setCurrentIndex(len(PAGES))
        self._sync_navigation()

    def _sync_navigation(self) -> None:
        active = self.pages.currentIndex()
        for index, button in enumerate(self.nav):
            if PAGES[index][1] is None:
                button.setObjectName("navActive" if index == active else "nav")
                button.style().unpolish(button)
                button.style().polish(button)
        self.settings_button.setObjectName("navActive" if active == len(PAGES) else "nav")
        self.settings_button.style().unpolish(self.settings_button)
        self.settings_button.style().polish(self.settings_button)

    @Slot()
    def _on_preferences_changed(self) -> None:
        """Purely visual repaint; never asks replay/journal workers for new data."""
        theme.activate(self.preferences.effective_theme)
        theme.apply_to(self)
        if isinstance(self.frame, OverviewFrame):
            self._update_time_display(self.frame)

    def _update_time_display(self, frame: OverviewFrame) -> None:
        """Render named replay/provider/receipt clocks; exact UTC remains in tooltip."""
        zone = self.preferences.time_zone
        virtual_ms = frame.clock.virtual_ms if frame.clock is not None else None
        self.clock_text.setText(view_time_text(virtual_ms, zone, clock="replay"))
        quote = frame.quote
        age = (
            "UNKNOWN"
            if frame.diagnostics.quote_age_ms is None
            else f"{frame.diagnostics.quote_age_ms:,} ms"
        )
        self.quote_meta.setText(
            f"{view_time_text(quote.provider_ms, zone, clock='provider')}  ·  "
            f"{view_time_text(quote.received_ms, zone, clock='received')}  ·  "
            f"Quote age {age}\n{frame.labels.price_caveat}."
        )
        self.quote_meta.setToolTip(
            f"Provider UTC {quote.provider_utc}\nReceived UTC {quote.received_utc}"
        )

    @property
    def page_index(self) -> int:
        return self.pages.currentIndex()

    # ================================================================ intents

    def load_source(self, request: LoadRequest) -> int:
        """Begin a new source generation; older queued frames are ignored from now on."""
        self._generation += 1
        self._source_id = request.source_id
        self._last_sequence = 0
        self._has_engine_frame = False
        self._pending = None
        self._pause_waiting = None
        self._sync_controls()  # intents of the previous source are disabled immediately
        self._request = request
        if getattr(self, "manual", None) is not None:
            # The writable journal opens only after this source loaded (first engine frame):
            # a source that cannot be loaded leaves the state directory byte-for-byte unchanged.
            self.manual.forget_snapshot()
            self.positions_page.apply_snapshot(None)
            self.journal_page.apply_snapshot(None)
            self.diagnostics_page.apply_journal(None)  # never the previous source's journal
        self.load_requested.emit(request, self._generation)
        return self._generation

    def refresh(self) -> None:
        """Ask the owner to republish its current snapshot; replay position is unaffected."""
        if self._controls_ready():
            self._refresh_after = self.frame.tag.sequence
            self._set_notice("Refreshing the view from the replay owner…")
            if self.manual is not None:
                self.manual.reload()  # the journal owner re-reads and pushes records
            self.refresh_requested.emit()

    def _set_notice(self, text: str) -> None:
        self.notice.setText(text)
        self.notice.setVisible(bool(text))

    def toggle_play(self) -> None:
        if self._controls_ready():
            self._set_notice("")
            self.toggle_requested.emit()

    def step_once(self) -> None:
        if self._controls_ready() and isinstance(self.frame, OverviewFrame):
            if self.frame.transport.can_step:
                self.step_requested.emit()

    def request_pause(self, callback: Callable[[PauseAck], None] | None = None) -> int:
        """Nonblocking pause handshake; controls stay disabled until the worker acks."""
        self._pause_token += 1
        token = self._pause_token
        self._pause_waiting = token
        if callback is not None:
            self._pause_callbacks[token] = callback
        self._sync_controls()
        self._pause_to_owner.emit(token, self._generation)
        return token

    def _relay(self, signal) -> None:
        if self._controls_ready():
            signal.emit(self._generation)

    def _controls_ready(self) -> bool:
        return (
            not self._closed
            and not self._closing
            and self._pause_waiting is None
            and not (getattr(self, "manual", None) is not None and self.manual.busy)
            and isinstance(self.frame, OverviewFrame)
            and self.frame.tag.generation == self._generation
            and self.frame.tag.source_id == self._source_id
            and self.frame.labels.has_transport
        )

    # ================================================================ frames

    @Slot(object)
    def _on_frame(self, frame: OverviewFrame | StatusFrame) -> None:
        self.frames_received += 1
        if self._closing:
            return
        if (
            frame.tag.generation != self._generation
            or frame.tag.source_id != self._source_id
            or frame.tag.sequence <= self._last_sequence
        ):
            self.dropped_stale += 1  # an obsolete source generation or out-of-date frame
            return
        self._last_sequence = frame.tag.sequence
        if isinstance(frame, StatusFrame) and frame.phase is Phase.FAULT:
            self._pending = frame
            self._apply_pending()  # faults are shown immediately
            return
        self._pending = frame  # a newer presentation frame replaces an unpainted one
        if not self._apply_scheduled:
            self._apply_scheduled = True
            QTimer.singleShot(0, self._apply_pending)

    def _apply_pending(self) -> None:
        self._apply_scheduled = False
        frame, self._pending = self._pending, None
        if frame is None or self._closed:
            return
        self.frames_applied += 1
        self.frame = frame
        if isinstance(frame, OverviewFrame):
            self._has_engine_frame = True
            if self.manual is not None and self._journal_generation != self._generation:
                self._journal_generation = self._generation
                self.manual.open_journal(self._request, self._generation)
            self._apply_overview(frame)
        else:
            self._apply_status(frame)
            if (
                frame.phase is Phase.FAULT
                and frame.exit_code is not None
                and not self._has_engine_frame
                and self._on_startup_failure is not None
            ):
                self._on_startup_failure(frame.exit_code, frame.detail)
        self._sync_controls()

    @Slot(object)
    def _on_pause_ack(self, ack: PauseAck) -> None:
        if (
            ack.generation != self._generation
            or ack.source_id != self._source_id
            or ack.token != self._pause_waiting
        ):
            return
        if self._pending is not None:
            self._apply_pending()  # the paused frame (queued before the ack) is shown first
        self._pause_waiting = None
        self.last_ack = ack
        callback = self._pause_callbacks.pop(ack.token, None)
        self._sync_controls()
        if callback is not None:
            callback(ack)

    # ================================================================ rendering

    def _apply_common(self, labels: ModeLabels) -> None:
        self._labels = labels
        self.mode_pill.setText(labels.mode.value)
        self.fidelity_pill.setText(labels.fidelity)
        self.toolbar.setVisible(labels.has_transport)

    def _apply_status(self, frame: StatusFrame | None) -> None:
        labels = frame.labels if frame is not None else REPLAY_LABELS
        self._apply_common(labels)
        fault = frame is not None and frame.phase is Phase.FAULT
        title = frame.title if frame else "Starting"
        detail = frame.detail if frame else "Opening the replay owner thread."
        self.health_pill.setText("ERROR" if fault else "UNKNOWN")
        set_tone(self.health_pill, "error" if fault else "warning", pill=True)
        self.playback_pill.setText("STOPPED" if fault else "LOADING")
        set_tone(self.playback_pill, "error" if fault else "info", pill=True)
        source = frame.tag.source_id if frame else ""
        self.source_text.setText(f"Source {source}" if source else "")
        last = frame.last_virtual_utc if frame else None
        self.clock_text.setText(f"Last known {labels.clock_caption.lower()} {last}" if last else "")
        self.decision_eyebrow.setText(
            "SOURCE FAULT" if fault else f"{labels.mode.value} · {labels.fidelity}"
        )
        self.headline.setText(title)
        set_tone(self.headline, "error" if fault else "neutral")
        self.decision.set_accent("error" if fault else "info")
        self.description.setText(detail)
        self.lanes.setText("Trading-record actions stay disabled until data is loaded.")
        self.banner.setVisible(fault)
        self.record_alert.setVisible(False)
        self.pending_condition.setVisible(False)
        self.review_signals.setVisible(False)
        if fault:
            self.banner.set_accent("error")
            self.banner_text.setText(
                "Replay data is unavailable or stopped. The values below are not current; "
                "no new signals are evaluated."
            )
        for m in (self.bid, self.ask, self.spread, self.h1, self.m15, self.m5):
            m.value.setText("—")
        self.quote_meta.setText("No quote loaded. Unknown values are shown as —, never 0.")
        for widget in (
            self.context_note,
            self.provisional,
            self.watch_text,
            self.positions_summary,
            self.positions_detail,
            self.recent_text,
            self.diag_text,
        ):
            widget.setText("")
        self.watch_text.setText("Not evaluated yet.")
        self.progress.setText("Loading…" if not fault else "Stopped")
        self.signal_ids.setVisible(False)
        self.pace.setText("")
        for count in self.nav_counts:
            count.setText("")
            count.setVisible(False)
        self.signals_page.show_unavailable(
            "Signals unavailable — " + ("source fault" if fault else "loading source")
        )
        if fault:
            self.diagnostics_page.mark_stale(f"{title}: {detail}", last)
        else:
            self.diagnostics_page.apply(None)

    def _apply_overview(self, f: OverviewFrame) -> None:
        o, q, t, d, p = f.overview, f.quote, f.transport, f.diagnostics, f.positions
        self._apply_common(f.labels)
        self.health_pill.setText(f"FEED {d.health}")
        set_tone(self.health_pill, TONE_FOR_HEALTH.get(d.health, "error"), pill=True)
        playing = t.playback is Playback.PLAYING
        self.playback_pill.setText(t.playback_text)
        set_tone(
            self.playback_pill,
            "ok" if playing else "warning" if t.playback is Playback.ENDED else "info",
            pill=True,
        )
        self.source_text.setText(f"Source {f.tag.source_id} · {d.origin} · {d.raw_symbol}")
        self.source_text.setToolTip(
            "Batch SHA-256: " + ", ".join(d.batch_sha256s) + f"\nConfig hash: {d.config_hash}"
        )
        self._update_time_display(f)

        self.banner.setVisible(f.banner is not None)
        if f.banner is not None:
            self.banner.set_accent("warning" if t.playback is Playback.ENDED else "error")
            self.banner_text.setText(f.banner)

        mode = f.labels
        self.decision_eyebrow.setText(f"CURRENT DECISION · {mode.mode.value} · {mode.fidelity}")
        self.headline.setText(o.headline)
        set_tone(self.headline, {"ready": "ready", "warning": "warning"}.get(o.tone, "neutral"))
        self.decision.set_accent({"ready": "ready", "warning": "warning"}.get(o.tone, "neutral"))
        self.description.setText(o.description)
        self.lanes.setText(
            f"Developing {f.forming}  ·  READY (simulated) {f.ready}  ·  Execution-blocked "
            f"{f.blocked}  ·  No ranking or automatic selection"
        )
        pending = (
            f.forming > 0
            and bool(o.watchlist)
            and d.health == "FRESH"
            and t.playback is not Playback.ENDED
        )
        self.pending_condition.setVisible(pending)
        if pending:
            if f.forming == 1 and len(o.watchlist) == 1:
                self.pending_title.setText("PENDING ENGINE CONDITION · NOT TRADABLE")
                self.pending_text.setText(o.watchlist[0])
            else:
                self.pending_title.setText("MULTIPLE DEVELOPING CONDITIONS")
                self.pending_text.setText(
                    f"{f.forming} candidates are developing; none is ranked or "
                    "confirmed READY. Compare each exact condition in Signals."
                )
        self.review_signals.setVisible(f.forming > 0 or f.ready > 0 or f.blocked > 0)
        self._render_record_attention(f)

        self.bid.value.setText(q.bid_text)
        self.ask.value.setText(q.ask_text)
        self.spread.value.setText(q.spread_text)
        self.h1.value.setText(o.h1)
        self.m15.value.setText(o.m15)
        self.m5.value.setText(o.m5)
        closes = {
            tf: f"Last confirmed {tf} bar closed {when} · available {available}"
            for tf, _n, when, available in d.bars
        }
        c = f.causes
        for card, cause, tf in (
            (self.h1, c.h1, "H1"),
            (self.m15, c.m15, "M15"),
            (self.m5, c.m5, "M5"),
        ):
            card.caption.setText(f"{cause}\n{closes.get(tf, f'No confirmed {tf} bar yet')}")
        self.context_note.setText(o.context_note)
        self.provisional.setText("\n".join(d.provisional))

        self.watch_text.setText(
            "\n\n".join(o.watchlist) if o.watchlist else "No developing setups right now."
        )
        if p.journal_ok:
            self.positions_summary.setText(
                f"{p.open_count} open  ·  {p.reconciliation_required} need reconciliation  ·  "
                f"{p.off_plan} off-plan"
            )
        else:
            self.positions_summary.setText("UNVERIFIED — journal could not be read")
        self.positions_detail.setText("\n".join((*p.lines, *p.advisories, p.journal_note)))

        self.recent_text.setText("\n".join(o.recent) if o.recent else "No changes yet.")
        bars = "   ".join(f"{tf} {n:,} confirmed" for tf, n, _when, _available in d.bars)
        reasons = ", ".join(d.health_reasons) or "none reported"
        self.diag_text.setText(
            f"Warm-up  {d.warmup}  ({'sufficient' if d.warmup_sufficient else 'INSUFFICIENT'})\n"
            f"Bars  {bars}\n"
            f"Feed  {d.health} · reasons: {reasons} · gaps recorded {d.gaps}\n"
            f"Engine  triggers observed {d.triggers_observed} · signal events {d.signal_events}"
            f" · M5 ATR14 exact {d.m5_atr_exact}\n"
            f"Config v{d.config_version} · hash {d.config_hash[:16]}… · state schema "
            f"v{d.state_schema_version}"
        )
        self.diag_text.setToolTip(f"Config hash {d.config_hash}\n" + "\n".join(d.batch_sha256s))

        if self._refresh_after is not None and f.tag.sequence > self._refresh_after:
            self._refresh_after = None
            self._set_notice(
                f"View refreshed from the engine snapshot (frame {f.tag.sequence}) · "
                f"replay position {t.processed:,} quotes"
            )
        ids = [f"READY signal ID  {sid}" for sid in f.ready_ids]
        ids += [f"Execution-blocked signal ID  {sid}" for sid in f.blocked_ids]
        self.signal_ids.setText("\n".join(ids))
        self.signal_ids.setVisible(bool(ids))
        self.pace.setText(t.pace_text)
        self.progress.setText(self._progress_text(t))
        self.play.setText("Pause" if playing else "Play")
        self.signals_page.apply(f.signals)
        self.diagnostics_page.apply(f.diag)
        self.positions_page.apply_marks(f.marks)
        self.journal_page.apply_engine(f.engine_rows, (f.tag.source_id, f.tag.generation))
        snap = self.manual.snapshot if self.manual is not None else None
        rr = len(snap.needs_reconciliation()) if snap is not None else 0
        pos_count = (
            f"{len(snap.open_positions())} open" + (f" · {rr} to reconcile" if rr else "")
            if snap is not None and snap.readable
            else ""
        )
        counts = ("", f"{f.ready} ready · {f.forming} developing", pos_count, "", "")
        for label_widget, text in zip(self.nav_counts, counts, strict=True):
            label_widget.setText(text)
            label_widget.setVisible(bool(text))

    @staticmethod
    def _progress_text(t) -> str:
        return f"{t.processed:,} / {t.total:,} quotes  ·  {t.pre_roll:,} pre-roll (history)"

    def _sync_controls(self) -> None:
        f = self.frame
        ready = self._controls_ready() and isinstance(f, OverviewFrame)
        t = f.transport if isinstance(f, OverviewFrame) else None
        self.play.setEnabled(bool(ready and t and t.can_toggle))
        self.step.setEnabled(bool(ready and t and t.can_step))
        self.refresh_button.setEnabled(bool(ready))
        live = bool(ready and t and t.can_toggle)  # pace is irrelevant once a replay ended
        self.faster.setEnabled(live and t.pace_text != "FAST")
        self.slower.setEnabled(live and t.pace_text != "50 ev/s")
        if self._pause_waiting is not None:
            self.progress.setText("Pausing — waiting for the replay owner to confirm…")
        elif getattr(self, "manual", None) is not None and self.manual.busy:
            self.progress.setText("Paused while recording — Play/Step resume after the form closes")
        elif t is not None and not self._closing:
            self.progress.setText(self._progress_text(t))
        if hasattr(self, "positions_page"):
            self.signals_page.refresh_actions()
            self.positions_page.set_gate(self._record_gate)
            self.journal_page.set_gate(self._record_gate)

    # ================================================================ layout

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._relayout(event.size().width())

    def _relayout(self, width: int) -> None:
        mode = "wide" if width >= WIDE else "medium" if width >= MEDIUM else "narrow"
        if mode == self._layout_mode:
            return
        self._layout_mode = mode
        self.sidebar.setFixedWidth({"wide": 220, "medium": 200, "narrow": 164}[mode])
        self.brand_sub.setVisible(mode != "narrow")
        vertical = QBoxLayout.Direction.TopToBottom
        horizontal = QBoxLayout.Direction.LeftToRight
        self.columns.setDirection(horizontal if mode == "wide" else vertical)
        self.signals_page.set_layout_mode(mode)
        self.positions_page.set_layout_mode(mode)
        self.journal_page.set_layout_mode(mode)
        self.diagnostics_page.set_layout_mode(mode)
        self.context_row.setDirection(vertical if mode == "narrow" else horizontal)
        if mode == "narrow":
            self.strip_bottom.addWidget(self.clock_text)
            # Controls keep the first row; progress wraps beside the safety text below.
            self.bar_bottom.addWidget(self.progress, 1)
            self.bar_bottom.addWidget(self.toolbar_safety)
        else:
            self.strip_top.addWidget(self.clock_text)
            self.bar_top.addWidget(self.progress, 1)
            self.bar_top.addWidget(self.toolbar_safety)

    @property
    def layout_mode(self) -> str:
        return self._layout_mode

    # ================================================================ shutdown

    def _begin_close(self) -> None:
        """Stop accepting intents and ask the owner to stop, without blocking the GUI."""
        if self._closing:
            return
        self._closing = True
        self._sync_controls()
        self.decision_eyebrow.setText("CLOSING")
        self.headline.setText("Closing — waiting for the replay owner to stop")
        set_tone(self.headline, "neutral")
        self.description.setText(
            "Any load or pre-roll already in progress finishes first; nothing is written. "
            "The window closes as soon as the replay owner thread has stopped."
        )
        self.progress.setText("Closing…")
        if self.manual is not None:
            n = self.manual.oversight_count()
            self.description.setText(
                self.description.text()
                + f" {n} local open position(s) still need your external oversight at the "
                "broker; Grog does not close or monitor them after exit. Any save already "
                "submitted finishes and reports first."
            )
            self.manual.shutdown()  # queued after any in-flight command on its own thread
        self.shutdown_requested.emit()  # queued behind any in-progress work
        self.thread.quit()

    def _threads_running(self) -> bool:
        journal = self.manual.thread.isRunning() if self.manual is not None else False
        return self.thread.isRunning() or journal

    @Slot()
    def _owner_finished(self) -> None:
        if self._closing and not self._closed and not self._threads_running():
            self._closed = True
            self.close()

    def shutdown(self) -> None:
        """Blocking join for use only after the Qt event loop has ended (program exit)."""
        if self.manual is not None and self.manual.dialog is not None:
            self.manual.dialog.state = self.manual.dialog.EDITING
            self.manual.dialog.done(0)  # nothing unsaved is written on forced exit
        self._begin_close()
        self.thread.wait()
        if self.manual is not None:
            # stopped -> thread.quit() is queued to this (finished) loop: quit directly.
            from PySide6.QtCore import QCoreApplication

            deadline = 200
            while self.manual.thread.isRunning() and deadline:
                QCoreApplication.processEvents()
                self.manual.thread.wait(25)
                deadline -= 1
            if self.manual.thread.isRunning():
                self.manual.thread.quit()
                self.manual.thread.wait()
        self._closed = True

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self.manual is not None and not self._closing:
            ok, why = self.manual.can_close()
            if not ok:
                event.ignore()
                self._set_notice(f"Not closing: {why}")
                return
        if self._threads_running():
            event.ignore()  # never destroy a running owner thread; close asynchronously
            self._begin_close()
            return
        self._closing = self._closed = True
        super().closeEvent(event)

    # ================================================================ D03 manual records

    @Slot(object)
    def _on_journal_snapshot(self, snap) -> None:
        self.positions_page.apply_snapshot(snap)
        self.journal_page.apply_snapshot(snap)
        self.diagnostics_page.apply_journal(snap)
        if isinstance(self.frame, OverviewFrame):
            self._render_record_attention(self.frame)
        self._sync_controls()

    def _frame_current(self) -> bool:
        f = self.frame
        return (
            isinstance(f, OverviewFrame)
            and f.tag.generation == self._generation
            and f.tag.source_id == self._source_id
        )

    def _record_gate(self) -> str | None:
        if getattr(self, "manual", None) is None:
            return "Local journal not connected — read-only."
        if self._closing or self._closed:
            return "Grog is closing."
        if self._pause_waiting is not None:
            return "Waiting for the replay to pause."
        if not self._frame_current():
            return "No current replay frame (loading or stopped)."
        return self.manual.why_not_writable()

    def _signal_gate(self, action: ActionFacts) -> tuple[bool, str]:
        why = self._record_gate()
        return (why is None, why or "")

    @Slot(str, str)
    def _on_action_requested(self, kind: str, target: str) -> None:
        if self._record_gate() is not None or self.manual is None:
            self._set_notice(f"Nothing opened: {self._record_gate()}")
            return
        if kind in ("entry", "skip"):
            self.manual.open_signal_form(kind, target)
        elif kind == "offplan":
            self.manual.open_off_plan()
        else:
            self.manual.open_position_form(kind, target)

    def _shortcut_action(self, kind: str) -> None:
        """Scoped keys: act on the visible page's selection only (never through inputs)."""
        page = self.page_index
        if kind in ("entry", "skip") and page == 1:
            for b in self.signals_page.action_buttons:
                if b.property("action_kind") == kind and b.isEnabled():
                    b.click()
                    return
            self._set_notice(f"{kind.title()}: select a READY signal whose action is enabled.")
        elif kind in ("partial", "modify", "close") and page == 2:
            b = self.positions_page.buttons[kind]
            if b.isEnabled():
                b.click()
            else:
                self._set_notice(self.positions_page.action_reason.text() or "Select a position.")
        elif kind == "offplan" and page in (2, 3):
            self._on_action_requested("offplan", "")
