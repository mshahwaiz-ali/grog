"""Read-only native Overview over the existing ReplaySession.

Qt Widgets only: no broker actions, no journal mutations, no engine calculation.
The D01 preview is intentionally limited to Overview; other pages are disabled.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from grog.desktop.overview_model import OverviewState, from_snapshot
from grog.replay.session import Playback

if TYPE_CHECKING:
    from grog.journal.positions import PositionJournal
    from grog.replay.session import ReplaySession

REDRAW_INTERVAL = 0.25
PLAYBACK_INTERVAL_MS = 50

STYLE = """
QMainWindow, QWidget#root { background: #0B111A; color: #E7EDF5; }
QWidget { font-family: 'Noto Sans', 'DejaVu Sans', sans-serif; font-size: 13px; }
QFrame#sidebar { background: #101923; border-right: 1px solid #263344; }
QFrame#card { background: #14202D; border: 1px solid #2B3A49; border-radius: 12px; }
QFrame#decisionCard { background: #192535; border: 1px solid #6F5D43; border-radius: 14px; }
QFrame#toolbar { background: #111C28; border-top: 1px solid #2B3A49; }
QLabel#brand { font-size: 23px; font-weight: 700; color: #E6BA63; }
QLabel#subtitle { font-size: 11px; color: #9EADC0; }
QLabel#modeBadge { font-size: 12px; font-weight: 700; color: #E8C783;
    background: #372D21; padding: 8px 12px; border-radius: 8px; }
QLabel#heading { font-size: 25px; font-weight: 700; color: #EDF1F7; }
QLabel#section { font-size: 15px; font-weight: 700; color: #E7EDF5; }
QLabel#caption { font-size: 11px; color: #A1B1C3; }
QLabel#value { font-size: 27px; font-weight: 700; color: #F0F3F8; }
QLabel#decision { font-size: 22px; font-weight: 700; color: #E6BA63; }
QLabel#body { font-size: 13px; color: #DFE6F0; }
QLabel#stat { font-size: 16px; font-weight: 650; color: #DCE7F2; }
QPushButton { background: #253446; color: #F0F3F8; border: 1px solid #36495E;
    border-radius: 8px; padding: 9px 16px; font-weight: 600; }
