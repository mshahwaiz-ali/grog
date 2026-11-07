"""Positions and Journal page facts (D03, no Qt import).

Built on the GUI thread from a detached :class:`JournalSnapshot` (durable operator
records) and the replay frame's :class:`MarkFacts` / :class:`EngineRow` (observations and
SIM ENGINE events reconstructed from the replay, never persisted). Operator journal rows
reuse the terminal's ``manual_journal_rows`` wording through a read-only shim over the
snapshot, so both front ends describe the same durable record identically. No trading
arithmetic is added: realized/R values come from the validated domain helpers.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from grog.desktop.frames import EngineRow, MarkFacts
from grog.desktop.journal_model import JournalMode, JournalSnapshot, OperatorEvent
from grog.desktop.presentation import price_text, utc_ms_text
from grog.journal.positions import (
    ManualPosition,
    PositionAction,
    PositionEventRecord,
    PositionState,
)
from grog.ui.format import DASH, UNKNOWN, r_long, r_short
from grog.ui.manual import PNL_UNKNOWN, _q, manual_journal_rows, signed
from grog.ui.panels import JOURNAL_COLUMNS, OPERATOR, SIM_ENGINE, entry_labels

# --------------------------------------------------------------------------- positions

OPEN, RECON, CLOSED, ALL = "Open", "Needs reconciliation", "Closed", "All"
POSITION_FILTERS = (OPEN, RECON, CLOSED, ALL)
POSITION_COLUMNS = (
    "Position",
    "Signal",
    "Side",
    "Remaining",
    "Entry",
    "Mark",
    "SL",
    "TP",
    "Gross R",
    "State",
    "Plan",
    "Last event UTC",
)


@dataclass(frozen=True, slots=True)
class PositionRow:
    key: str
    cells: tuple[str, ...]
    tone: str
    state: str
    is_open: bool


def _mark_for(pos: ManualPosition, marks: Sequence[MarkFacts]) -> MarkFacts | None:
    """Only facts computed from exactly this journal version of the position."""
    return next(
        (m for m in marks if m.position_id == pos.position_id and m.events == pos.events), None
    )


def state_text(pos: ManualPosition, mode: JournalMode) -> str:
    text = pos.state.value.replace("_", " ")
    if mode is JournalMode.READ_ONLY and pos.is_open:
        text += " · UNVERIFIED (read-only)"
    return text


def position_rows(
    snap: JournalSnapshot, marks: Sequence[MarkFacts], which: str
) -> tuple[PositionRow, ...]:
    out = []
    for p in reversed(snap.positions):  # newest entry first, stable by ID
        if which == OPEN and not p.is_open:
            continue
        if which == RECON and p.state is not PositionState.RECONCILIATION_REQUIRED:
            continue
        if which == CLOSED and p.is_open:
            continue
        m = _mark_for(p, marks) if p.is_open else None
        sig = p.linked_signal_id or DASH
        if p.plan_status.value == "OFF_PLAN" and not p.linked_signal_id:
            sig = "OFF_PLAN"
        if p.is_open:
            r = r_short(m.total_r) if m is not None and m.closeable is not None else DASH
            mark = DASH
            if m is not None and m.closeable is not None:
                mark = price_text(m.closeable) + ("" if m.freshness == "FRESH" else "*")
        else:
            r = r_short(p.realized_r) + " realized" if p.realized_r is not None else DASH
            mark = "closed"
        tone = (
            "error"
            if p.state is PositionState.RECONCILIATION_REQUIRED
            else "info"
            if not p.is_open
            else "neutral"
        )
        cells = (
            p.position_id,
            sig,
            p.side.value,
            f"{_q(p.remaining_qty)} / {_q(p.initial_qty)}",
            price_text(p.entry_price),
            mark,
            price_text(p.current_sl) + ("*" if p.current_sl != p.initial_sl else ""),
            price_text(p.current_tp),
            r,
            state_text(p, snap.mode),
            p.plan_status.value,
            utc_ms_text(p.last_event_ms),
        )
        out.append(PositionRow(p.position_id, cells, tone, p.state.value, p.is_open))
    return tuple(out)


def event_line(e: OperatorEvent) -> str:
    payload = e.payload()
    detail = ""
    if e.qty is not None:
        detail = f" · qty {_q(e.qty)} @ {price_text(e.price)}"
    if e.action == PositionAction.MODIFY.value:
        detail = (
            f" · SL {payload.get('new_stop') or 'unchanged'} · TP "
            f"{payload.get('new_target') or 'unchanged'}"
        )
    fees = ""
    if e.action in ("ENTRY", "PARTIAL_CLOSE", "CLOSE"):
        fees = f" · fees {e.fees if e.fees is not None else UNKNOWN}"
    note = payload.get("note") or payload.get("reason")
    tail = f" · note: {note}" if note else ""
    return (
        f"#{e.sequence} {e.action}{detail}{fees}{tail}\n"
        f"    event {utc_ms_text(e.effective_ms)} · recorded {utc_ms_text(e.recorded_ms)}"
        f" · ID {e.event_id}"
    )


def position_detail(
    snap: JournalSnapshot, pos: ManualPosition, marks: Sequence[MarkFacts]
) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    """(title, status, body lines, event lines) with the terminal's wording."""
    ent, ex = entry_labels(pos.side)
    m = _mark_for(pos, marks) if pos.is_open else None
    title = f"POSITION {pos.position_id} · {pos.side.value}"
    status = f"{state_text(pos, snap.mode)} · {pos.fidelity} {pos.mode} — local record"
    lines = [
        f"Signal: {pos.linked_signal_id or 'none'} ({pos.signal_link}) · Plan status: "
        f"{pos.plan_status.value} {', '.join(pos.off_plan_reasons)}".rstrip(),
        f"Fill {ent} {price_text(pos.entry_price)} at {utc_ms_text(pos.entry_ms)} (recorded "
        f"{utc_ms_text(pos.entry_recorded_ms)}) · qty {_q(pos.remaining_qty)} of "
        f"{_q(pos.initial_qty)}",
        f"SL {ex} initial {price_text(pos.initial_sl)} / current {price_text(pos.current_sl)}"
        f" · TP1 {price_text(pos.tp1)} · TP {ex} {price_text(pos.current_tp)} · initial risk "
        f"{price_text(pos.initial_risk) if pos.initial_risk else UNKNOWN}",
    ]
    if pos.plan is not None:
        pl = pos.plan
        lines.append(
            f"Original plan (unchanged): E0 {price_text(pl.e0)} · SL {price_text(pl.sl0)} · "
            f"TP2 {price_text(pl.tp2)} · risk {price_text(pl.original_risk)} · expires "
            f"{utc_ms_text(pl.expiry_ms)}"
        )
    if pos.is_open:
        if m is None:
            lines.append("Mark: waiting for the replay to observe this journal version.")
        else:
            if m.closeable is not None:
                lines.append(
                    f"Mark {m.closeable_side} {price_text(m.closeable)} at "
                    f"{utc_ms_text(m.quote_ms)} [{m.freshness}] · unrealized gross price x "
                    f"qty {signed(m.unrealized_units)}"
                )
            if m.reason:
                lines.append(m.reason)
            full = price_text(m.original_risk_units) if m.original_risk_units else UNKNOWN
            lines.append(
                f"R (gross): move/unit {r_long(m.move_r)} · realized {r_long(m.realized_r)} · "
                f"unrealized remaining {r_long(m.unrealized_r)} · total {r_long(m.total_r)}"
            )
            lines.append(
                f"Denominator: original full-position risk {full} price units · Net R: "
                f"UNKNOWN · Fees {pos.fees_text} · {PNL_UNKNOWN}"
            )
            touches = ", ".join(f"{k} first at {utc_ms_text(ms)}" for k, ms in m.touched)
            if touches:
                lines.append(f"Touches (observations only, NOT fills): {touches}")
            lines.append("Observations: " + (" | ".join(m.observations) or "none"))
    else:
        lines.append(
            f"Realized gross {r_long(pos.realized_r)} · Net R: UNKNOWN · Fees "
            f"{pos.fees_text} · {PNL_UNKNOWN}"
        )
    if pos.state is PositionState.RECONCILIATION_REQUIRED:
        lines.append(
            "RECONCILIATION REQUIRED — verify at your broker. If it is open exactly as "
            "recorded, use Confirm still open; otherwise record the partial/close/modification."
        )
    if snap.mode is JournalMode.READ_ONLY:
        lines.append(
            "READ ONLY journal: this record is UNVERIFIED; restart reconciliation "
            "was not performed and nothing can be recorded."
        )
    lines.append("No hold or exit advice. No automatic broker order is created.")
    events = tuple(event_line(e) for e in snap.events_for(pos.position_id))
    return title, status, tuple(lines), events


