"""Manual-record dialog (D03): identity / immutable plan or position / fields / preview /
Cancel + Confirm local record (docs/02 §16.7).

Qt GUI thread only. The dialog never writes: Confirm emits ``confirmed`` and the
controller revalidates and hands the command to the journal owner thread. Safety:
Cancel is initially focused and never saves; Enter inside a field only moves to the next
field; Esc closes a clean form but an edited form needs a second Esc or an explicit
Discard; Confirm is disabled while saving and after a save; a failed save keeps every
input and the same action ID; success is shown only from the journal's result.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from grog.desktop import theme
from grog.desktop.journal_model import CommandResult
from grog.desktop.manual_forms import ACK, SIDE, FormSpec
from grog.desktop.theme import SPACE, Card, label, set_tone
from grog.journal.positions import new_action_id

PREVIEW_LINES = 4  # reduced from 7 so field scroll area can bring last field fully into view on 820x620

TONE = {"error": "error", "caution": "warning", "gold": "ready", "ok": "ok", "muted": "info"}


class ManualFormDialog(QDialog):
    confirmed = Signal()  # the operator asked to save the current inputs
    off_plan_requested = Signal(object)  # dict of current inputs for a separate OFF_PLAN form

    EDITING, SAVING, SAVED = "EDITING", "SAVING", "SAVED"

    def __init__(self, spec: FormSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.spec = spec
        self.action_id = new_action_id()  # created once; every retry reuses it
        self.state = self.EDITING
        self.saves_requested = 0
        self.last_result: CommandResult | None = None
        self._esc_armed = False
        self.setObjectName("manualForm")
        self.setWindowTitle(spec.title)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setStyleSheet(theme.STYLESHEET + f"QDialog#manualForm {{ background: {theme.BG}; }}")
        self.setMinimumWidth(640)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE[4], SPACE[3], SPACE[4], SPACE[3])
        outer.setSpacing(SPACE[2])
        title = label(spec.title, "cardTitle", wrap=True)
        outer.addWidget(title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, SPACE[1], 0)
        column.setSpacing(SPACE[2])
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        ident = Card("Identity")
        for text, tone in spec.identity:
            line = label(text, "body", wrap=True, select=True)
            set_tone(line, TONE.get(tone, "neutral"))
            ident.body.addWidget(line)
        for text, _tone in spec.context:
            line = label(text, "meta", wrap=True, select=True)
            ident.body.addWidget(line)
        column.addWidget(ident)
        if spec.warnings:
            warn = Card("Warnings")
            warn.set_accent("warning")
            for text, tone in spec.warnings:
                line = label(text, "body", wrap=True)
                set_tone(line, TONE.get(tone, "warning"))
                warn.body.addWidget(line)
            column.addWidget(warn)

        fields_card = Card("Your actual broker-side facts")
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(SPACE[1])
        self.inputs: dict[str, QWidget] = {}
        self.errors: dict[str, object] = {}
        for f in spec.fields:
            initial = spec.prefill.get(f.key, f.default)
            if f.kind == SIDE:
                w = QComboBox()
                w.addItems(["", "BUY", "SELL"])
                w.setPlaceholderText("Choose BUY or SELL")
                w.setCurrentText(initial)
                w.currentTextChanged.connect(self._changed)
            elif f.kind == ACK:
                w = QCheckBox(f.label.rstrip(" *"))
                w.setChecked(initial == "yes")
                w.toggled.connect(self._changed)
            else:
                w = QLineEdit(initial)
                w.setPlaceholderText(f.placeholder)
                w.textChanged.connect(self._changed)
            w.setAccessibleName(f.label)
            w.setObjectName(f"field_{f.key}")
            box = QVBoxLayout()
            box.addWidget(w)
            err = label("", "meta", wrap=True)
            err.setObjectName(f"error_{f.key}")
            set_tone(err, "error")
            box.addWidget(err)
            self.inputs[f.key] = w
            self.errors[f.key] = err
            form.addRow(label(f.label, "body"), box)
        fields_card.body.addLayout(form)
        column.addWidget(fields_card)

        self.preview_card = Card("Preview")
        self.preview = label("", "body", wrap=True, select=True)
        self.preview.setObjectName("preview")
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setObjectName("previewArea")
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview_scroll.setStyleSheet(
            "QScrollArea#previewArea, #previewArea > QWidget > QWidget { background: transparent; }"
        )
        self.preview_scroll.setWidget(self.preview)
        self.preview.ensurePolished()
        lines = self.preview.fontMetrics().lineSpacing()
        self.preview_scroll.setFixedHeight(lines * PREVIEW_LINES + SPACE[1])
        self.preview_card.body.addWidget(self.preview_scroll)
        column.addStretch()
        outer.addWidget(self.preview_card)

        self.outcome = label("", "body", wrap=True, select=True)
        self.outcome.setObjectName("outcome")
        outer.addWidget(self.outcome)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button = QPushButton("Confirm local record")
        self.confirm_button.setObjectName("confirm")
        self.confirm_button.setDefault(False)
        self.confirm_button.clicked.connect(self._confirm)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.confirm_button)
        outer.addLayout(buttons)

        self._refresh()

    def _changed(self) -> None:
        self._esc_armed = False
        self._refresh()

    def _refresh(self) -> None:
        values = {k: self._value(k) for k in self.inputs}
        for key, err in self.errors.items():
            err.setText("")
        lines = self.spec.preview(values)
        self.preview.setText("\n".join(t for t, _ in lines))
        self.confirm_button.setEnabled(self.state is self.EDITING)

    def _value(self, key: str) -> str:
        w = self.inputs[key]
        if isinstance(w, QCheckBox):
            return "yes" if w.isChecked() else ""
        if isinstance(w, QComboBox):
            return w.currentText()
        return w.text()

    def _confirm(self) -> None:
        if self.state is not self.EDITING:
            return
        self.saves_requested += 1
        self.confirmed.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self._esc_armed or not any(self._value(k) for k in self.inputs):
                self.reject()
            else:
                self._esc_armed = True
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.state is self.SAVING:
            event.ignore()
            return
        super().closeEvent(event)