QPushButton:hover { background: #32455C; }
QPushButton:pressed { background: #182739; }
QPushButton:disabled { color: #718094; background: #152231; border-color: #273549; }
QPushButton#activeNav { background: #443721; color: #F1CF8A; border-color: #6C5634;
    text-align: left; }
QPushButton#nav { text-align: left; }
QScrollArea { border: none; background: #0B111A; }
QScrollArea > QWidget > QWidget { background: #0B111A; }
"""


def _text(value: str, kind: str = "body", *, wrap: bool = False) -> QLabel:
    label = QLabel(value)
    label.setObjectName(kind)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(wrap)
    return label


def _box(parent: QVBoxLayout | QHBoxLayout, title: str, text: str) -> QLabel:
    card = QFrame()
    card.setObjectName("card")
    contents = QVBoxLayout(card)
    contents.setContentsMargins(18, 16, 18, 16)
    contents.setSpacing(8)
    contents.addWidget(_text(title, "caption"))
    value = _text(text, "value")
    contents.addWidget(value)
    parent.addWidget(card, 1)
    return value


class GoldWindow(QMainWindow):
    """One owner thread for ReplaySession, Qt widgets and the read-only journal."""

    def __init__(self, session: ReplaySession, journal: PositionJournal) -> None:
        super().__init__()
        self.session = session
        self.journal = journal
        self._last_tick = time.monotonic()
        self._last_redraw = 0.0
        self._pending_redraw = True
        self.setWindowTitle("Gold | XAUUSD Research Workstation [SIMULATED]")
        self.setMinimumSize(820, 620)
        self.resize(1180, 790)
        self.setStyleSheet(STYLE)
        self._build()
        self._render()
        self.timer = QTimer(self)
        self.timer.setInterval(PLAYBACK_INTERVAL_MS)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(202)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(17, 24, 17, 20)
        side.setSpacing(12)
        side.addWidget(_text("GOLD", "brand"))
        side.addWidget(_text("Research workstation", "subtitle"))
        side.addSpacing(26)
        pages = ("Overview", "Signals", "Positions", "Journal", "Diagnostics")
        for index, title in enumerate(pages):
            nav = QPushButton(title)
            nav.setObjectName("activeNav" if index == 0 else "nav")
            if index > 0:
                nav.setEnabled(False)
                nav.setToolTip("Coming in D02-D04; this D01 build is read-only Overview")
            side.addWidget(nav)
        side.addStretch()
        side.addWidget(_text("OFFLINE  ·  NO BROKER ORDERS", "caption", wrap=True))
        outer.addWidget(sidebar)

        content = QWidget()
        page = QVBoxLayout(content)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        main = QVBoxLayout(inner)
        main.setContentsMargins(28, 25, 28, 24)
        main.setSpacing(17)
        main.addWidget(_text("Market overview", "heading"))
        self.source = _text("", "modeBadge", wrap=True)
        main.addWidget(self.source)
        self.time = _text("", "caption")
        main.addWidget(self.time)

        quotes = QHBoxLayout()
        quotes.setSpacing(12)
        self.bid = _box(quotes, "BID PRICE", "—")
        self.ask = _box(quotes, "ASK PRICE", "—")
        self.spread = _box(quotes, "SPREAD · GOLD PRICE UNITS", "—")
        main.addLayout(quotes)

        decision_card = QFrame()
        decision_card.setObjectName("decisionCard")
        decision = QVBoxLayout(decision_card)
        decision.setContentsMargins(22, 20, 22, 20)
        decision.setSpacing(12)
        decision.addWidget(_text("CURRENT RESEARCH DECISION", "caption"))
        self.decision = _text("", "decision", wrap=True)
        decision.addWidget(self.decision)
        self.decision_detail = _text("", "body", wrap=True)
        decision.addWidget(self.decision_detail)
        self.health = _text("", "caption", wrap=True)
        decision.addWidget(self.health)
        main.addWidget(decision_card)

        main.addWidget(_text("Market structure", "section"))
        context = QHBoxLayout()
        context.setSpacing(12)
        self.h1 = _box(context, "1 HOUR · CONFIRMED TREND", "—")
        self.m15 = _box(context, "15 MIN · BUY / SELL CONTEXT", "—")
        self.m15.setWordWrap(True)
        self.m5 = _box(context, "5 MIN · SETUP", "—")
        self.m5.setWordWrap(True)
        main.addLayout(context)
        self.context_note = _text("", "caption", wrap=True)
        main.addWidget(self.context_note)

        main.addWidget(_text("Developing watchlist", "section"))
        self.watchlist = _text("", "body", wrap=True)
        main.addWidget(self.watchlist)
        main.addWidget(_text("Saved manual-position summary", "section"))
        self.positions = _text("", "caption", wrap=True)
        main.addWidget(self.positions)
        main.addStretch()
        scroll.setWidget(inner)
        page.addWidget(scroll, 1)

        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        buttons = QHBoxLayout(toolbar)
        buttons.setContentsMargins(25, 12, 25, 12)
        buttons.setSpacing(10)
        self.play = QPushButton("Play replay")
        self.play.clicked.connect(self._play_pause)
        self.step = QPushButton("Step 1 quote")
        self.step.clicked.connect(self._step)
        self.slower = QPushButton("Slower")
        self.slower.clicked.connect(self._slower)
        self.faster = QPushButton("Faster")
        self.faster.clicked.connect(self._faster)
        for b in (self.play, self.step, self.slower, self.faster):
            buttons.addWidget(b)
        self.progress = _text("", "caption")
        buttons.addWidget(self.progress, 1)
        page.addWidget(toolbar)
        outer.addWidget(content, 1)

        self.shortcuts = []
        for key, action in (
            ("Space", self._play_pause),
            (".", self._step),
            ("+", self._faster),
            ("-", self._slower),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(action)
            self.shortcuts.append(shortcut)

    def _tick(self) -> None:
        now = time.monotonic()
        delta = min(now - self._last_tick, 0.5)
        self._last_tick = now
        if self.session.advance(delta):
            self._pending_redraw = True
        if self._pending_redraw and now - self._last_redraw >= REDRAW_INTERVAL:
            self._render()

    def _render(self) -> None:
        # Journal is queried read-only; never construct a false empty overlay on failure.
        overlay = self.journal.signal_actions(self.session.source.source_id)
        positions = self.journal.open_positions()
        snapshot = self.session.snapshot()
        state = from_snapshot(
            snapshot,
            self.session.pipeline.signals.events,
            overlay,
            open_positions=len(positions),
        )
        self._apply(state)
        self._last_redraw = time.monotonic()
        self._pending_redraw = False

    def _apply(self, s: OverviewState) -> None:
        for widget, value in (
            (self.source, s.source), (self.time, s.virtual_utc),
            (self.bid, s.bid), (self.ask, s.ask), (self.spread, s.spread),
            (self.decision, s.headline), (self.decision_detail, s.description),
            (self.health, f"SOURCE {s.source_health} · {s.source_health_detail}"),
            (self.h1, s.h1), (self.m15, s.m15), (self.m5, s.m5),
            (self.context_note, s.context_note),
            (self.watchlist, "\n\n".join(s.watchlist) if s.watchlist else "No developing setups."),
            (self.positions, s.open_positions),
            (self.progress, s.playback + "  ·  " + s.progress),
        ):
            widget.setText(value)
        self.play.setText(
            "Pause replay" if self.session.playback is Playback.PLAYING else "Play replay"
        )
        self.play.setEnabled(self.session.playback is not Playback.ENDED)
        self.step.setEnabled(self.session.playback is Playback.PAUSED)

    def _play_pause(self) -> None:
        if self.session.playback is Playback.ENDED:
            return
        self.session.toggle_play()
        self._last_tick = time.monotonic()
        self._render()

    def _step(self) -> None:
        if self.session.playback is Playback.PAUSED and self.session.step():
            self._render()

    def _faster(self) -> None:
        self.session.faster()
        self._render()

    def _slower(self) -> None:
        self.session.slower()
        self._render()
