"""Positions and Journal pages (D03). Qt GUI thread only.

Both pages render detached facts (``records_model``) and never touch SQLite, the replay
session or a live record. Rows are keyed by stable unique IDs, so a refresh never moves
the operator's selection to another record. Positions offers the manual journeys for the
selected record (Partial, Close, Modify stop/target, Confirm still open) and the
separate OFF_PLAN external-fill form; whether a button is enabled combines the record's
state with the window's gate (writable journal, no open form). Journal is read-only:
there is no edit, correction or delete control (docs/08 GUI-50).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from grog.desktop.frames import EngineRow, MarkFacts
from grog.desktop.journal_model import JournalMode, JournalSnapshot
from grog.desktop.records_model import (
    ALL,
    JOURNAL_PAGE_COLUMNS,
    OPEN,
    POSITION_COLUMNS,
    POSITION_FILTERS,
    STREAMS,
    JournalEntry,
    engine_entries,
    filter_entries,
    operator_entries,
    position_detail,
    position_rows,
)
from grog.desktop.theme import SPACE, Card, Metric, label, set_tone
from grog.journal.positions import JournalError, PositionState
from grog.ui.manual import parse_time

KEY_ROLE = Qt.ItemDataRole.UserRole + 1
TIME_SAMPLE = "2026-10-14 00:15:00.071 UTC"
JOURNAL_ROW_LIMIT = 2000  # rows painted at once; filters reach every stored record

Gate = Callable[[], str | None]


def _table(columns: Sequence[str], name: str) -> tuple[QTableView, QStandardItemModel]:
    model = QStandardItemModel(0, len(columns))
    model.setHorizontalHeaderLabels(list(columns))
    table = QTableView()
    table.setModel(model)
    table.setAccessibleName(name)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(True)
    header.setMinimumSectionSize(56)
    table.setMinimumHeight(240)
    return table, model


def _fill(table: QTableView, model: QStandardItemModel, rows, selected: str | None) -> None:
    """Replace rows; keep the selected key selected (never auto-select another)."""
    table.setUpdatesEnabled(False)
    blocker = table.selectionModel().blockSignals(True)  # a refresh is not a user selection
    model.removeRows(0, model.rowCount())
    for key, cells in rows:
        items = []
        for text in cells:
            item = QStandardItem(text)
            item.setData(key, KEY_ROLE)
            item.setToolTip(text)
            items.append(item)
        model.appendRow(items)
    if model.rowCount() and not table.property("sized"):
        table.setProperty("sized", True)  # once: later refreshes keep the user's widths
        table.resizeColumnsToContents()
        header = table.horizontalHeader()
        exact_time = table.fontMetrics().horizontalAdvance(TIME_SAMPLE) + 24
        for c in range(model.columnCount()):
            wanted = min(max(header.sectionSize(c), 64), 360)
            if model.headerData(c, Qt.Orientation.Horizontal).upper().endswith("UTC"):
                wanted = max(wanted, exact_time)  # exact ms UTC is never elided
            header.resizeSection(c, wanted)
    if selected is not None:
        for r in range(model.rowCount()):
            if model.item(r, 0).data(KEY_ROLE) == selected:
                table.selectRow(r)
                break
    table.selectionModel().blockSignals(blocker)
    table.setUpdatesEnabled(True)


def _selected_key(table: QTableView) -> str | None:
    index = table.selectionModel().currentIndex()
    if not index.isValid():
        return None
    return index.data(KEY_ROLE)


class PositionsPage(QWidget):
    action_requested = Signal(str, str)  # (partial | close | modify | confirm | offplan, ID)

    def __init__(self) -> None:
        super().__init__()
        self._gate: Gate = lambda: "Local journal not connected — read-only."
        self.snapshot: JournalSnapshot | None = None
        self.marks: tuple[MarkFacts, ...] = ()
        self.selected_key: str | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE[4] + 4, SPACE[4], SPACE[4] + 4, SPACE[4])
        outer.setSpacing(SPACE[2])
        outer.addWidget(label("Positions", "pageTitle"))
        outer.addWidget(
            label(
                "Your manually recorded positions. Local records only — not broker-synced; "
                "Grog never closes, reduces or modifies anything at a broker.",
                "pagePurpose",
                wrap=True,
            )
        )
        self.mode_banner = Card()
        self.mode_text = label("", "body", wrap=True, select=True)
        self.mode_banner.body.addWidget(self.mode_text)
        outer.addWidget(self.mode_banner)

        # Counts reflect the detached journal only; broker state is never inferred.
        self.summary_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.summary_row.setSpacing(SPACE[2])
        self.open_metric = Metric("Open local", caption="Not broker-synced")
        self.reconcile_metric = Metric("Need reconciliation", caption="Verify externally")
        self.closed_metric = Metric("Closed local", caption="Records only")
        for metric in (self.open_metric, self.reconcile_metric, self.closed_metric):
            metric.setProperty("grogRaised", "true")
            self.summary_row.addWidget(metric, 1)
        outer.addLayout(self.summary_row)

        self.worklist = label("", "body", wrap=True)
        self.worklist.setAccessibleName("Reconciliation worklist")
        outer.addWidget(self.worklist)

        bar = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.addItems(list(POSITION_FILTERS))
        self.filter.setAccessibleName("Position filter")
        self.filter.currentTextChanged.connect(lambda _t: self._render())
        self.off_plan_button = QPushButton("Record external fill (OFF_PLAN)…")
        self.off_plan_button.setToolTip(
            "Record a trade you made yourself that is not a READY on-plan entry (n)"
        )
        self.off_plan_button.clicked.connect(lambda: self.action_requested.emit("offplan", ""))
        bar.addWidget(label("Show", "meta"))
        bar.addWidget(self.filter)
        bar.addStretch(1)
        bar.addWidget(self.off_plan_button)
        outer.addLayout(bar)

        self.content = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.content.setSpacing(SPACE[3])
        self.table, self.model = _table(POSITION_COLUMNS, "Positions table")
        self.table.selectionModel().currentRowChanged.connect(lambda *_a: self._on_select())
        self.empty = label("", "meta", wrap=True)
        left = QVBoxLayout()
        left.addWidget(self.empty)
        left.addWidget(self.table, 1)
        self.content.addLayout(left, 3)
        self.detail = Card("Selected position")
        self.detail_title = label(
            "Select a position to see its complete record.", "cardTitle", wrap=True, select=True
        )
        self.detail_status = label("", "body", wrap=True)
        self.detail_summary = label("", "overviewSummary", wrap=True, select=True)
        self.detail_summary.setAccessibleName("Local position status summary")
        self.detail_body = label("", "body", wrap=True, select=True)
        self.events_title = label("EVENTS (append-only, oldest first)", "eyebrow")
        self.events = label("", "mono", wrap=True, select=True)
        self.events.setAccessibleName("Position events")
        for w in (
            self.detail_title,
            self.detail_status,
            self.detail_summary,
            self.detail_body,
            self.events_title,
            self.events,
        ):
            self.detail.body.addWidget(w)
        actions = QHBoxLayout()
        self.buttons: dict[str, QPushButton] = {}
        for kind, text, tip in (
            ("partial", "Partial close…", "Record a partial close you made at your broker (p)"),
            ("close", "Close…", "Record the full close of the remaining quantity (x)"),
            ("modify", "Modify stop/target…", "Record a stop/target change at your broker (m)"),
            ("confirm", "Confirm still open…", "Record that you verified it open at the broker"),
        ):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _c=False, k=kind: self._emit(k))
            actions.addWidget(b)
            self.buttons[kind] = b
        actions.addStretch()
        self.detail.body.addLayout(actions)
        self.action_reason = label("", "meta", wrap=True)
        self.detail.body.addWidget(self.action_reason)
        self.detail.body.addStretch()
        self.content.addWidget(self.detail, 2)
        outer.addLayout(self.content, 1)
        self._render()

    # ------------------------------------------------------------------ inputs

    def set_gate(self, gate: Gate) -> None:
        self._gate = gate
        self._render_actions()

    def set_layout_mode(self, mode: str) -> None:
        """Records have many exact columns: the table always spans the page width and
        the complete detail follows below it (no column is hidden behind the detail)."""
        self.content.setDirection(QBoxLayout.Direction.TopToBottom)
        self.summary_row.setDirection(
            QBoxLayout.Direction.TopToBottom
            if mode == "narrow"
            else QBoxLayout.Direction.LeftToRight
        )

    def apply_snapshot(self, snap: JournalSnapshot | None) -> None:
        self.snapshot = snap
        self._render()

    def apply_marks(self, marks: tuple[MarkFacts, ...]) -> None:
        if marks != self.marks:
            self.marks = marks
            self._render()

    def _emit(self, kind: str) -> None:
        if self.selected_key is not None:
            self.action_requested.emit(kind, self.selected_key)

    # ------------------------------------------------------------------ rendering

    def _render(self) -> None:
        snap = self.snapshot
        if snap is None or not snap.readable:
            counts = ("—", "—", "—")
        else:
            open_count = len(snap.open_positions())
            counts = (
                str(open_count),
                str(len(snap.needs_reconciliation())),
                str(len(snap.positions) - open_count),
            )
        for metric, value in zip(
            (self.open_metric, self.reconcile_metric, self.closed_metric),
            counts,
            strict=True,
        ):
            metric.value.setText(value)
        if snap is None:
            self.mode_text.setText("Opening the local journal…")
            self.mode_banner.set_accent("warning")
            _fill(self.table, self.model, [], None)
            self.empty.setText("No records loaded yet.")
            self.worklist.setText("")
            self._render_detail()
            return
        tone = {"WRITABLE": "ok", "READ_ONLY": "warning"}.get(snap.mode.value, "error")
        self.mode_banner.set_accent(tone)
        self.mode_text.setText(f"Local journal {snap.mode.value} — {snap.reason}")
        set_tone(self.mode_text, tone)
        rr = snap.needs_reconciliation() if snap.readable else []
        if not snap.readable:
            self.worklist.setText(
                "Reconciliation status UNKNOWN — local records could not be read. "
                "No broker positions can be inferred."
            )
            set_tone(self.worklist, "error")
        elif rr:
            restored = f" ({len(snap.restored)} marked at this start)" if snap.restored else ""
            self.worklist.setText(
                f"RECONCILIATION REQUIRED: {len(rr)} position(s){restored} — verify each at "
                "your broker: " + ", ".join(p.position_id for p in rr)
            )
            set_tone(self.worklist, "error")
        else:
            self.worklist.setText("No positions need reconciliation.")
            set_tone(self.worklist, "info")
        rows = position_rows(snap, self.marks, self.filter.currentText())
        _fill(self.table, self.model, [(r.key, r.cells) for r in rows], self.selected_key)
        if not snap.readable:
            self.empty.setText("Records unavailable — nothing is assumed (no empty overlay).")
        elif not rows:
            what = self.filter.currentText().lower()
            self.empty.setText(
                "No manually confirmed positions. Nothing is assumed executed."
                if self.filter.currentText() in (OPEN, ALL)
                else f"No {what} positions."
            )
        else:
            self.empty.setText(
                f"{len(rows)} shown · MARK = closeable BID (BUY) / ASK (SELL) from SIMULATED "
                f"replay quotes; * = not FRESH. {('R = gross, net R UNKNOWN.')}"
            )
        self._render_detail()

    def _on_select(self) -> None:
        self.selected_key = _selected_key(self.table)
        self._render_detail()

    def _render_detail(self) -> None:
        snap = self.snapshot
        pos = snap.position(self.selected_key) if snap and self.selected_key else None
        if pos is None:
            if self.selected_key is not None and snap is not None:
                self.detail_title.setText(f"{self.selected_key} is not in the current records.")
            else:
                self.detail_title.setText("Select a position to see its complete record.")
            for w in (self.detail_status, self.detail_summary, self.detail_body, self.events):
                w.setText("")
        else:
            title, status, lines, events = position_detail(snap, pos, self.marks)
            self.detail_title.setText(title)
            self.detail_status.setText(status)
            self.detail_summary.setText(
                f"{pos.side.value} · {pos.state.value.replace('_', ' ')} · "
                f"{pos.plan_status.value} · local record, not broker-synced"
            )
            set_tone(
                self.detail_status,
                "error" if pos.state is PositionState.RECONCILIATION_REQUIRED else "neutral",
            )
            self.detail_body.setText("\n".join(lines))
            self.events.setText("\n".join(events))
        self._render_actions()

    def _render_actions(self) -> None:
        snap = self.snapshot
        pos = snap.position(self.selected_key) if snap and self.selected_key else None
        gate = self._gate()
        self.off_plan_button.setEnabled(gate is None)
        self.off_plan_button.setToolTip(gate or "Record a trade you made yourself (n)")
        reasons = []
        for kind, b in self.buttons.items():
            why = gate
            if why is None:
                if pos is None:
                    why = "Select an open position."
                elif not pos.is_open:
                    why = f"{pos.position_id} is CLOSED."
                elif kind == "confirm" and pos.state is not PositionState.RECONCILIATION_REQUIRED:
                    why = "Only a RECONCILIATION REQUIRED position can be confirmed open."
            b.setEnabled(why is None)
            b.setVisible(
                kind != "confirm"
                or pos is None
                or pos.state is PositionState.RECONCILIATION_REQUIRED
            )
            if why and why not in reasons and b.isVisible():
                reasons.append(why)
        self.action_reason.setText("Disabled: " + " ".join(reasons) if reasons else "")

    def detail_text(self) -> str:
        parts = [
            self.detail_title.text(),
            self.detail_status.text(),
            self.detail_summary.text(),
            self.detail_body.text(),
            self.events.text(),
            self.action_reason.text(),
        ]
        return "\n".join(p for p in parts if p)


class JournalPage(QWidget):
    action_requested = Signal(str, str)  # only ("offplan", "")

    def __init__(self) -> None:
        super().__init__()
        self._gate: Gate = lambda: "Local journal not connected — read-only."
        self.snapshot: JournalSnapshot | None = None
        self._operator: tuple[JournalEntry, ...] = ()
        self._engine: tuple[JournalEntry, ...] = ()
        self._engine_count = -1
        self._engine_key: tuple = ()
        self.shown: list[JournalEntry] = []
        self.selected_key: str | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE[4] + 4, SPACE[4], SPACE[4] + 4, SPACE[4])
        outer.setSpacing(SPACE[2])
        outer.addWidget(label("Journal", "pageTitle"))
        outer.addWidget(
            label(
                "Operator records (durable, local) and SIM ENGINE events (reconstructed from "
                "this replay, not persisted), newest first. Read-only: historical records "
                "cannot be edited or deleted here.",
                "pagePurpose",
                wrap=True,
            )
        )
        self.mode_text = label("", "meta", wrap=True)
        outer.addWidget(self.mode_text)
        f1 = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search IDs, reasons, notes, mode…")
        self.search.setAccessibleName("Search journal")
        self.search.setClearButtonEnabled(True)
        self.stream = QComboBox()
        self.stream.addItems(list(STREAMS))
        self.stream.setAccessibleName("Recorded by filter")
        self.action = QComboBox()
        self.action.setAccessibleName("Action filter")
        self.action.addItem("All actions")
        self.side = QComboBox()
        self.side.addItems(["All sides", "BUY", "SELL"])
        self.side.setAccessibleName("Side filter")
        for w in (self.search,):
            f1.addWidget(w, 1)
        for w in (self.stream, self.action, self.side):
            w.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            w.setMinimumContentsLength(9)  # long action names never widen the page
            f1.addWidget(w)
        outer.addLayout(f1)
        f2 = QHBoxLayout()
        self.from_utc = QLineEdit()
        self.from_utc.setPlaceholderText("From UTC, e.g. 2026-10-14T00:00:00Z")
        self.from_utc.setAccessibleName("From UTC")
        self.to_utc = QLineEdit()
        self.to_utc.setPlaceholderText("To UTC (inclusive)")
        self.to_utc.setAccessibleName("To UTC")
        self.range_error = label("", "meta", wrap=True)
        set_tone(self.range_error, "error")
        self.off_plan_button = QPushButton("Record external fill (OFF_PLAN)…")
        self.off_plan_button.clicked.connect(lambda: self.action_requested.emit("offplan", ""))
        f2.addWidget(self.from_utc, 1)
        f2.addWidget(self.to_utc, 1)
        f2.addWidget(self.range_error, 1)
        f2.addWidget(self.off_plan_button)
        outer.addLayout(f2)
        for w in (self.search, self.from_utc, self.to_utc):
            w.textChanged.connect(lambda _t: self._render())
        for c in (self.stream, self.action, self.side):
            c.currentTextChanged.connect(lambda _t: self._render())

        self.content = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.content.setSpacing(SPACE[3])
        self.table, self.model = _table(JOURNAL_PAGE_COLUMNS, "Journal table")
        self.table.selectionModel().currentRowChanged.connect(lambda *_a: self._on_select())
        self.count = label("", "meta", wrap=True)
        left = QVBoxLayout()
        left.addWidget(self.count)
        left.addWidget(self.table, 1)
        self.content.addLayout(left, 3)
        self.detail = Card("Selected record")
        self.detail_text_label = label(
            "Select a row to see the full record.", "body", wrap=True, select=True
        )
        self.detail.body.addWidget(self.detail_text_label)
        self.detail.body.addWidget(
            label(
                "Corrections and deletions are not supported in this build; a future, "
                "separately approved workflow is required.",
                "meta",
                wrap=True,
            )
        )
        self.detail.body.addStretch()
        self.content.addWidget(self.detail, 2)
        outer.addLayout(self.content, 1)
        self._render()

    def set_gate(self, gate: Gate) -> None:
        self._gate = gate
        why = gate()
        self.off_plan_button.setEnabled(why is None)
        self.off_plan_button.setToolTip(why or "Record a trade you made yourself (n)")

    def set_layout_mode(self, mode: str) -> None:
        self.content.setDirection(QBoxLayout.Direction.TopToBottom)

    def apply_snapshot(self, snap: JournalSnapshot | None) -> None:
        self.snapshot = snap
        self._operator = operator_entries(snap)
        self._render()

    def apply_engine(self, rows: tuple[EngineRow, ...], generation_key: tuple) -> None:
        if generation_key == self._engine_key and len(rows) == self._engine_count:
            return
        self._engine_key, self._engine_count = generation_key, len(rows)
        self._engine = engine_entries(rows)
        self._render()

    def _bounds(self) -> tuple[int | None, int | None, str]:
        lo = hi = None
        errors = []
        for edit, name in ((self.from_utc, "From"), (self.to_utc, "To")):
            text = edit.text().strip()
            if not text:
                continue
            try:
                ms = parse_time(text, f"{name} UTC")
            except JournalError as exc:
                errors.append(exc.message)
                continue
            if name == "From":
                lo = ms
            else:
                hi = ms
        return lo, hi, "; ".join(errors)

    def _render(self) -> None:
        snap = self.snapshot
        if snap is None:
            self.mode_text.setText("Operator records: opening the local journal…")
        elif snap.readable:
            self.mode_text.setText(
                f"Operator records: {len(snap.events)} position event(s), "
                f"{len(snap.decisions)} skip decision(s) · journal {snap.mode.value}"
                + (" — UNVERIFIED read-only view" if snap.mode is JournalMode.READ_ONLY else "")
            )
        else:
            self.mode_text.setText(f"Operator records unavailable — {snap.reason}")
        entries = self._operator + self._engine
        actions = sorted({e.action for e in entries})
        current = self.action.currentText()
        if [self.action.itemText(i) for i in range(1, self.action.count())] != actions:
            blocker = self.action.blockSignals(True)
            self.action.clear()
            self.action.addItem("All actions")
            self.action.addItems(actions)
            self.action.setCurrentText(current if current in actions else "All actions")
            self.action.blockSignals(blocker)
        lo, hi, error = self._bounds()
        self.range_error.setText(error)
        action = self.action.currentText()
        side = self.side.currentText()
        matched = filter_entries(
            entries,
            stream=self.stream.currentText(),
            text=self.search.text(),
            action="" if action == "All actions" else action,
            side="" if side == "All sides" else side,
            from_ms=lo,
            to_ms=hi,
        )
        self.shown = matched[:JOURNAL_ROW_LIMIT]
        more = len(matched) - len(self.shown)
        self.count.setText(
            f"{len(self.shown)} shown of {len(matched)} matching ({len(entries)} total)"
            + (f" · {more} older matching rows: narrow the filters to see them" if more else "")
            if entries
            else "No journal events yet."
        )
        _fill(self.table, self.model, [(e.key, e.cells) for e in self.shown], self.selected_key)
        self._render_detail()

    def _on_select(self) -> None:
        self.selected_key = _selected_key(self.table)
        self._render_detail()

    def _render_detail(self) -> None:
        entry = next((e for e in self._operator + self._engine if e.key == self.selected_key), None)
        if entry is None:
            self.detail_text_label.setText(
                "Select a row to see the full record."
                if self.selected_key is None
                else f"{self.selected_key} is not in the current records."
            )
            return
        self.detail_text_label.setText("\n".join(entry.detail))
