"""D05 startup source chooser (Qt). Shown by the launcher when no explicit or saved
source is usable: "NO DATA LOADED" (docs/02 §16.9). It inspects state directories
read-only, lists their imported sources with origin labels and spells out the existing
CLI import; it never imports, downloads, creates or copies a database, and opens no
prices until the operator picks a source and presses Open."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from grog.desktop import theme
from grog.desktop.source_select import (
    Selection,
    StateInfo,
    default_config,
    import_guidance,
    inspect_state,
    selection_path,
    write_selection,
)
from grog.desktop.theme import SPACE, Card, label, set_tone
from grog.settings import parse_utc_timestamp_ms

COLUMNS = ("Source ID", "Origin", "Symbol", "Batches", "Quotes", "First UTC", "Last UTC")


class SourceChooser(QDialog):
    """Modal chooser; ``selection`` is set only when the operator presses Open."""

    def __init__(
        self,
        reason: str,
        *,
        state_dir: str = "",
        config: str = "",
        env: Mapping[str, str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.env = env
        self.selection: Selection | None = None
        self.saved_to: str | None = None
        self.info: StateInfo | None = None
        self.setObjectName("chooser")
        self.setWindowTitle("Gold — choose a local source")
        self.setStyleSheet(theme.STYLESHEET + f"QDialog#chooser {{ background: {theme.BG}; }}")
        self.setMinimumWidth(640)
        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE[4], SPACE[3], SPACE[4], SPACE[3])
        root.setSpacing(SPACE[2])
        # Everything but the buttons scrolls, so small windows never squeeze text/inputs.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        outer = QVBoxLayout(body)
        outer.setContentsMargins(0, 0, SPACE[1], 0)
        outer.setSpacing(SPACE[2])
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        title = label("NO DATA LOADED — select or import an existing source", "cardTitle")
        title.setWordWrap(True)
        set_tone(title, "warning")
        outer.addWidget(title)
        self.title = title
        self.reason = label(reason, "meta", wrap=True, select=True)
        outer.addWidget(self.reason)

        where = Card("Local state directory (read-only inspection)")
        form = QFormLayout()
        self.state_edit = QLineEdit(state_dir)
        self.state_edit.setPlaceholderText("blank = default local state ($XDG_DATA_HOME/grog)")
        self.state_edit.setAccessibleName("State directory")
        browse = QPushButton("Browse…")
        browse.setAutoDefault(False)
        browse.clicked.connect(self._browse_state)
        self.inspect_button = QPushButton("Inspect")
        self.inspect_button.setAutoDefault(False)
        self.inspect_button.clicked.connect(self.inspect)
        line = QHBoxLayout()
        line.addWidget(self.state_edit, 1)
        line.addWidget(browse)
        line.addWidget(self.inspect_button)
        form.addRow(label("State directory", "meta"), line)
        self.config_edit = QLineEdit(config)
        cfg = default_config(env)
        self.config_edit.setPlaceholderText(f"blank = {cfg} if present, else built-in defaults")
        self.config_edit.setAccessibleName("Replay configuration TOML")
        form.addRow(label("Config (optional)", "meta"), self.config_edit)
        self.from_edit = QLineEdit()
        self.from_edit.setPlaceholderText(
            "optional visible window start, e.g. 2026-10-14T00:00:00Z"
        )
        self.from_edit.setAccessibleName("Replay window start UTC")
        form.addRow(label("From UTC (optional)", "meta"), self.from_edit)
        where.body.addLayout(form)
        self.state_note = label("", "meta", wrap=True, select=True)
        where.body.addWidget(self.state_note)
        outer.addWidget(where)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAccessibleName("Imported sources")
        self.table.setMinimumHeight(4 * self.table.verticalHeader().defaultSectionSize() + 8)
        self.table.itemSelectionChanged.connect(self._sync)
        outer.addWidget(self.table)
        self.caution = label("", "body", wrap=True)
        outer.addWidget(self.caution)

        guide = Card("Import guidance (existing CLI; nothing runs automatically)")
        self.guidance = label("", "mono", wrap=True, select=True)
        guide.body.addWidget(self.guidance)
        outer.addWidget(guide)

        self.remember = QCheckBox("Remember this source for the launcher")
        self.remember.setChecked(True)
        outer.addWidget(self.remember)
        saved_note = f"Saved only to {selection_path(env)}"
        outer.addWidget(label(saved_note, "meta", wrap=True, select=True))
        outer.addWidget(
            label(
                "Opening replays stored quotes offline (SIMULATED). No feed, MT5, Wine or "
                "broker is started; manual records stay local journal entries.",
                "meta",
                wrap=True,
            )
        )
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.quit_button = QPushButton("Quit")
        self.quit_button.setAutoDefault(False)
        self.quit_button.clicked.connect(self.reject)
        self.open_button = QPushButton("Open source")
        self.open_button.setObjectName("primary")
        self.open_button.setAutoDefault(False)
        self.open_button.clicked.connect(self._open)
        buttons.addWidget(self.quit_button)
        buttons.addWidget(self.open_button)
        root.addLayout(buttons)
        self.resize(900, 680)
        self.inspect()
        self.quit_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Return/Enter press the FOCUSED button only (every button is non-default, so a
        text field never opens or quits); in the state field Return re-inspects."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            focus = self.focusWidget()
            if isinstance(focus, QPushButton):
                if focus.isEnabled():
                    focus.click()
                event.accept()
                return
            if focus is self.state_edit:
                self.inspect_button.click()
            event.accept()  # other fields: nothing happens (no implicit default button)
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ actions

    def _browse_state(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose a Grog state directory")
        if path:
            self.state_edit.setText(path)
            self.inspect()

    def inspect(self) -> StateInfo:
        info = inspect_state(self.state_edit.text().strip() or None, self.env)
        self.info = info
        self.table.setRowCount(0)
        for s in info.sources:
            r = self.table.rowCount()
            self.table.insertRow(r)
            cells = (s.source_id, s.origin, s.symbol, str(s.batches), f"{s.quotes:,}",
                     s.first_utc or "UNKNOWN", s.last_utc or "UNKNOWN")  # fmt: skip
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, s.source_id)
                self.table.setItem(r, c, item)
        notes = [f"Database: {info.database or '—'}"]
        if info.problem:
            notes.append(f"NOT USABLE: {info.problem}")
        if info.temporary:
            notes.append(
                "TEMPORARY location (system temp directory): fine for demos, not durable; "
                "it is never copied into your permanent state."
            )
        self.state_note.setText(" · ".join(notes))
        set_tone(self.state_note, "warning" if (info.problem or info.temporary) else "neutral")
        self.guidance.setText(import_guidance(info.state_dir))
        self._sync()
        return info

    def selected_source(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)

    def _sync(self) -> None:
        sid = self.selected_source()
        info = self.info
        chosen = next((s for s in info.sources if s.source_id == sid), None) if info else None
        self.caution.setText(chosen.caution if chosen else "Select a source to open it.")
        set_tone(self.caution, "warning" if chosen and chosen.origin == "SYNTHETIC" else "neutral")
        self.open_button.setEnabled(chosen is not None)

    def _open(self) -> None:
        sid = self.selected_source()
        if sid is None or self.info is None:
            return
        config = self.config_edit.text().strip() or None
        from_ts = self.from_edit.text().strip() or None
        problem = None
        if config is not None:
            config = str(Path(config).expanduser().absolute())  # saved paths never cwd-relative
            if not Path(config).is_file():
                problem = f"Config file not found: {config}"
        if problem is None and from_ts is not None:
            try:
                parse_utc_timestamp_ms(from_ts, "From UTC")
            except ValueError as exc:
                problem = str(exc)
        selection = Selection(sid, self.info.state_dir, config, from_ts)
        if problem is None and self.remember.isChecked():
            try:
                self.saved_to = str(write_selection(selection, self.env))
            except OSError as exc:
                problem = f"Could not remember this source (nothing opened): {exc}"
        if problem is not None:
            self.caution.setText(problem)
            set_tone(self.caution, "error")
            return
        self.selection = selection
        self.accept()
