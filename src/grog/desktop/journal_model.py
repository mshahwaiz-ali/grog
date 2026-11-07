"""Detached journal snapshots and manual-record commands for the desktop (no Qt).

The journal owner thread builds a :class:`JournalSnapshot` from the validated
``PositionJournal`` read methods and executes :class:`Command` objects through its write
methods only. Everything here is an immutable value that can cross a Qt queued
connection: no SQLite object, live mapping or mutable payload dictionary is shared.
Validation, plan classification, idempotency and the first operator claim stay in
``PositionJournal``; this module only routes a command to the matching method and turns
the outcome into a truthful SAVED LOCALLY / NOT SAVED result.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from grog.journal.positions import (
    DecisionRecord,
    EntryRequest,
    JournalError,
    ManualPosition,
    PlanRef,
    PositionEventRecord,
    PositionJournal,
    PositionState,
)


class JournalMode(StrEnum):
    OPENING = "OPENING"
    WRITABLE = "WRITABLE"  # Store.open + migrations/backup + restore_on_startup succeeded
    READ_ONLY = "READ_ONLY"  # saved records shown UNVERIFIED; no restore, no writes
    UNAVAILABLE = "UNAVAILABLE"  # records could not be read: nothing is assumed


@dataclass(frozen=True, slots=True)
class OperatorEvent:
    """One durable ``position_events`` row, detached (payload kept as canonical JSON)."""

    event_id: str
    position_id: str
    sequence: int
    action: str
    effective_ms: int
    recorded_ms: int
    qty: Decimal | None
    price: Decimal | None
    fees: Decimal | None
    payload_json: str

    @classmethod
    def of(cls, e: PositionEventRecord) -> OperatorEvent:
        return cls(
            e.event_id,
            e.position_id,
            e.sequence,
            e.action.value,
            e.effective_at_ms,
            e.recorded_at_ms,
            e.qty,
            e.price,
            e.fees,
            json.dumps(e.payload, sort_keys=True, separators=(",", ":")),
        )

    def payload(self) -> dict:
        """A fresh copy of the immutable payload (callers may not mutate shared state)."""
        return json.loads(self.payload_json)


@dataclass(frozen=True, slots=True)
class JournalSnapshot:
    generation: int
    sequence: int
    source_id: str
    mode: JournalMode
    reason: str  # why the journal is read-only/unavailable, or the restore summary
    positions: tuple[ManualPosition, ...]  # all, including CLOSED (entry order)
    events: tuple[OperatorEvent, ...]  # every operator position event (service order)
    decisions: tuple[DecisionRecord, ...]  # every USER_SKIPPED decision
    claims: tuple[tuple[str, str, str | None], ...]  # (signal_id, action, position_id)
    restored: tuple[str, ...] = ()  # position IDs marked RECONCILIATION_REQUIRED now

    @property
    def writable(self) -> bool:
        return self.mode is JournalMode.WRITABLE

    @property
    def readable(self) -> bool:
        return self.mode in (JournalMode.WRITABLE, JournalMode.READ_ONLY)

    def overlay(self) -> dict[str, tuple[str, str | None]] | None:
        """Fresh ``signal_actions`` mapping for this source, or ``None`` when unreadable."""
        if not self.readable:
            return None
        return {sid: (action, pid) for sid, action, pid in self.claims}

    def open_positions(self) -> list[ManualPosition]:
        return [p for p in self.positions if p.is_open]

    def position(self, position_id: str) -> ManualPosition | None:
        return next((p for p in self.positions if p.position_id == position_id), None)

    def events_for(self, position_id: str) -> tuple[OperatorEvent, ...]:
        return tuple(
            sorted(
                (e for e in self.events if e.position_id == position_id),
                key=lambda e: e.sequence,
            )
        )

    def needs_reconciliation(self) -> list[ManualPosition]:
        return [p for p in self.positions if p.state is PositionState.RECONCILIATION_REQUIRED]


def read_snapshot(
    journal: PositionJournal,
    *,
    generation: int,
    sequence: int,
    source_id: str,
    mode: JournalMode,
    reason: str,
    restored: tuple[str, ...] = (),
) -> JournalSnapshot:
    """Read everything through the service's own read methods (owner thread only), all
    inside ONE read transaction so another instance's commit can never fall between the
    reads (no position shown with an event list from a different moment)."""
    with _read_transaction(journal._conn):  # the service's own connection, this thread
        return _read_all(
            journal,
            generation=generation,
            sequence=sequence,
            source_id=source_id,
            mode=mode,
            reason=reason,
            restored=restored,
        )


@contextmanager
def _read_transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """Begin a deferred read transaction and end only that one. If the connection is
    already inside a transaction (a caller's write), join it and never end it: ending
    it here could roll back or commit someone else's mutation."""
    if conn.in_transaction:
        yield
        return
    conn.execute("BEGIN DEFERRED")
    try:
        yield
    finally:
        if conn.in_transaction:
            conn.execute("ROLLBACK")  # read-only: nothing of ours to keep


def _read_all(
    journal: PositionJournal,
    *,
    generation: int,
    sequence: int,
    source_id: str,
    mode: JournalMode,
    reason: str,
    restored: tuple[str, ...],
) -> JournalSnapshot:
    claims = journal.signal_actions(source_id)
    return JournalSnapshot(
        generation=generation,
        sequence=sequence,
        source_id=source_id,
        mode=mode,
        reason=reason,
        positions=tuple(journal.positions()),
        events=tuple(OperatorEvent.of(e) for e in journal.events()),
        decisions=tuple(journal.decisions()),
        claims=tuple(sorted((sid, a, pid) for sid, (a, pid) in claims.items())),
        restored=restored,
    )


# --------------------------------------------------------------------------- commands


class CommandKind(StrEnum):
    ENTRY = "ENTRY"  # on a READY signal (plan linked) or OFF_PLAN external fill
    SKIP = "SKIP"
    PARTIAL = "PARTIAL"
    CLOSE = "CLOSE"
    MODIFY = "MODIFY"
    CONFIRM_OPEN = "CONFIRM_OPEN"


@dataclass(frozen=True, slots=True)
class Command:
    """One operator-confirmed local record. ``action_id`` is created once per form and
    reused for every retry of the same payload (the service deduplicates it)."""

    kind: CommandKind
    token: int
    generation: int
    source_id: str
    action_id: str
    entry: EntryRequest | None = None
    plan: PlanRef | None = None  # skip
    position_id: str | None = None
    price: Decimal | None = None
    qty: Decimal | None = None
    time_ms: int | None = None  # fill / effective / skip time
    fees: Decimal | None = None
    new_stop: Decimal | None = None
    new_target: Decimal | None = None
    note: str | None = None
    expected_events: int | None = None  # position event count the form was built from


@dataclass(frozen=True, slots=True)
class CommandResult:
    token: int
    kind: CommandKind
    action_id: str
    saved: bool
    created: bool  # False on an idempotent retry of an already-saved identical record
    code: str  # "SAVED" or the stable JournalError code
    message: str
    position_id: str | None = None


def execute(journal: PositionJournal, cmd: Command) -> CommandResult:
    """Run one command through the validated service; never raises for a rejected record."""

    def ok(created: bool, position_id: str | None, message: str) -> CommandResult:
        note = "" if created else " (already saved earlier — same action ID, no new record)"
        return CommandResult(
            cmd.token,
            cmd.kind,
            cmd.action_id,
            True,
            created,
            "SAVED",
            message + note,
            position_id,
        )

    try:
        if cmd.position_id is not None and cmd.expected_events is not None:
            current = journal.get(cmd.position_id)
            retry = any(e.event_id == cmd.action_id for e in journal.events(cmd.position_id))
            if current is not None and current.events != cmd.expected_events and not retry:
                # Only a hint before the transaction; the service re-checks inside it.
                raise JournalError(
                    "POSITION_CHANGED",
                    f"{cmd.position_id} changed since this form opened (now {current.events} "
                    f"events, form showed {cmd.expected_events}); nothing was saved. Close "
                    "the form and reopen it to see the current position",
                )
        if cmd.kind is CommandKind.ENTRY:
            assert cmd.entry is not None
            pos, created = journal.record_entry(cmd.entry)
            what = f"{pos.position_id} {pos.side.value} {pos.plan_status.value}"
            return ok(created, pos.position_id, f"SAVED LOCALLY: {what}. No broker order sent.")
        if cmd.kind is CommandKind.SKIP:
            assert cmd.plan is not None and cmd.time_ms is not None
            rec, created = journal.record_skip(
                cmd.action_id, cmd.plan, effective_ms=cmd.time_ms, reason=cmd.note
            )
            return ok(created, None, f"SAVED LOCALLY: {rec.signal_id} USER_SKIPPED.")
        if cmd.kind in (CommandKind.PARTIAL, CommandKind.CLOSE):
            fn = journal.record_close if cmd.kind is CommandKind.CLOSE else journal.record_partial
            pos, created = fn(
                cmd.action_id,
                cmd.position_id,
                price=cmd.price,
                qty=cmd.qty,
                fill_ms=cmd.time_ms,
                fees=cmd.fees,
                note=cmd.note,
            )
            what = (
                "CLOSED"
                if cmd.kind is CommandKind.CLOSE
                else f"partial close, remaining {format(pos.remaining_qty.normalize(), 'f')}"
            )
            return ok(
                created,
                pos.position_id,
                f"SAVED LOCALLY: {pos.position_id} {what}. Broker position not touched.",
            )
        if cmd.kind is CommandKind.MODIFY:
            pos, created = journal.record_modify(
                cmd.action_id,
                cmd.position_id,
                effective_ms=cmd.time_ms,
                new_stop=cmd.new_stop,
                new_target=cmd.new_target,
                note=cmd.note,
            )
            return ok(
                created,
                pos.position_id,
                f"SAVED LOCALLY: {pos.position_id} modification. Broker position not touched.",
            )
        if cmd.kind is CommandKind.CONFIRM_OPEN:
            _check_confirm_chronology(journal, cmd)
            pos, created = journal.confirm_open(
                cmd.action_id, cmd.position_id, effective_ms=cmd.time_ms, note=cmd.note
            )
            return ok(
                created,
                pos.position_id,
                f"SAVED LOCALLY: {pos.position_id} verified open by you — MONITORING. "
                "No broker data was read.",
            )
        raise JournalError("UNSUPPORTED", f"unsupported command {cmd.kind}")
    except JournalError as exc:
        return CommandResult(
            cmd.token,
            cmd.kind,
            cmd.action_id,
            False,
            False,
            exc.code,
            f"NOT SAVED — {exc.code}: {exc.message}",
            cmd.position_id,
        )
    except Exception as exc:  # noqa: BLE001 - an unexpected fault is never reported as saved
        return CommandResult(
            cmd.token,
            cmd.kind,
            cmd.action_id,
            False,
            False,
            OUTCOME_UNKNOWN,
            f"OUTCOME UNKNOWN — {type(exc).__name__}: {exc}. The record may or may not have "
            "been committed. Retrying this same form is safe: it reuses the same action ID, "
            "so an already-saved record is never duplicated.",
            cmd.position_id,
        )


OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


def _check_confirm_chronology(journal: PositionJournal, cmd: Command) -> None:
    """Save-side rule on the journal owner (never trusting the form): a verification
    cannot be dated before the recorded fill. ``confirm_open`` does not check time, and the
    fill time of a position is immutable, so this read cannot go stale. An exact retry of
    an already-saved action is left to the service's idempotency check."""
    assert cmd.position_id is not None and cmd.time_ms is not None
    if any(e.event_id == cmd.action_id for e in journal.events(cmd.position_id)):
        return
    pos = journal.get(cmd.position_id)
    if pos is not None and cmd.time_ms < pos.entry_ms:
        raise JournalError(
            "TIME_BEFORE_ENTRY",
            "verification time is before the recorded fill time; nothing was saved",
        )
