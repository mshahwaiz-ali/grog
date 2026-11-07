"""Signals page (D02): Developing, READY / execution-blocked and History, read-only.

Qt GUI thread only. Renders the detached :class:`SignalsFacts` of each applied frame.
Search and filters act on the already-built rows and never reach the replay owner, so
they cannot alter market state. Rows are keyed by full IDs: the selection and its detail
survive replay updates, sorting and filtering, and a row that moves (READY -> History) or
leaves the snapshot is announced instead of being silently replaced. D03: Record entry /
Skip buttons emit ``action_requested``; whether they are enabled combines the engine's
eligibility with the window's gate (writable journal, no open form, current frame).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import (
    QEvent,
    QModelIndex,
    QObject,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from grog.desktop.presentation import view_time_text
from grog.desktop.signals_model import (
    CURRENT_COLUMNS,
    DEVELOPING_COLUMNS,
    HISTORY_COLUMNS,
    ActionFacts,
    DetailFacts,
    RowFacts,
    Section,
    SignalsFacts,
)
from grog.desktop.theme import SPACE, Card, label, set_tone

KEY_ROLE = Qt.ItemDataRole.UserRole + 1
TIME_ROLE = Qt.ItemDataRole.UserRole + 2  # sortable raw epoch ms, never localized display text
ALL_SIDES = "All sides"
ALL_STATES = "All states"
COLUMNS = {
    Section.DEVELOPING: DEVELOPING_COLUMNS,
    Section.CURRENT: CURRENT_COLUMNS,
    Section.HISTORY: HISTORY_COLUMNS,
}
# Compact, content-based column widths (sample text measured in the table font): no
# 130 px default for every column. Values longer than their column are elided in the
# middle with the exact text in the tooltip and the Selected detail; no column is removed.
_TIME = "2026-10-14 00:15:00.071 UTC"  # digits are measured as the font's widest digit
_ID = "SIG-6fbee…a7364bb1"
COLUMN_SAMPLES = {
    "Signal ID": _ID,
    "Candidate ID": _ID,
    "ID": _ID,
    "Side": "SELL",
    "Issued (UTC)": _TIME,
    "Expiry (UTC)": _TIME,
    "Detected (UTC)": _TIME,
    "Time (UTC)": _TIME,
    "Current state": "EXECUTION_BLOCKED",
    "Status": "EXECUTION_BLOCKED",
    "Event": "MISSED_PRICE_CHASE",
    "State / outcome": "MISSED_PRICE_CHASE · PRE-ROLL",
    "Entry": "ASK 4,053.79",
    "SL": "BID 4,052.43",
    "TP1": "BID 4,055.15",
    "TP2": "BID 4,056.51",
    "Band": "4053.70-4053.97",
    "Time left": "59m59s",
    "Fidelity": "SIMULATED",
    "Age": "59m59s",
    "Strategy": "v0.2-proposal",
    "Next confirmed M5 BID close": "BID ≥ 4,053.79 (M5 close)",
}
# Visual order of the READY table: the core plan (state, entry, SL, TPs, time left) comes
# first so it is visible at practical widths; the model keeps its canonical column order.
CURRENT_VISUAL_ORDER = (
    "Signal ID",
    "Side",
    "Current state",
    "Entry",
    "SL",
    "TP1",
    "TP2",
    "Time left",
    "Band",
    "Expiry (UTC)",
    "Issued (UTC)",
    "Fidelity",
)
assert sorted(CURRENT_VISUAL_ORDER) == sorted(CURRENT_COLUMNS)
CORE_COLUMNS = CURRENT_VISUAL_ORDER[:8]  # through "Time left"
DETAIL_MIN, DETAIL_MAX = 380, 560
MORE_COLUMNS = (
    "More columns to the right — scroll the table sideways (Shift+wheel) or widen the window. "
    "Every value is also shown exactly in Selected detail."
)
EMPTY = {
    Section.DEVELOPING: "No developing setups.",
    Section.CURRENT: "No READY or execution-blocked signal — NO TRADE.",
    Section.HISTORY: "No signal history yet.",
}


class _RowFilter(QSortFilterProxyModel):
    """Side/state/search filter over pre-built rows; never touches engine state."""

    def __init__(self, page: SignalsPage) -> None:
        super().__init__(page)
        self._page = page

    def filterAcceptsRow(self, source_row: int, parent: QModelIndex) -> bool:  # noqa: N802
        index = self.sourceModel().index(source_row, 0, parent)
        row = self._page.row_for(index.data(KEY_ROLE))
        return row is not None and self._page.accepts(row)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:  # noqa: N802
        """Chronological sort is always based on raw UTC ms, not localized labels."""
        earlier, later = left.data(TIME_ROLE), right.data(TIME_ROLE)
        if isinstance(earlier, int) and isinstance(later, int):
            return earlier < later if earlier != later else left.row() < right.row()
        return super().lessThan(left, right)


def longest_token_width(widget: QLabel) -> int:
    """Pixel width of the label's longest unbreakable word (it cannot wrap inside it)."""
    metrics = widget.fontMetrics()
    words = widget.text().split()
    return max((metrics.horizontalAdvance(w) for w in words), default=0) + 2