# --------------------------------------------------------------------------- journal

STREAM_ALL, STREAM_OPERATOR, STREAM_ENGINE = "Operator + SIM ENGINE", OPERATOR, SIM_ENGINE
STREAMS = (STREAM_ALL, STREAM_OPERATOR, STREAM_ENGINE)
JOURNAL_PAGE_COLUMNS = ("EVENT UTC", "RECORDED UTC", *JOURNAL_COLUMNS[1:])
OPERATOR_PROVENANCE = (
    "Operator-confirmed LOCAL journal record — durable in the local state database. "
    "Not a broker record."
)
ENGINE_PROVENANCE = (
    "SIM ENGINE event reconstructed from this replay session — SIMULATED, not persisted, "
    "not a trade; replaying the same source reproduces it."
)


@dataclass(frozen=True, slots=True)
class JournalEntry:
    key: str  # stable unique: pe-<event id> / sd-<decision id> / engine event ID
    producer: str  # OPERATOR | SIM ENGINE
    time_ms: int  # event (effective / decision) UTC
    recorded_ms: int | None  # durable recording time (operator rows only)
    order: tuple  # total, stable sort key (ties broken by recorded time and unique key)
    action: str
    side: str
    cells: tuple[str, ...]  # JOURNAL_PAGE_COLUMNS
    search: str
    detail: tuple[str, ...]

    def matches(self, text: str) -> bool:
        needle = text.strip().lower()
        if not needle:
            return True
        return any(needle in c.lower() for c in self.cells) or needle in self.search.lower()


