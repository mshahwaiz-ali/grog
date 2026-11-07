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

PREVIEW_LINES = 7  # fixed preview region height (lines); longer previews scroll inside

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
            box.setSpacing(2)
            box.addWidget(w)
            if f.hint:
                box.addWidget(label(f.hint, "meta", wrap=True))
            err = label("", "meta", wrap=True)
            set_tone(err, "error")
            err.setVisible(False)
            err.setAccessibleName(f"{f.label} error")
            box.addWidget(err)
            self.inputs[f.key], self.errors[f.key] = w, err
            form.addRow(label("" if f.kind == ACK else f.label, "meta"), box)
        fields_card.body.addLayout(form)
        column.addWidget(fields_card)

        self.preview_card = Card("Preview and safety checks (computed, nothing saved yet)")
        self.preview = label("", "body", wrap=True, select=True)
        self.preview.setAccessibleName("Preview")
        # D04: a FIXED-height preview region. The preview's length changes with every
        # keystroke/checkbox (e.g. an error line vs the full computed preview); letting
        # the card grow shrank the scrolling field area under the cursor and pushed the
        # control just clicked out of view (layout jump measured at 820x620, any scale).
        # Longer previews scroll inside this region instead.
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
        outer.addWidget(self.preview_card)  # always visible next to Confirm, never scrolled

        self.outcome = label("", "body", wrap=True, select=True)
        self.outcome.setAccessibleName("Save outcome")
        self.outcome.setVisible(False)
        outer.addWidget(self.outcome)
        self.discard_bar = QWidget()
        bar = QHBoxLayout(self.discard_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        self.discard_text = label(
            "You have unsaved input. Discard it? Nothing has been recorded.", "body", wrap=True
        )
        set_tone(self.discard_text, "warning")
        self.keep_button = QPushButton("Keep editing")
        self.discard_button = QPushButton("Discard input")
        self.keep_button.clicked.connect(self._keep_editing)
        self.discard_button.clicked.connect(self._discard)
        bar.addWidget(self.discard_text, 1)
        bar.addWidget(self.keep_button)
        bar.addWidget(self.discard_button)
        self.discard_bar.setVisible(False)
        outer.addWidget(self.discard_bar)

        buttons = QHBoxLayout()
        self.off_plan_button = QPushButton("Record as OFF_PLAN external fill…")
        self.off_plan_button.setToolTip(
            "Opens a separate OFF_PLAN form with a new action ID; nothing is converted "
            "automatically."
        )
        self.off_plan_button.setVisible(False)
        self.off_plan_button.clicked.connect(lambda: self.off_plan_requested.emit(self.values()))
        buttons.addWidget(self.off_plan_button)
        buttons.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.confirm_button = QPushButton(spec.confirm_label)
        self.confirm_button.setObjectName("primary")
        for b in (self.cancel_button, self.confirm_button, self.keep_button, self.discard_button):
            b.setAutoDefault(False)
            b.setDefault(False)
        self.cancel_button.setToolTip("Close without saving (Esc)")
        self.confirm_button.setToolTip("Save this local record after revalidation; no order")
        self.cancel_button.clicked.connect(self.request_cancel)
        self.confirm_button.clicked.connect(self._confirm)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.confirm_button)
        outer.addLayout(buttons)

        self._initial = self.values()
        self._render_preview()
        self.resize(760, 720)
        self.cancel_button.setFocus(Qt.FocusReason.OtherFocusReason)

    # ------------------------------------------------------------------ values

    def values(self) -> dict[str, str]:
        out = {}
        for key, w in self.inputs.items():
            if isinstance(w, QComboBox):
                out[key] = w.currentText()
            elif isinstance(w, QCheckBox):
                out[key] = "yes" if w.isChecked() else ""
            else:
                out[key] = w.text()
        return out

    @property
    def dirty(self) -> bool:
        return self.state != self.SAVED and self.values() != self._initial

    def _changed(self, *_args) -> None:
        self._esc_armed = False
        self.discard_bar.setVisible(False)
        if self.state == self.EDITING:
            self.outcome.setVisible(False)
        self._render_preview()

    def _render_preview(self) -> None:
        lines, errors = self.spec.render_preview(self.values())
        for key, err in self.errors.items():
            text = errors.get(key, "")
            # an untouched empty required field shows its rule only after a save attempt
            show = bool(text) and (self.saves_requested > 0 or self.values()[key] != "")
            err.setText(text)
            err.setVisible(show)
        self.preview.setText("\n".join(text for text, _tone in lines))
        # A domain warning (e.g. stop moved further away) is shown, never blocking; only an
        # input error or a structured rule rejection (spec.reject) disables Confirm.
        rejected = "_rejected" in errors or "_form" in errors
        set_tone(self.preview, "warning" if rejected else "neutral")
        self.preview_ok = not errors
        self.confirm_button.setEnabled(self.state == self.EDITING and self.preview_ok)
        self.confirm_button.setToolTip(
            "Save this local record after revalidation; no order"
            if self.preview_ok
            else "Fix the marked inputs first; nothing is saved"
        )

    # ------------------------------------------------------------------ save flow

    def _confirm(self) -> None:
        if self.state != self.EDITING:
            return  # duplicate clicks while saving/after saving are ignored
        self.saves_requested += 1
        self._render_preview()
        if not self.preview_ok:
            return
        self.state = self.SAVING
        for w in self.inputs.values():
            w.setEnabled(False)
        self.confirm_button.setEnabled(False)
        self.confirm_button.setText("Saving…")
        self.cancel_button.setEnabled(False)
        self.off_plan_button.setVisible(False)
        self._show_outcome("Saving locally — waiting for the journal transaction…", "info")
        self.confirmed.emit()

    def show_result(self, res: CommandResult) -> None:
        self.last_result = res
        if res.saved:
            self.state = self.SAVED
            self.confirm_button.setText("Saved")
            self.confirm_button.setEnabled(False)
            self.cancel_button.setText("Close")
            self.cancel_button.setEnabled(True)
            self.cancel_button.setFocus()
            self._show_outcome(f"{res.message}  [action {res.action_id}]", "ok")
            return
        self.show_not_saved(res.code, res.message)

    def show_not_saved(self, code: str, message: str, *, offer_off_plan: bool = False) -> None:
        """Keep every input and the action ID; the operator may fix and retry or cancel."""
        self.state = self.EDITING
        for w in self.inputs.values():
            w.setEnabled(True)
        self.confirm_button.setText(self.spec.confirm_label)
        self.cancel_button.setEnabled(True)
        text = (
            message
            if message.startswith(("NOT SAVED", "OUTCOME"))
            else (f"NOT SAVED — {code}: {message}")
        )
        nxt = " Fix the input and confirm again, or Cancel."
        if code in ("SIGNAL_CHANGED", "SIGNAL_ALREADY_ENTERED", "SIGNAL_ALREADY_SKIPPED"):
            nxt = (
                " This on-plan form can no longer be saved; Cancel, or record a real fill "
                "separately as OFF_PLAN."
            )
            self.confirm_button.setEnabled(False)
            self.preview_ok = False
        if code == "DUPLICATE_ACTION_ID":
            nxt = (
                " This form's action ID was already used for different data; Cancel and "
                "reopen the form."
            )
        self._show_outcome(text + nxt, "error")
        self.off_plan_button.setVisible(offer_off_plan)
        if code not in ("SIGNAL_CHANGED", "SIGNAL_ALREADY_ENTERED", "SIGNAL_ALREADY_SKIPPED"):
            self._render_preview()
        self.cancel_button.setFocus()

    def _show_outcome(self, text: str, tone: str) -> None:
        self.outcome.setText(text)
        set_tone(self.outcome, tone)
        self.outcome.setVisible(True)

    # ------------------------------------------------------------------ cancel / keys

    def request_cancel(self) -> None:
        if self.state == self.SAVING:
            self._show_outcome(
                "Saving is in progress — wait for SAVED LOCALLY or NOT SAVED.", "warning"
            )
            return
        if self.dirty:
            self.discard_bar.setVisible(True)
            self.keep_button.setFocus()
            return
        super().reject()

    def _keep_editing(self) -> None:
        self._esc_armed = False
        self.discard_bar.setVisible(False)
        self.cancel_button.setFocus()

    def _discard(self) -> None:
        if self.state != self.SAVING:
            super().reject()

    def reject(self) -> None:  # Esc (via QDialog) and programmatic rejects
        if self.state == self.SAVING:
            self.request_cancel()
            return
        if self.dirty and not self._esc_armed:
            self._esc_armed = True
            self.discard_bar.setVisible(True)
            self.discard_text.setText(
                "You have unsaved input. Press Esc again or choose Discard input to close "
                "without saving; nothing has been recorded."
            )
            return
        super().reject()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            focus = self.focusWidget()
            if isinstance(focus, QPushButton):
                if focus.isEnabled():
                    focus.animateClick()
            else:
                self.focusNextChild()  # Enter never submits or cancels from an input
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self.state == self.SAVING or (self.dirty and not self._esc_armed):
            event.ignore()
            self.reject()
            return
        super().closeEvent(event)
