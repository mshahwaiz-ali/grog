"""Manual-record coordinator on the GUI thread (D03).

Owns the journal owner thread and the single open form. Sequence for every form:

1. ask the replay owner to pause and wait for its acknowledgement (exact cursor);
2. read fresh engine eligibility for a signal form (``check_signal``) and open the form
   only if the signal is still READY and unclaimed in the latest journal snapshot;
3. on Confirm, re-read eligibility again and compare it with what the form showed
   (source, generation, cursor, state, blocked flag, immutable plan) — any change stops
   the on-plan save and only offers a separate, explicitly acknowledged OFF_PLAN form;
4. send the command (stable action ID) to the journal owner thread; show SAVED LOCALLY
   or NOT SAVED only from its result. Replay stays paused after the form closes.

It never touches SQLite or the replay session; all data arrive as detached values.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QWidget

from grog.desktop.form_dialog import ManualFormDialog
from grog.desktop.frames import ClockFacts, OverviewFrame, PauseAck, SignalCheck
from grog.desktop.journal_model import CommandResult, JournalMode, JournalSnapshot
from grog.desktop.loading import LoadRequest
from grog.desktop.manual_forms import (
    FormSpec,
    confirm_open_spec,
    entry_spec,
    exit_spec,
    modify_spec,
    off_plan_spec,
    skip_spec,
)
from grog.journal.positions import JournalError, PositionState


@dataclass
class _Pending:
    purpose: str  # "open" | "save"
    kind: str
    target: str  # signal ID or position ID
    dialog: ManualFormDialog | None = None


class ManualController(QObject):
    """GUI-thread coordinator; ``window`` supplies pause/frames/generation."""

    snapshot_changed = Signal(object)  # JournalSnapshot
    busy_changed = Signal(bool)
    notice = Signal(str)
    journal_stopped = Signal()

    _open_to_owner = Signal(object, int)
    _reload_to_owner = Signal(int)
    _submit_to_owner = Signal(object)
    _shutdown_to_owner = Signal()
    _check_to_replay = Signal(int, int, str)
    _push_to_replay = Signal(str, object, object, str)

    def __init__(
        self,
        worker: QObject,
        replay_worker: QObject,
        *,
        parent_widget: QWidget,
        request_pause: Callable[[Callable[[PauseAck], None]], int],
        frame: Callable[[], OverviewFrame | None],
        generation: Callable[[], int],
    ) -> None:
        super().__init__(parent_widget)
        self._parent_widget = parent_widget
        self._request_pause = request_pause
        self._frame = frame
        self._generation = generation
        self.snapshot: JournalSnapshot | None = None
        self.dialog: ManualFormDialog | None = None
        self._opening = False
        self._token = 0
        self._pending: dict[int, _Pending] = {}
        self._inflight: dict[int, ManualFormDialog] = {}
        # action ID -> the exact eligibility a signal command was built with, so a retry
        # after an uncertain outcome rebuilds the identical payload (service idempotency).
        self._submitted_fresh: dict[str, SignalCheck | None] = {}
        self._journal_generation = 0
        self._source_id = ""
        self._stopping = False
        self.results: list[CommandResult] = []  # test evidence: every result received

        self.worker = worker
        self.thread = QThread(self)
        self.thread.setObjectName("gold-journal-owner")
        worker.moveToThread(self.thread)
        worker.snapshot.connect(self._on_snapshot)
        worker.result.connect(self._on_result)
        worker.stopped.connect(self._on_stopped)
        self._open_to_owner.connect(worker.open)
        self._reload_to_owner.connect(worker.reload)
        self._submit_to_owner.connect(worker.submit)
        self._shutdown_to_owner.connect(worker.shutdown)
        replay_worker.signal_checked.connect(self._on_check)
        self._check_to_replay.connect(replay_worker.check_signal)
        self._push_to_replay.connect(replay_worker.set_journal)
        self.thread.start()

    # ------------------------------------------------------------------ journal lifecycle

    def open_journal(self, request: LoadRequest, generation: int) -> None:
        self._journal_generation, self._source_id = generation, request.source_id
        self.snapshot = None
        self._open_to_owner.emit(request, generation)

    def forget_snapshot(self) -> None:
        """A new source generation started: records of the previous one are not shown."""
        self.snapshot = None
        self._journal_generation = -1

    def reload(self) -> None:
        self._reload_to_owner.emit(self._journal_generation)

    @Slot(object)
    def _on_snapshot(self, snap: JournalSnapshot) -> None:
        if snap.generation != self._journal_generation or snap.source_id != self._source_id:
            return  # an earlier source generation
        if self.snapshot is not None and snap.sequence <= self.snapshot.sequence:
            return
        self.snapshot = snap
        overlay = snap.overlay()
        positions = snap.open_positions() if snap.readable else None
        self._push_to_replay.emit(snap.source_id, overlay, positions, self.journal_note())
        self.snapshot_changed.emit(snap)

    def journal_note(self) -> str:
        s = self.snapshot
        if s is None:
            return "Opening the local journal…"
        restored = f" · {len(s.restored)} restored now" if s.restored else ""
        return f"Local journal {s.mode.value}{restored} · {s.reason}"

    @property
    def mode(self) -> JournalMode:
        return JournalMode.OPENING if self.snapshot is None else self.snapshot.mode

    @property
    def busy(self) -> bool:
        """A form is open/opening or a command is in flight: replay controls stay off."""
        return self.dialog is not None or self._opening or bool(self._inflight)

    def why_not_writable(self) -> str | None:
        if self._stopping:
            return "Grog is closing."
        s = self.snapshot
        if s is None:
            return "The local journal is still opening."
        if s.mode is JournalMode.READ_ONLY:
            return (
                "Local journal is READ ONLY — saved records are UNVERIFIED; nothing can be "
                "recorded."
            )
        if s.mode is JournalMode.UNAVAILABLE:
            return "Local journal unavailable — nothing can be recorded."
        if self.busy:
            return "Another manual form is open."
        return None

    # ------------------------------------------------------------------ opening forms

    def _set_opening(self, value: bool) -> None:
        self._opening = value
        self.busy_changed.emit(self.busy)

    def _start(self, kind: str, target: str) -> bool:
        why = self.why_not_writable()
        frame = self._frame()
        if why is None and not isinstance(frame, OverviewFrame):
            why = "No current replay frame."
        if why is not None:
            self.notice.emit(f"Nothing opened: {why}")
            return False
        self._set_opening(True)
        self._request_pause(lambda ack: self._after_pause(ack, kind, target))
        return True

    def open_signal_form(self, kind: str, signal_id: str) -> bool:
        return self._start(kind, signal_id)

    def open_position_form(self, kind: str, position_id: str) -> bool:
        return self._start(kind, position_id)

    def open_off_plan(self) -> bool:
        return self._start("offplan", "")

    def _after_pause(self, ack: PauseAck, kind: str, target: str) -> None:
        if self._stopping:
            self._set_opening(False)
            return
        if kind in ("entry", "skip"):
            self._token += 1
            self._pending[self._token] = _Pending("open", kind, target)
            self._check_to_replay.emit(self._token, ack.generation, target)
            return
        self._open_now(kind, target, None)

    def _clock(self) -> ClockFacts | None:
        f = self._frame()
        return f.clock if isinstance(f, OverviewFrame) else None

    def _open_now(self, kind: str, target: str, check: SignalCheck | None) -> None:
        snap = self.snapshot
        spec: FormSpec | None = None
        why = self.why_not_writable_for_open()
        gen, src = self._journal_generation, self._source_id
        if why is None and snap is not None:
            if kind in ("entry", "skip"):
                assert check is not None
                claim = (snap.overlay() or {}).get(target)
                if not check.ready:
                    why = f"signal {target} is {check.state} now ({check.reason or 'engine state'})"
                elif claim is not None:
                    why = f"signal {target} already {claim[0]} locally"
                else:
                    spec = (
                        entry_spec(check, snap.open_positions())
                        if kind == "entry"
                        else skip_spec(check)
                    )
            elif kind == "offplan":
                spec = off_plan_spec(src, gen, self._clock())
            else:
                pos = snap.position(target)
                if pos is None or not pos.is_open:
                    why = f"{target} is not an open recorded position"
                elif kind == "confirm" and pos.state is not PositionState.RECONCILIATION_REQUIRED:
                    why = f"{target} does not need reconciliation"
                elif kind in ("partial", "close"):
                    spec = exit_spec(
                        pos, self._clock(), close=kind == "close", source_id=src, generation=gen
                    )
                elif kind == "modify":
                    spec = modify_spec(pos, self._clock(), source_id=src, generation=gen)
                elif kind == "confirm":
                    spec = confirm_open_spec(pos, self._clock(), source_id=src, generation=gen)
        if spec is None:
            self._set_opening(False)
            self.notice.emit(f"Nothing opened: {why or 'not available'}. Replay stays paused.")
            return
        self.show_form(spec)

    def why_not_writable_for_open(self) -> str | None:
        s = self.snapshot
        if self._stopping:
            return "Grog is closing."
        if s is None or not s.writable:
            return "the local journal is not writable"
        return None

    def show_form(self, spec: FormSpec) -> ManualFormDialog:
        dialog = ManualFormDialog(spec, self._parent_widget)
        self.dialog = dialog
        self._opening = False
        dialog.confirmed.connect(lambda d=dialog: self._save(d))
        dialog.off_plan_requested.connect(lambda values, d=dialog: self._switch_off_plan(d, values))
        dialog.finished.connect(lambda _r, d=dialog: self._closed(d))
        self.busy_changed.emit(True)
        dialog.open()
        return dialog

    def _closed(self, dialog: ManualFormDialog) -> None:
        if self.dialog is dialog:
            self.dialog = None
        res = dialog.last_result
        if res is not None and res.saved:
            self.notice.emit(f"{res.message} Replay stays paused — resume when ready.")
        else:
            self.notice.emit("Form closed — nothing recorded. Replay stays paused.")
        self.busy_changed.emit(self.busy)
        dialog.deleteLater()

    def _switch_off_plan(self, dialog: ManualFormDialog, values: dict) -> None:
        """Changed signal: offer a NEW, separate OFF_PLAN form (new action ID)."""
        plan = dialog.spec.opened.plan if dialog.spec.opened else None
        prefill = {
            k: values[k]
            for k in ("price", "qty", "time", "stop", "target", "fees", "broker", "note")
            if k in values
        }
        if plan is not None:
            prefill["side"] = plan.side.value
            prefill["signal"] = plan.signal_id
        spec = off_plan_spec(
            self._source_id,
            self._journal_generation,
            self._clock(),
            prefill=prefill,
            reason="The READY signal changed or was claimed before saving. This is a separate "
            "OFF_PLAN record of your own external fill; review every field.",
        )
        dialog.state = dialog.EDITING
        dialog.done(0)  # nothing was saved on the on-plan form
        self._opening = True
        self.show_form(spec)

    # ------------------------------------------------------------------ saving

    def _save(self, dialog: ManualFormDialog) -> None:
        spec = dialog.spec
        why = self.why_not_writable_for_open()
        if why is not None:
            dialog.show_not_saved("NOT_WRITABLE", why)
            return
        if spec.opened is not None:  # signal form: fresh eligibility at SAVE time
            self._token += 1
            self._pending[self._token] = _Pending(
                "save", spec.kind.value, spec.signal_id or "", dialog
            )
            self._check_to_replay.emit(self._token, spec.opened.generation, spec.signal_id or "")
            return
        self._submit(dialog, None)

    def _not_submitted(self, dialog: ManualFormDialog) -> None:
        res = CommandResult(
            0,
            dialog.spec.kind,
            dialog.action_id,
            False,
            False,
            "SHUTTING_DOWN",
            "NOT SAVED — SHUTTING_DOWN: Grog closed before this record was submitted; "
            "nothing was written.",
            dialog.spec.position_id,
        )
        self.results.append(res)
        self.notice.emit(res.message)

    def _submit(self, dialog: ManualFormDialog, fresh: SignalCheck | None) -> None:
        spec = dialog.spec
        if self._stopping:
            self._not_submitted(dialog)
            return
        parsed = spec.parse(dialog.values())
        if parsed.errors:
            dialog.show_not_saved("INVALID_INPUT", "; ".join(parsed.errors.values()))
            return
        rejected = spec.rejections(parsed.values)  # the fresh values, not the button state
        if rejected:
            code, msg = rejected[0]
            dialog.show_not_saved(code, f"NOT SAVED — {code}: {msg}")
            return
        self._token += 1
        try:
            cmd = spec.build(self._token, dialog.action_id, parsed.values, fresh)
        except JournalError as exc:
            dialog.show_not_saved(exc.code, exc.message)
            return
        self._inflight[self._token] = dialog
        self._submitted_fresh[dialog.action_id] = fresh  # the latest payload sent
        self.busy_changed.emit(True)
        self._submit_to_owner.emit(cmd)

    @Slot(object)
    def _on_check(self, check: SignalCheck) -> None:
        pending = self._pending.pop(check.token, None)
        if pending is None:
            return
        if pending.purpose == "open":
            if check.generation != self._generation() or not check.found:
                self._set_opening(False)
                self.notice.emit(f"Nothing opened: {check.reason or 'signal not found'}.")
                return
            self._open_now(pending.kind, pending.target, check)
            return
        dialog = pending.dialog
        if dialog is None or dialog is not self.dialog:
            return
        opened = dialog.spec.opened
        snap = self.snapshot
        if dialog.action_id in self._submitted_fresh and _recorded(snap, dialog.action_id):
            # A retry after an uncertain outcome whose own action ID is already in the
            # journal: the service decides. The identical payload (same values, same
            # captured eligibility) is confirmed as already saved; any changed value is
            # rejected as DUPLICATE_ACTION_ID. Never reported as a foreign claim.
            self._submit(dialog, self._submitted_fresh[dialog.action_id])
            return
        claim = (snap.overlay() or {}).get(check.signal_id) if snap is not None else None
        problem = None
        if opened is None or not check.same_eligibility(opened):
            problem = _describe_change(opened, check)
        elif not check.ready:
            problem = f"the signal is {check.state} now"
        elif claim is not None:
            problem = f"the signal was already {claim[0]} locally"
        if problem is not None:
            dialog.show_not_saved(
                "SIGNAL_CHANGED",
                f"NOT SAVED — SIGNAL_CHANGED: {problem}; the on-plan record was not saved.",
                offer_off_plan=dialog.spec.offer_off_plan,
            )
            return
        self._submit(dialog, check)

    @Slot(object)
    def _on_result(self, res: CommandResult) -> None:
        self.results.append(res)
        dialog = self._inflight.pop(res.token, None)
        if dialog is not None:
            dialog.show_result(res)
            if res.code in ("SIGNAL_ALREADY_ENTERED", "SIGNAL_ALREADY_SKIPPED"):
                dialog.off_plan_button.setVisible(dialog.spec.offer_off_plan)
        self.notice.emit(res.message)
        self.busy_changed.emit(self.busy)

    # ------------------------------------------------------------------ shutdown

    def can_close(self) -> tuple[bool, str]:
        if self.dialog is not None or self._opening:
            return False, "Close the open manual form first (Cancel or finish saving)."
        return True, ""

    def oversight_count(self) -> int:
        s = self.snapshot
        return 0 if s is None else len(s.open_positions())

    def shutdown(self) -> None:
        """Queued after any in-flight command: it finishes (and reports) before closing."""
        if self._stopping:
            return
        self._stopping = True
        # A Save still waiting for its signal re-check was never submitted: record that
        # truthfully (nothing written) instead of letting it vanish with the window.
        for token, pending in list(self._pending.items()):
            if pending.purpose == "save" and pending.dialog is not None:
                del self._pending[token]
                self._not_submitted(pending.dialog)
        self._shutdown_to_owner.emit()

    @Slot()
    def _on_stopped(self) -> None:
        self.thread.quit()
        self.journal_stopped.emit()


def _recorded(snap: JournalSnapshot | None, action_id: str) -> bool:
    """True when the journal snapshot holds a durable record with this action ID."""
    if snap is None or not snap.readable:
        return False
    return any(e.event_id == action_id for e in snap.events) or any(
        d.decision_id == action_id for d in snap.decisions
    )


def _describe_change(opened: SignalCheck | None, now: SignalCheck) -> str:
    if opened is None:
        return "no eligibility was captured when the form opened"
    parts = []
    if (opened.source_id, opened.generation) != (now.source_id, now.generation):
        parts.append("the source changed")
    if opened.cursor != now.cursor:
        parts.append(f"the replay moved (cursor {opened.cursor} -> {now.cursor})")
    if not now.found:
        parts.append(now.reason or "the signal is no longer in the replay")
    elif opened.state != now.state:
        parts.append(f"state {opened.state} -> {now.state}")
    if now.found and opened.blocked != now.blocked:
        parts.append("EXECUTION BLOCKED changed" if now.blocked else "block was lifted")
    if now.found and opened.plan != now.plan:
        parts.append("the plan differs")
    return ", ".join(parts) or "eligibility changed"