class _ResizeWatch(QObject):
    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Resize:
            self._callback()
        return False


class _FieldsBox(QWidget):
    """Holds the exact detail fields and pins its minimum height to the form's
    height-for-width at its real width.

    Root cause this fixes (proved by measurement): Qt's parent box layout kept using a
    stale height for this nested form when a value wrapped (e.g. a 609 px form needing
    618 px got 601 px), so multi-line exact values (entry band, config hash) were cropped
    or overlapped by the next row. An explicit minimum height re-propagates correctly.
    """

    def __init__(self, form: QFormLayout) -> None:
        super().__init__()
        self.setLayout(form)
        form.setContentsMargins(0, 0, 0, 0)

    def sync_height(self) -> None:
        """Pick name-beside-value only when the widest unbreakable token (a full hash or an
        exact Decimal) fits the value column, else name above value; then pin the height."""
        layout = self.layout()
        policy = self._wrap_policy()
        if layout.rowWrapPolicy() != policy:
            layout.setRowWrapPolicy(policy)
            layout.activate()
        height = layout.totalHeightForWidth(self.width()) if self.width() > 0 else 0
        height = max(height, layout.totalMinimumSize().height())
        if height != self.minimumHeight():
            self.setMinimumHeight(height)

    def _wrap_policy(self) -> QFormLayout.RowWrapPolicy:
        layout = self.layout()
        names, tokens = 0, 0
        for row in range(layout.rowCount()):
            name = layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
            value = layout.itemAt(row, QFormLayout.ItemRole.FieldRole)
            if name is None or value is None:
                continue
            names = max(names, name.widget().sizeHint().width())
            tokens = max(tokens, longest_token_width(value.widget()))
        room = self.width() - names - layout.horizontalSpacing()
        return (
            QFormLayout.RowWrapPolicy.DontWrapRows
            if room >= tokens
            else QFormLayout.RowWrapPolicy.WrapAllRows
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.sync_height()
        QTimer.singleShot(0, self.sync_height)  # again once wrapped children have settled


def _read_only_gate(action: ActionFacts) -> tuple[bool, str]:
    return False, "Local journal not connected — read-only."


class SignalsPage(QWidget):
    action_requested = Signal(str, str)  # (entry | skip, full signal ID)

    def __init__(self) -> None:
        super().__init__()
        self._gate: Callable[[ActionFacts], tuple[bool, str]] = _read_only_gate
        self.time_zone = "PKT"
        self.facts: SignalsFacts | None = None
        self.selected_key: str | None = None
        self.selected_section: Section | None = None
        self._rows: dict[str, RowFacts] = {}
        self._shown_detail: DetailFacts | None = None
        # Selection notices: a sticky lifecycle notice (moved / promoted / vanished / stale,
        # kept until the operator selects another row or it is resolved) plus a filter notice
        # recomputed on every refilter/frame, so it disappears as soon as the row is visible.
        self._event_kind: str | None = None
        self._event_text = ""
        self._filter_text = ""
        self.models: dict[Section, QStandardItemModel] = {}
        self.proxies: dict[Section, _RowFilter] = {}
        self.tables: dict[Section, QTableView] = {}
        self._keys: dict[Section, tuple[str, ...]] = {s: () for s in Section}
        self._cells: dict[Section, tuple[tuple[str, ...], ...]] = {s: () for s in Section}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE[4] + 4, SPACE[4], SPACE[4] + 4, SPACE[4])
        outer.setSpacing(SPACE[2])
        outer.addWidget(label("Signals", "pageTitle"))
        outer.addWidget(
            label(
                "Developing setups, READY proposals and their history. Read-only: search and "
                "filters never change the engine; no row is ranked or auto-selected.",
                "pagePurpose",
                wrap=True,
            )
        )
        self.section_summary = label(
            "No source evaluated — research-only; no broker orders.",
            "overviewSummary",
            wrap=True,
            select=True,
        )
        self.section_summary.setAccessibleName("Signal state counts and safety")
        outer.addWidget(self.section_summary)
        self.journal_note = label("", "meta", wrap=True)
        outer.addWidget(self.journal_note)

        filters = QHBoxLayout()
        filters.setSpacing(SPACE[1])
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search full IDs, side, state, prices, reason codes…")
        self.search.setAccessibleName("Search signals")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refilter)
        self.side_filter = QComboBox()
        self.side_filter.setAccessibleName("Side filter")
        self.side_filter.addItems([ALL_SIDES, "BUY", "SELL"])
        self.side_filter.currentTextChanged.connect(self._refilter)
        self.state_filter = QComboBox()
        self.state_filter.setAccessibleName("State filter")
        self.state_filter.addItem(ALL_STATES)
        self.state_filter.currentTextChanged.connect(self._refilter)
        for combo in (self.side_filter, self.state_filter):  # long states never widen the page
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setMinimumContentsLength(10)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.side_filter)
        filters.addWidget(self.state_filter)
        outer.addLayout(filters)

        self.side_by_side = True
        self._columns_sized = False
        self._arranged_width: int | None = None
        self._overflow_watch = _ResizeWatch(self._update_overflow_hint)
        self.content = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.content.setSpacing(SPACE[3])
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        for section in Section:
            self.tabs.addTab(self._build_table(section), section.value)
        self.tabs.setMinimumHeight(240)
        self.tabs.currentChanged.connect(lambda _i: self._update_overflow_hint())
        self.more_columns = label(MORE_COLUMNS, "meta", wrap=True)
        self.more_columns.setAccessibleName("More columns hint")
        self.more_columns.setVisible(False)
        table_side = QVBoxLayout()
        table_side.setSpacing(SPACE[0])
        table_side.addWidget(self.tabs, 1)
        table_side.addWidget(self.more_columns)
        self.content.addLayout(table_side, 3)
        self.content.addWidget(self._build_detail(), 2)
        outer.addLayout(self.content, 1)
        self._update_tab_titles()

    def set_time_zone(self, zone: str) -> None:
        """Repaint visible dates only; keep keyed selection and source UTC unchanged."""
        if zone not in ("PKT", "UTC"):
            raise ValueError(f"Unsupported Signals display time zone: {zone!r}")
        if zone == self.time_zone:
            return
        self.time_zone = zone
        for section, model in self.models.items():
            model.setHorizontalHeaderLabels(
                [name.replace("(UTC)", f"({zone})") for name in COLUMNS[section]]
            )
        if self.facts is not None:
            for section in Section:
                self._set_rows(section, self.facts.rows(section), repaint=True)
            self._refilter()
        if self._shown_detail is not None:
            self._update_detail_times(self._shown_detail)

    def _display_cell(self, row: RowFacts, index: int) -> tuple[str, int | None]:
        """Use integer timestamps supplied by the engine owner, never parse raw text."""
        raw = row.cells[index]
        for column, when_ms in row.display_times:
            if column == index:
                return view_time_text(when_ms, self.time_zone), when_ms
        return raw, None

    def _paint_cell(self, item: QStandardItem, row: RowFacts, index: int) -> None:
        raw = row.cells[index]
        shown, when_ms = self._display_cell(row, index)
        if item.text() != shown:
            item.setText(shown)
        item.setToolTip(raw if when_ms is None else f"{shown}\nExact UTC: {raw}")
        item.setData(when_ms, TIME_ROLE)

    # ------------------------------------------------------------------ structure

    def _build_table(self, section: Section) -> QWidget:
        model = QStandardItemModel(0, len(COLUMNS[section]), self)
        model.setHorizontalHeaderLabels(
            [name.replace("(UTC)", f"({self.time_zone})") for name in COLUMNS[section]]
        )
        proxy = _RowFilter(self)
        proxy.setSourceModel(model)
        table = QTableView()
        table.setModel(proxy)
        table.setAccessibleName(f"{section.value} table")
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)
        table.sortByColumn(-1, Qt.SortOrder.AscendingOrder)  # engine order until a header click
        table.verticalHeader().setVisible(False)
        table.setWordWrap(False)
        table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # Only History's free-text Summary stretches; plan columns keep their compact widths.
        header.setStretchLastSection(section is Section.HISTORY)
        header.setMinimumSectionSize(48)
        if section is Section.CURRENT:
            for target, name in enumerate(CURRENT_VISUAL_ORDER):
                header.moveSection(header.visualIndex(CURRENT_COLUMNS.index(name)), target)
        table.viewport().installEventFilter(self._overflow_watch)
        header.sectionResized.connect(lambda *_a: self._update_overflow_hint())
        table.selectionModel().currentRowChanged.connect(
            lambda current, _prev, s=section: self._on_current(s, current)
        )
        self.models[section], self.proxies[section], self.tables[section] = model, proxy, table
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE[0])
        empty = label(EMPTY[section], "meta", wrap=True)
        empty.setContentsMargins(SPACE[2], SPACE[1], SPACE[2], 0)
        empty.setObjectName("meta")
        setattr(self, f"empty_{section.name.lower()}", empty)
        layout.addWidget(empty)
        layout.addWidget(table, 1)
        return box

    def size_columns(self) -> None:
        """Measure compact column widths in the fonts the tables really use (after the
        window style sheet has polished them): cells in the table font, titles in the bold
        header font; digits are measured as the font's widest digit."""
        for section, table in self.tables.items():
            table.ensurePolished()
            header = table.horizontalHeader()
            header.ensurePolished()
            cell, title = table.fontMetrics(), header.fontMetrics()
            widest = max("0123456789", key=cell.horizontalAdvance)
            digits = str.maketrans("0123456789", widest * 10)
            for i, name in enumerate(COLUMNS[section]):
                sample = COLUMN_SAMPLES.get(name, name).translate(digits)
                header.resizeSection(
                    i, max(cell.horizontalAdvance(sample) + 20, title.horizontalAdvance(name) + 28)
                )
        self._columns_sized = True
        self._arranged_width = None
        self._arrange()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._columns_sized:
            self.size_columns()

    def visible_columns(self, section: Section) -> list[str]:
        """Column names fully inside the table viewport, in visual order (for QA/tests)."""
        table = self.tables[section]
        header = table.horizontalHeader()
        width = table.viewport().width()
        names = []
        for visual in range(header.count()):
            logical = header.logicalIndex(visual)
            left = header.sectionViewportPosition(logical)
            if left >= 0 and left + header.sectionSize(logical) <= width:
                names.append(COLUMNS[section][logical])
        return names

    def _update_overflow_hint(self) -> None:
        if not hasattr(self, "more_columns"):
            return  # still building
        section = list(Section)[self.tabs.currentIndex()]
        table = self.tables[section]
        overflow = table.horizontalHeader().length() > table.viewport().width() + 1
        self.more_columns.setVisible(overflow)

    def _build_detail(self) -> QWidget:
        self.detail = Card("Selected detail")
        self.detail.setMinimumWidth(300)
        self.notice = label("", "meta", wrap=True)
        self.notice.setAccessibleName("Selection notice")
        set_tone(self.notice, "warning")
        self.notice.setVisible(False)
        self.detail_title = label(
            "Select a row to see its complete detail.", "cardTitle", wrap=True
        )
        self.detail_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail_status = label("", "body", wrap=True)
        self.detail_summary = label("", "body", wrap=True, select=True)
        self.detail_summary.setAccessibleName("Plain-language signal interpretation")
        self.detail_times = label("", "meta", wrap=True, select=True)
        self.detail_times.setAccessibleName("Display-zone event and lifecycle times")
        self.detail_evidence = label("EXACT PLAN & AUDIT EVIDENCE", "eyebrow")
        # QFormLayout (not QGridLayout): it gives every wrapped value its height-for-width, so
        # multi-line exact values (entry band, config hash) never overlap or crop.
        self.fields = QFormLayout()
        self.fields.setHorizontalSpacing(SPACE[2])
        self.fields.setVerticalSpacing(SPACE[0])
        self.fields.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.fields.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.fields.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        self.notes = label("", "body", wrap=True, select=True)
        self.lifecycle_title = label("ENGINE LIFECYCLE EVENTS", "eyebrow")
        self.lifecycle = label("", "mono", wrap=True, select=True)
        self.action_row = QHBoxLayout()
        self.action_row.setSpacing(SPACE[1])
        self.action_row.addStretch()
        self.action_buttons: list[QPushButton] = []
        self.action_reason = label("", "meta", wrap=True)
        for w in (
            self.notice,
            self.detail_title,
            self.detail_status,
            self.detail_summary,
            self.detail_times,
            self.detail_evidence,
        ):
            self.detail.body.addWidget(w)
        self.fields_box = _FieldsBox(self.fields)
        self.fields.setContentsMargins(0, 0, 0, 0)
        self.detail.body.addWidget(self.fields_box)
        for w in (self.notes, self.lifecycle_title, self.lifecycle):
            self.detail.body.addWidget(w)
        self.detail.body.addLayout(self.action_row)
        self.detail.body.addWidget(self.action_reason)
        self.detail.body.addStretch()
        self._render_detail(None)
        return self.detail

    def set_layout_mode(self, mode: str) -> None:
        """Window layout hint; the page arranges itself from its own width (`_arrange`)."""
        self._arrange()

    def core_width(self) -> int:
        """Width the READY table needs to show its core plan columns without scrolling."""
        header = self.tables[Section.CURRENT].horizontalHeader()
        return sum(header.sectionSize(CURRENT_COLUMNS.index(n)) for n in CORE_COLUMNS) + 24

    def detail_need(self) -> int:
        """Detail width that fits the longest unbreakable exact value (a full hash or an
        exact Decimal) on one line, and never less than DETAIL_MIN."""
        tokens = 0
        for row in range(self.fields.rowCount()):
            value = self.fields.itemAt(row, QFormLayout.ItemRole.FieldRole)
            if value is not None and value.widget() is not None:
                tokens = max(tokens, longest_token_width(value.widget()))
        margins = self.detail.body.contentsMargins()
        frame = 2 * self.detail.frameWidth() + 2
        return max(DETAIL_MIN, tokens + margins.left() + margins.right() + frame)

    def _arrange(self) -> None:
        """Table and detail side by side only when the table can still show the whole core
        plan (ID, side, state, entry, SL, TP1, TP2, time left) beside a detail wide enough for
        its longest exact value (`detail_need`, at least 380 px);
        otherwise a full-width table with the detail below it. Each field name sits above its
        value whenever a long exact value would not fit beside it (see `_FieldsBox`)."""
        margins = self.layout().contentsMargins()
        width = self.width() - margins.left() - margins.right()
        need = self.detail_need()
        spare = width - self.core_width() - self.content.spacing()
        side = spare >= need
        if side != self.side_by_side or self._arranged_width is None:
            self.side_by_side = side
            self.content.setDirection(
                QBoxLayout.Direction.LeftToRight if side else QBoxLayout.Direction.TopToBottom
            )
        # Beside the table the detail is wide enough for its longest exact value but never
        # takes the core plan columns' width.
        self.detail.setMinimumWidth(need if side else 0)
        self.detail.setMaximumWidth(max(need, min(DETAIL_MAX, spare)) if side else 16_777_215)
        self._arranged_width = width
        self.fields_box.sync_height()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._arrange()

    # ------------------------------------------------------------------ data

    def row_for(self, key: str | None) -> RowFacts | None:
        return None if key is None else self._rows.get(key)

    def accepts(self, row: RowFacts) -> bool:
        side = self.side_filter.currentText()
        if side != ALL_SIDES and row.side != side:
            return False
        state = self.state_filter.currentText()
        if state != ALL_STATES and row.state != state:
            return False
        needle = self.search.text().strip().lower()
        localized = " ".join(
            view_time_text(ms, self.time_zone) for _column, ms in row.display_times
        ).lower()
        return all(part in row.search or part in localized for part in needle.split())

    def show_unavailable(self, text: str) -> None:
        self.facts = None  # the next engine frame re-renders everything
        self.journal_note.setText(text)
        self.section_summary.setText("Signals unavailable — do not act on previous data.")
        set_tone(self.journal_note, "warning")
        if self.selected_key is not None:
            self._set_event_notice(
                "stale",
                f"{text}. Detail for {self.selected_key} is the last known state, not current.",
            )
            self._show_notice()

    def apply(self, facts: SignalsFacts) -> None:
        """Render a new frame's rows; selection and filters are preserved by full ID."""
        if facts == self.facts:
            return
        self.facts = facts
        self._rows = {r.key: r for s in Section for r in facts.rows(s)}
        self.section_summary.setText(
            f"{len(facts.developing)} developing · "
            f"{len(facts.current)} READY / execution-blocked · "
            f"{len(facts.history)} historical. No ranking or automatic selection."
        )
        self.journal_note.setText(
            "Operator overlay: read-only local journal snapshot. " + facts.note
            if facts.journal_ok
            else "Operator records unavailable — READY signals cannot be confirmed unclaimed. "
            + facts.note
        )
        set_tone(self.journal_note, "info" if facts.journal_ok else "warning")
        self._sync_state_choices()
        for section in Section:
            self._set_rows(section, facts.rows(section))
        self._update_tab_titles()
        self._follow_selection()

    def _sync_state_choices(self) -> None:
        states = sorted({r.state for r in self._rows.values()})
        current = self.state_filter.currentText()
        existing = [self.state_filter.itemText(i) for i in range(1, self.state_filter.count())]
        if existing == states:
            return
        self.state_filter.blockSignals(True)
        self.state_filter.clear()
        self.state_filter.addItem(ALL_STATES)
        self.state_filter.addItems(states)
        if current != ALL_STATES and current not in states:
            self.state_filter.addItem(current)  # never silently drop the operator's filter
        self.state_filter.setCurrentText(current)
        self.state_filter.blockSignals(False)

    def _set_rows(
        self, section: Section, rows: tuple[RowFacts, ...], *, repaint: bool = False
    ) -> None:
        keys = tuple(r.key for r in rows)
        cells = tuple(r.cells for r in rows)
        model, table = self.models[section], self.tables[section]
        if keys == self._keys[section]:
            if cells != self._cells[section] or repaint:
                for i, row in enumerate(rows):  # same keys: update in place, preserve selection
                    for j, _raw in enumerate(row.cells):
                        self._paint_cell(model.item(i, j), row, j)
                self._cells[section] = cells
            self.proxies[section].invalidate()
            return
        table.selectionModel().blockSignals(True)
        model.removeRows(0, model.rowCount())
        for row in rows:
            items = []
            for j, text in enumerate(row.cells):
                item = QStandardItem(text)
                self._paint_cell(item, row, j)
                item.setData(row.key, KEY_ROLE)
                items.append(item)
            model.appendRow(items)
        table.selectionModel().blockSignals(False)
        self._keys[section], self._cells[section] = keys, cells
        getattr(self, f"empty_{section.name.lower()}").setVisible(not rows)

    def _update_tab_titles(self) -> None:
        for i, section in enumerate(Section):
            total = len(self._keys[section])
            shown = self.proxies[section].rowCount()
            text = (
                f"{section.value} ({total})"
                if shown == total
                else (f"{section.value} ({shown} of {total})")
            )
            self.tabs.setTabText(i, text)

    def _refilter(self, *_args) -> None:
        for proxy in self.proxies.values():
            proxy.invalidate()
        self._update_tab_titles()
        self._follow_selection()

    # ------------------------------------------------------------------ selection

    def select_key(self, key: str) -> bool:
        """Select a row by full ID (keyboard/mouse equivalent); False when not shown."""
        row = self._rows.get(key)
        if row is None:
            return False
        self.tabs.setCurrentIndex(list(Section).index(row.section))
        self.selected_key, self.selected_section = key, row.section
        self._set_event_notice(None, "")
        self._reselect()
        self._follow_selection()
        return True

    def _on_current(self, section: Section, index: QModelIndex) -> None:
        if not index.isValid():
            return
        key = index.siblingAtColumn(0).data(KEY_ROLE)
        row = self._rows.get(key)
        if row is None or key == self.selected_key:
            return
        self.selected_key, self.selected_section = key, section
        self._set_event_notice(None, "")
        self._filter_text = ""
        self._show_notice()
        self._render_detail(row.detail)

    def _reselect(self) -> None:
        if self.selected_key is None or self.selected_section is None:
            return
        section = self.selected_section
        table, proxy = self.tables[section], self.proxies[section]
        for r in range(proxy.rowCount()):
            index = proxy.index(r, 0)
            if index.data(KEY_ROLE) == self.selected_key:
                table.selectionModel().blockSignals(True)
                table.setCurrentIndex(index)
                table.selectRow(r)
                table.selectionModel().blockSignals(False)
                return

    def _follow_selection(self) -> None:
        key = self.selected_key
        if key is None or self.facts is None:
            return
        row = self._rows.get(key)
        if row is None:
            promoted = next(
                (
                    r
                    for r in self.facts.current + self.facts.history
                    if r.kind == "SIGNAL" and r.candidate_id == key
                ),
                None,
            )
            if promoted is not None:
                self._set_event_notice(
                    "promoted",
                    f"Candidate {key} is no longer developing: it became signal "
                    f"{promoted.key} ({promoted.section.value}). Last known candidate "
                    "detail kept below.",
                )
            else:
                self._set_event_notice(
                    "vanished",
                    f"{key} is no longer in the engine snapshot. Last known detail kept "
                    "below (frozen, not current).",
                )
            self._filter_text = ""
            self._show_notice()
            return
        if row.section is not self.selected_section:
            previous = self.selected_section.value if self.selected_section else "?"
            self._set_event_notice(
                "moved",
                f"Selected {key} moved from {previous} to {row.section.value} — now "
                f"{row.state}. Detail kept; frozen plan unchanged.",
            )
            self.selected_section = row.section
        elif self._event_kind in ("vanished", "stale"):
            self._set_event_notice(None, "")  # the row is current again in this snapshot
        self._filter_text = (
            "" if self.accepts(row) else f"Selected {key} is hidden by the current search/filter."
        )
        self._show_notice()
        self._reselect()
        if row.detail != self._shown_detail:
            self._render_detail(row.detail)

    def _set_event_notice(self, kind: str | None, text: str) -> None:
        self._event_kind, self._event_text = kind, text

    def _show_notice(self) -> None:
        text = "\n".join(t for t in (self._event_text, self._filter_text) if t)
        self.notice.setText(text)
        self.notice.setVisible(bool(text))

    @property
    def notice_kind(self) -> str | None:
        return self._event_kind

    def _update_detail_times(self, detail: DetailFacts) -> None:
        self.detail_times.setText(
            " · ".join(
                f"{name}: {view_time_text(ms, self.time_zone)}" for name, ms in detail.time_fields
            )
        )

    def _render_detail(self, detail: DetailFacts | None) -> None:
        self._shown_detail = detail
        while self.fields.rowCount():
            # takeRow + deleteLater, never removeRow: removeRow deletes the label widgets
            # synchronously inside a frame update and intermittently segfaulted (proved on
            # 43e1fd9: test_selected_ready_moving_to_history..., 4 of 6 runs).
            taken = self.fields.takeRow(0)
            for item in (taken.labelItem, taken.fieldItem):
                widget = item.widget() if item is not None else None
                if widget is not None:
                    widget.hide()
                    widget.deleteLater()
        for button in self.action_buttons:
            button.deleteLater()
        self.action_buttons = []
        if detail is None:
            self.detail_title.setText("Select a row to see its complete detail.")
            self.detail_status.setText("")
            self.detail_summary.setText("")
            self.detail_times.setText("")
            self.detail_evidence.setVisible(False)
            self.notes.setText("")
            self.lifecycle_title.setVisible(False)
            self.lifecycle.setText("")
            self.action_reason.setText("")
            return
        self.detail_title.setText(detail.title)
        self.detail_status.setText(detail.status)
        self.detail_summary.setText(detail.summary)
        self._update_detail_times(detail)
        self.detail_evidence.setVisible(True)
        set_tone(self.detail_status, detail.tone)
        for name, value in detail.fields:
            key_label = label(name, "meta")
            value_label = label(value, "body", wrap=True, select=True)
            value_label.setAccessibleName(name)
            self.fields.addRow(key_label, value_label)
        self.fields.activate()
        self._arrange()  # a longer exact value may need a wider detail or stacking
        self.fields_box.sync_height()
        self.notes.setText("\n".join(detail.notes))
        self.lifecycle_title.setVisible(bool(detail.lifecycle))
        self.lifecycle.setText("\n".join(detail.lifecycle))
        for action in detail.actions:
            button = QPushButton(action.name)
            button.setProperty("action_kind", action.kind)
            button.setProperty("signal_id", action.signal_id)
            if action.kind:
                button.clicked.connect(
                    lambda _c=False, a=action: self.action_requested.emit(a.kind, a.signal_id)
                )
            self.action_row.insertWidget(self.action_row.count() - 1, button)
            self.action_buttons.append(button)
        self.refresh_actions()

    def set_action_gate(self, gate: Callable[[ActionFacts], tuple[bool, str]]) -> None:
        """D03: the window decides whether an eligible action can open a form now
        (writable journal, no open form, fresh frame); the engine decides eligibility."""
        self._gate = gate
        self.refresh_actions()

    def refresh_actions(self) -> None:
        detail = self._shown_detail
        if detail is None:
            return
        reasons = []
        for button, action in zip(self.action_buttons, detail.actions, strict=False):
            enabled, reason = action.enabled, action.reason
            if enabled:
                enabled, reason = self._gate(action)
            button.setEnabled(enabled)
            button.setToolTip(reason or f"{action.name}: opens a local-journal form")
            button.setAccessibleDescription(reason)
            if not enabled and reason and reason not in reasons:
                reasons.append(reason)
        self.action_reason.setText("Disabled: " + " ".join(reasons) if reasons else "")

    def detail_text(self) -> str:
        """Everything the detail panel currently shows, for tests and copy."""
        parts = [
            self.notice.text(),
            self.detail_title.text(),
            self.detail_status.text(),
            self.detail_summary.text(),
            self.detail_times.text(),
        ]
        for i in range(self.fields.count()):
            widget = self.fields.itemAt(i).widget()
            if isinstance(widget, QLabel):
                parts.append(widget.text())
        parts += [self.notes.text(), self.lifecycle.text(), self.action_reason.text()]
        return "\n".join(p for p in parts if p)