class _SnapshotJournal:
    """Read-only shim exposing the three read methods ``manual_journal_rows`` uses."""

    def __init__(self, snap: JournalSnapshot) -> None:
        self._snap = snap

    def positions(self) -> list[ManualPosition]:
        return list(self._snap.positions)

    def events(self) -> list[PositionEventRecord]:
        return [
            PositionEventRecord(
                e.event_id,
                e.position_id,
                e.sequence,
                PositionAction(e.action),
                e.effective_ms,
                e.recorded_ms,
                e.qty,
                e.price,
                e.fees,
                e.payload(),
            )
            for e in self._snap.events
        ]

    def decisions(self):
        return list(self._snap.decisions)


def operator_entries(snap: JournalSnapshot | None) -> tuple[JournalEntry, ...]:
    if snap is None or not snap.readable:
        return ()
    events = {f"pe-{e.event_id}": e for e in snap.events}
    decisions = {f"sd-{d.decision_id}": d for d in snap.decisions}
    out = []
    for time_ms, row in manual_journal_rows(_SnapshotJournal(snap)):  # type: ignore[arg-type]
        e = events.get(row.key)
        d = decisions.get(row.key)
        recorded = e.recorded_ms if e is not None else d.recorded_at_ms if d is not None else None
        detail = [
            f"{name}: {value}" for name, value in zip(JOURNAL_COLUMNS, row.cells, strict=True)
        ]
        detail[0] = f"EVENT UTC: {utc_ms_text(time_ms)}"
        detail.insert(1, f"RECORDED UTC: {utc_ms_text(recorded)}")
        if e is not None:
            detail.append(f"Event ID: {e.event_id} · position {e.position_id} · seq {e.sequence}")
            detail.append(f"Exact payload: {_wrappable_payload(e.payload_json)}")
        if d is not None:
            detail.append(
                f"Decision ID: {d.decision_id} · signal {d.signal_id} · source {d.source_id}"
            )
        detail.append(f"Full refs: {row.search.strip()}")
        detail.append(OPERATOR_PROVENANCE)
        cells = (utc_ms_text(time_ms), utc_ms_text(recorded), *row.cells[1:])
        out.append(
            JournalEntry(
                key=row.key,
                producer=OPERATOR,
                time_ms=time_ms,
                recorded_ms=recorded,
                order=(
                    time_ms,
                    recorded or 0,
                    1,
                    e.position_id if e else "",
                    e.sequence if e else 0,
                    row.key,
                ),
                action=row.cells[2],
                side=row.cells[4],
                cells=cells,
                search=row.search + " " + (e.payload_json if e else ""),
                detail=tuple(detail),
            )
        )
    return tuple(out)


