"""Manual-journal modal forms (docs/02 §9). Local records only — never broker orders.

Every form:

* opens with **Cancel** focused (default selection) and shows a preview before saving;
* calls only a validated :class:`grog.journal.positions.PositionJournal` method through
  the ``submit`` callback, with one stable action ID per form instance (ST-05);
* on failure shows ``NOT SAVED — <reason>`` and stays open, so a DB error is never
  presented as success (ST-04);
* Esc with unsubmitted edits asks for a second Esc before discarding (docs/02 §3).

Typing into a field never triggers a global hotkey: the app disables its own bindings
while any modal is open and Textual inputs consume printable keys (docs/02 §3).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.markup import escape
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label

from grog.journal.positions import JournalError, new_action_id
from grog.ui.panels import Line
from grog.ui.widgets import TextPanel


@dataclass(frozen=True, slots=True)
class Field:
    key: str
    label: str
    default: str = ""
    placeholder: str = ""


Values = dict[str, str]
PreviewFn = Callable[[Values], Sequence[Line]]
SubmitFn = Callable[[str, Values], str]  # (action_id, values) -> success message


class JournalForm(ModalScreen[str | None]):
    """Generic confirm-before-save form for one local journal action."""

    BINDINGS = [Binding("escape", "escape_form", "Back")]

    def __init__(
        self,
        form_id: str,
        title: str,
        info: Sequence[Line],
        fields: Sequence[Field],
        preview: PreviewFn,
        submit: SubmitFn,
        confirm_label: str = "Confirm local record",
        warnings: Sequence[Line] = (),
    ) -> None:
        super().__init__(id=form_id)
        self.title_text = title
        self.info = list(info)
        self.warnings = list(warnings)
        self.fields = list(fields)
        self.preview_fn = preview
        self.submit_fn = submit
        self.confirm_label = confirm_label
        self.action_id = new_action_id()  # one per form instance (idempotent resubmits)
        self.saved = False
        self._esc_warned = False
        self.submissions = 0

    def compose(self) -> ComposeResult:
        """docs/02 §2.1 modal anatomy: identity -> plan/position -> fields -> risk preview
        & warnings -> actions (Cancel focused)."""
        with VerticalScroll(classes="modal form", id="form-box") as box:
            box.border_title = escape(self.title_text)
            yield TextPanel(id="form-identity")
            with Vertical(classes="section", id="sec-plan") as sec:
                sec.border_title = "PLAN / POSITION"
                yield TextPanel(id="form-info")
            with Vertical(classes="section", id="sec-fields") as sec:
                sec.border_title = "YOUR ACTUAL VALUES  (* required)"
                for f in self.fields:
                    with Horizontal(classes="form-row"):
                        yield Label(f.label, classes="form-label")
                        yield Input(value=f.default, placeholder=f.placeholder, id=f"f-{f.key}")
            with Vertical(classes="section", id="sec-preview") as sec:
                sec.border_title = "RISK PREVIEW & WARNINGS"
                yield TextPanel(id="form-warnings")
                yield TextPanel(id="form-preview")
                yield TextPanel(id="form-error")
            yield TextPanel(id="form-hint", classes="form-hint")
            with Horizontal(classes="form-buttons"):
                yield Button(self.confirm_label, id="confirm", variant="warning")
                yield Button("Cancel", id="cancel", variant="default")

    def on_mount(self) -> None:
        self.query_one("#form-identity", TextPanel).set_lines(self.info[:1])
        self.query_one("#form-info", TextPanel).set_lines(self.info[1:])
        self.query_one("#form-warnings", TextPanel).set_lines(self.warnings)
        self.query_one("#form-hint", TextPanel).set_lines(
            [
                [
                    (
                        "Tab next field · typing never triggers hotkeys · Esc cancels (twice if "
                        "edited) · LOCAL record only, nothing is sent to a broker",
                        "muted",
                    )
                ]
            ]
        )
        self._refresh_preview()
        # docs/02 §9: default selection Cancel; the dialog still opens at its top so the
        # identity section is read first on small terminals (docs/02 §2.1).
        self.query_one("#cancel", Button).focus(scroll_visible=False)

    # ------------------------------------------------------------------ state

    def values(self) -> Values:
        return {f.key: self.query_one(f"#f-{f.key}", Input).value for f in self.fields}

    @property
    def dirty(self) -> bool:
        vals = self.values()
        return any(vals[f.key] != f.default for f in self.fields)

    @property
    def preview_plain(self) -> str:
        return self.query_one("#form-preview", TextPanel).plain

    @property
    def error_plain(self) -> str:
        return self.query_one("#form-error", TextPanel).plain

    @property
    def plain(self) -> str:
        parts = [
            self.title_text,
            self.query_one("#form-identity", TextPanel).plain,
            self.query_one("#form-info", TextPanel).plain,
            self.query_one("#form-warnings", TextPanel).plain,
        ]
        parts += [f"{f.label} [{self.values()[f.key]}]" for f in self.fields]
        parts += [self.preview_plain, self.error_plain, f"[{self.confirm_label}] [Cancel]"]
        return "\n".join(parts)

    def _refresh_preview(self) -> None:
        try:
            lines = list(self.preview_fn(self.values()))
        except JournalError as exc:
            lines = [[(f"Preview unavailable: {exc.message}", "caution")]]
        self.query_one("#form-preview", TextPanel).set_lines(lines)

    def _error(self, text: str) -> None:
        self.query_one("#form-error", TextPanel).set_lines([[(text, "error")]] if text else [])

    # ------------------------------------------------------------------ events

    def on_input_changed(self, _event: Input.Changed) -> None:
        self._esc_warned = False
        self._error("")
        self._refresh_preview()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "cancel":
            self.action_escape_form()
        elif event.button.id == "confirm":
            self.confirm()

    def confirm(self) -> None:
        if self.saved:  # duplicate keypress after success: nothing more happens
            return
        self.submissions += 1
        try:
            message = self.submit_fn(self.action_id, self.values())
        except JournalError as exc:
            self._error(f"NOT SAVED — {exc.message}")
            return
        self.saved = True
        self.dismiss(message)

    def action_escape_form(self) -> None:
        if self.dirty and not self._esc_warned:
            self._esc_warned = True
            self._error("Unsubmitted input — press Esc again to discard (nothing is saved).")
            return
        self.dismiss(None)


class PositionDetail(ModalScreen[str | None]):
    """Enter on a position: exact record, events and observations (view only). When the
    position is RECONCILIATION_REQUIRED it offers an explicit local confirmation that the
    operator verified it is still open at the broker exactly as recorded."""

    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(
        self,
        lines: Sequence[Line],
        confirm_open: Callable[[str], str] | None,
    ) -> None:
        super().__init__(id="position-detail")
        self.lines = list(lines)
        self.confirm_open_fn = confirm_open
        self.action_id = new_action_id()
        self.saved = False

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal", id="detail-box") as box:
            box.border_title = (
                "POSITION DETAILS — RECONCILIATION REQUIRED"
                if self.confirm_open_fn is not None
                else "POSITION DETAILS — local record"
            )
            yield TextPanel(id="detail-body")
            if self.confirm_open_fn is not None:
                with Vertical(classes="section", id="sec-reconcile") as sec:
                    sec.border_title = "RECONCILIATION"
                    yield TextPanel(id="reconcile-text")
            yield TextPanel(id="form-error")
            with Horizontal(classes="form-buttons"):
                if self.confirm_open_fn is not None:
                    yield Button(
                        "Confirm still open as recorded", id="confirm-open", variant="warning"
                    )
                yield Button("Back", id="back", variant="default")

    def on_mount(self) -> None:
        self.query_one("#detail-body", TextPanel).set_lines(self.lines)
        if self.confirm_open_fn is not None:
            self.query_one("#reconcile-text", TextPanel).set_lines(
                [
                    [
                        (
                            "Confirm records a local verification only. [Back] is the default.",
                            "muted",
                        )
                    ],
                ]
            )
        self.query_one("#back", Button).focus()

    @property
    def plain(self) -> str:
        return self.query_one("#detail-body", TextPanel).plain

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "back":
            self.dismiss(None)
        elif event.button.id == "confirm-open" and self.confirm_open_fn and not self.saved:
            try:
                msg = self.confirm_open_fn(self.action_id)
            except JournalError as exc:
                self.query_one("#form-error", TextPanel).set_lines(
                    [[(f"NOT SAVED — {exc.message}", "error")]]
                )
                return
            self.saved = True
            self.dismiss(msg)

    def action_back(self) -> None:
        self.dismiss(None)