def engine_entries(rows: Sequence[EngineRow]) -> tuple[JournalEntry, ...]:
    out = []
    for i, r in enumerate(rows):
        detail = [f"{name}: {value}" for name, value in zip(JOURNAL_COLUMNS, r.cells, strict=True)]
        detail[0] = f"EVENT UTC (decision/receipt): {utc_ms_text(r.time_ms)}"
        detail.insert(1, f"Event time (provider/bar/expiry): {utc_ms_text(r.event_ms)}")
        detail.insert(2, "RECORDED UTC: — (not persisted; reconstructed from the replay)")
        detail.append(f"Engine event ID: {r.key} · full ref {r.ref}")
        detail.append(ENGINE_PROVENANCE)
        out.append(
            JournalEntry(
                key=r.key,
                producer=SIM_ENGINE,
                time_ms=r.time_ms,
                recorded_ms=None,
                order=(r.time_ms, 0, 0, "", i, r.key),
                action=r.kind,
                side=r.side,
                cells=(utc_ms_text(r.time_ms), DASH, *r.cells[1:]),
                search=f"{r.search} {r.ref}",
                detail=tuple(detail),
            )
        )
    return tuple(out)


def filter_entries(
    entries: Sequence[JournalEntry],
    *,
    stream: str = STREAM_ALL,
    text: str = "",
    action: str = "",
    side: str = "",
    from_ms: int | None = None,
    to_ms: int | None = None,
) -> list[JournalEntry]:
    """Newest first with a total, stable order (equal milliseconds never drop or swap)."""
    out = [
        e
        for e in entries
        if (stream == STREAM_ALL or e.producer == stream)
        and (not action or e.action == action)
        and (not side or e.side == side)
        and (from_ms is None or e.time_ms >= from_ms)
        and (to_ms is None or e.time_ms <= to_ms)
        and e.matches(text)
    ]
    out.sort(key=lambda e: e.order, reverse=True)
    return out


def _wrappable_payload(payload_json: str) -> str:
    """The stored payload, value-for-value (strings stay quoted exact decimals), with
    spaces between members so a long record wraps instead of widening the page."""
    try:
        data = json.loads(payload_json)
    except ValueError:
        return payload_json
    if not isinstance(data, dict):
        return payload_json
    return "{" + ", ".join(f"{json.dumps(k)}: {json.dumps(v)}" for k, v in data.items()) + "}"
