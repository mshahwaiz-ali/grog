"""Pure, detached Signals read model for the native desktop (D02, no Qt).

Built on the replay owner thread from one engine snapshot, the engine's ordered signal
events and the read-only operator overlay. Every value is copied into frozen tuples of
strings, so the Qt page only filters, sorts and renders. No trading arithmetic beyond the
existing shared presenters, no ranking, no journal writes. Rows are keyed by full
candidate/signal/event IDs so a selection survives replay updates and section moves.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from grog.desktop.overview_model import human_condition
from grog.desktop.presentation import UNAVAILABLE, price_text, utc_ms_text
from grog.domain.enums import Side, SignalEventKind, SignalState
from grog.ui.format import duration
from grog.ui.lanes import exposure, signal_lane
from grog.ui.panels import band_text, candidate_condition, entry_labels

if TYPE_CHECKING:
    from grog.domain.models import S1Candidate, SignalEvent
    from grog.journal.positions import ManualPosition
    from grog.replay.session import SignalView, Snapshot

NO_EVENT_RECORD = (
    "No signal was issued, so no SignalRecord exists; this row is the engine event itself."
)
UNCONFIRMED = "Operator records unavailable — this READY cannot be confirmed unclaimed."


class Section(StrEnum):
    DEVELOPING = "Developing"
    CURRENT = "READY / execution-blocked"
    HISTORY = "History"


DEVELOPING_COLUMNS = (
    "Candidate ID",
    "Side",
    "Strategy",
    "Status",
    "Next confirmed M5 BID close",
    "Detected (UTC)",
    "Age",
)
CURRENT_COLUMNS = (
    "Signal ID",
    "Side",
    "Issued (UTC)",
    "Current state",
    "Entry",
    "Band",
    "SL",
    "TP1",
    "TP2",
    "Expiry (UTC)",
    "Time left",
    "Fidelity",
)
HISTORY_COLUMNS = ("ID", "Event", "Side", "Time (UTC)", "State / outcome", "Summary")


@dataclass(frozen=True, slots=True)
class ActionFacts:
    name: str
    enabled: bool  # engine/overlay eligibility only; the GUI also needs a writable journal
    reason: str
    kind: str = ""  # "entry" | "skip" (D03 manual forms) or "" (informational only)
    signal_id: str = ""


@dataclass(frozen=True, slots=True)
class DetailFacts:
    title: str
    status: str
    tone: str  # neutral | ready | warning | error (presentation only)
    fields: tuple[tuple[str, str], ...]  # exact label/value pairs
    notes: tuple[str, ...]
    lifecycle: tuple[str, ...]
    actions: tuple[ActionFacts, ...]
    summary: str = ""  # UI-only human overview, never eligibility
    time_fields: tuple[tuple[str, int], ...] = ()  # exact epoch ms for display zone


@dataclass(frozen=True, slots=True)
class RowFacts:
    key: str  # full candidate / signal / event ID
    section: Section
    kind: str  # CANDIDATE | SIGNAL | engine event kind
    side: str
    state: str
    candidate_id: str
    cells: tuple[str, ...]
    search: str  # lower-case haystack of every shown value and full ID
    detail: DetailFacts
    display_times: tuple[tuple[int, int], ...] = ()  # (column index, raw UTC epoch ms)


@dataclass(frozen=True, slots=True)
class SignalsFacts:
    developing: tuple[RowFacts, ...]
    current: tuple[RowFacts, ...]
    history: tuple[RowFacts, ...]
    journal_ok: bool
    note: str

    def rows(self, section: Section) -> tuple[RowFacts, ...]:
        return {
            Section.DEVELOPING: self.developing,
            Section.CURRENT: self.current,
            Section.HISTORY: self.history,
        }[section]

    def find(self, key: str) -> RowFacts | None:
        for row in (*self.developing, *self.current, *self.history):
            if row.key == key:
                return row
        return None


def _codes(codes) -> str:
    return ", ".join(c.value for c in codes) or "none"


def _haystack(*parts: str) -> str:
    return " ".join(parts).lower()


def _candidate_row(snap: Snapshot, c: S1Candidate) -> RowFacts:
    status, needs = candidate_condition(snap, c)
    level = snap.trigger_thresholds.get(c.candidate_id)
    now = snap.virtual_time_ms
    age = duration(None if now is None else now - c.first_detected_ms)
    pair = c.pair
    explanation = human_condition(snap, c)
    cells = (
        c.candidate_id,
        c.side.value,
        f"S1 {c.strategy_version}",
        status,
        needs,
        utc_ms_text(c.first_detected_ms),
        age,
    )
    fields = (
        ("Candidate ID", c.candidate_id),
        ("Side / pair", f"{c.side.value} · {pair.direction}"),
        ("Strategy", f"{c.strategy_id} {c.strategy_version}"),
        ("Engine state", c.state.value),
        ("Status", status),
        ("Next confirmed M5 BID close", needs),
        (
            "Trigger level (exact)",
            price_text(level) if level is not None else "UNAVAILABLE — not 0",
        ),
        ("Pair low (BID)", f"{price_text(pair.low.price)} · {pair.low.bar_id}"),
        ("Pair high (BID)", f"{price_text(pair.high.price)} · {pair.high.bar_id}"),
        ("Impulse", price_text(pair.impulse)),
        ("ATR14 M5 at pair", price_text(pair.atr_m5)),
        ("Pair available", utc_ms_text(pair.available_at_ms)),
        ("Pullback extreme", price_text(c.pullback_extreme)),
        ("Depth", price_text(c.depth)),
        ("Post-pivot M5 bars", str(c.post_pivot_bars)),
        ("Last closed M5 bar", c.last_closed_m5_id or UNAVAILABLE),
        ("First detected", utc_ms_text(c.first_detected_ms)),
        ("Last changed", utc_ms_text(c.last_changed_ms)),
        ("Reason codes", _codes(c.reason_codes)),
        ("Source", f"{c.source_id} [{c.source_origin.value}]"),
    )
    detail = DetailFacts(
        title=f"CANDIDATE {c.candidate_id}",
        status="NOT TRADABLE — developing",
        tone="neutral",
        fields=fields,
        notes=(explanation, "No entry can be recorded on a developing candidate."),
        lifecycle=(),
        actions=(ActionFacts("Record entry", False, "A developing candidate is not tradable."),),
        summary=explanation,
        time_fields=(
            ("Detected", c.first_detected_ms),
            ("Last changed", c.last_changed_ms),
            ("Pair available", pair.available_at_ms),
        ),
    )
    return RowFacts(
        key=c.candidate_id,
        section=Section.DEVELOPING,
        kind="CANDIDATE",
        side=c.side.value,
        state=status,
        candidate_id=c.candidate_id,
        cells=cells,
        search=_haystack(*cells, *(v for _, v in fields)),
        detail=detail,
        display_times=((DEVELOPING_COLUMNS.index("Detected (UTC)"), c.first_detected_ms),),
    )


def _lifecycle(events: Sequence[SignalEvent], signal_id: str, window_start: int | None):
    out = []
    for e in events:
        if e.signal_id != signal_id:
            continue
        pre = " · PRE-ROLL" if window_start is None or e.decision_time_ms < window_start else ""
        out.append(
            f"#{e.sequence} {e.kind.value} at {utc_ms_text(e.decision_time_ms)}"
            f" · reasons {_codes(e.reason_codes)}{pre}"
        )
    return tuple(out)


def _signal_row(
    snap: Snapshot,
    v: SignalView,
    events: Sequence[SignalEvent],
    overlay: Mapping[str, tuple[str, str | None]] | None,
    positions: Sequence[ManualPosition],
    section: Section,
) -> RowFacts:
    r = v.record
    lane = signal_lane(v, overlay or {})
    ent, ex = entry_labels(r.side)
    now = snap.virtual_time_ms
    live = v.status.state is SignalState.READY
    ttl = duration(r.expiry_ms - now) if live and now is not None else UNAVAILABLE
    q = snap.quote
    current = None if q is None else (q.ask if r.side is Side.BUY else q.bid)
    state = lane.label + (" · PRE-ROLL" if v.pre_roll else "")
    if overlay is None:
        operator = "UNKNOWN — operator records unreadable"
    elif lane.operator is None:
        operator = "none recorded locally"
    else:
        operator = lane.operator + (f" ({lane.position_id})" if lane.position_id else "")
    fidelity = r.execution_fidelity.value
    cells: tuple[str, ...]
    if section is Section.CURRENT:
        cells = (
            r.signal_id,
            r.side.value,
            utc_ms_text(r.first_ready_ms),
            state,
            f"{ent} {price_text(r.e0)}",
            band_text(r),
            f"{ex} {price_text(r.sl0)}",
            f"{ex} {price_text(r.tp1)}",
            f"{ex} {price_text(r.tp2)}",
            utc_ms_text(r.expiry_ms),
            ttl,
            fidelity,
        )
        display_times = (
            (CURRENT_COLUMNS.index("Issued (UTC)"), r.first_ready_ms),
            (CURRENT_COLUMNS.index("Expiry (UTC)"), r.expiry_ms),
        )
    else:
        cells = (
            r.signal_id,
            "SIGNAL · READY_ISSUED",
            r.side.value,
            utc_ms_text(r.first_ready_ms),
            state,
            f"{ent} {price_text(r.e0)} · SL {ex} {price_text(r.sl0)} · TP2 {ex} "
            f"{price_text(r.tp2)}",
        )
        display_times = ((HISTORY_COLUMNS.index("Time (UTC)"), r.first_ready_ms),)
    fields = (
        ("Signal ID", r.signal_id),
        ("Candidate ID", r.candidate_id),
        ("Trigger ID", r.trigger_id),
        ("Side", r.side.value),
        ("Source", f"{r.original_source_id} [{snap.source.origin}]"),
        ("Fidelity", f"{fidelity} — not broker-verified"),
        ("Strategy / rules", f"{r.strategy_version} · {r.signal_rules_version}"),
        ("Issued", f"READY at {utc_ms_text(r.first_ready_ms)} (immutable plan)"),
        ("Current state", lane.current + (" · PRE-ROLL history" if v.pre_roll else "")),
        ("Operator (local journal)", operator),
        (f"E0 = {ent} (entry side)", price_text(r.e0)),
        ("Original BID / ASK", f"{price_text(r.original_bid)} / {price_text(r.original_ask)}"),
        ("Entry band", f"{price_text(r.entry_low)} – {price_text(r.entry_high)}"),
        (f"SL0 ({ex} closes)", price_text(r.sl0)),
        (f"TP1 ({ex} closes)", price_text(r.tp1)),
        (f"TP2 ({ex} closes)", price_text(r.tp2)),
        ("Frozen ATR", price_text(r.frozen_atr)),
        ("Original gross risk", price_text(r.original_risk_price)),
        ("Price step", price_text(r.price_step)),
        ("Expiry", utc_ms_text(r.expiry_ms)),
        ("Time left (virtual clock)", ttl),
        (f"Current {ent}", price_text(current)),
        ("Current spread", price_text(None if q is None else q.spread)),
        ("Blocking codes now", _codes(v.status.blocked_reasons)),
        (
            "Terminal reason",
            v.status.terminal_reason.value if v.status.terminal_reason else UNAVAILABLE,
        ),
        ("Exit policy", r.exit_policy),
        ("Cost model", r.estimated_cost_model_id or "UNKNOWN — net R/fees not confirmed"),
        ("Config", f"{snap.source.config_hash} v{snap.source.config_version}"),
    )
    notes: list[str] = []
    if v.pre_roll:
        notes.append("PRE-ROLL history signal — issued before the replay window; not an alert.")
    if lane.blocked:
        notes.append(
            "EXECUTION BLOCKED — no on-plan entry. A real external fill would be recorded "
            "OFF_PLAN through a separate, acknowledged workflow."
        )
    if lane.terminal:
        notes.append(f"{lane.current} — terminal, never resurrected.")
    if overlay is None:
        notes.append("Operator records unavailable — this READY cannot be confirmed unclaimed.")
    elif lane.operator is not None:
        notes.append(f"{lane.why_not_actionable}.")
    if lane.can_record and overlay is not None:
        notes.extend(exposure(positions, r.side).warnings())
    sid = r.signal_id
    if lane.can_record and overlay is not None:
        # A READY that is EXECUTION BLOCKED can still be recorded, always OFF_PLAN (the
        # journal classifies it); the button says so before the form opens.
        entry = "Record entry — OFF_PLAN (blocked)" if lane.blocked else "Record entry (on-plan)"
        actions = [
            ActionFacts(entry, True, "", "entry", sid),
            ActionFacts("Skip", True, "", "skip", sid),
        ]
    else:
        why = lane.why_not_actionable
        reason = UNCONFIRMED if overlay is None else f"{why}." if why else "Not READY."
        actions = [
            ActionFacts("Record entry", False, reason, "entry", sid),
            ActionFacts("Skip", False, reason, "skip", sid),
        ]
    tone = "error" if lane.terminal else "warning" if (lane.blocked or v.pre_roll) else "ready"
    if lane.operator is not None or overlay is None:
        tone = "warning"
    if overlay is None:
        summary = "Local journal unavailable — cannot verify whether this signal was claimed."
    elif v.pre_roll:
        summary = "Pre-roll history — this proposal predates the visible replay window."
    elif lane.terminal:
        summary = f"{lane.current} — a historical signal, not a fresh proposal."
    elif lane.operator is not None:
        summary = f"Local operator action recorded: {operator}. No new on-plan entry implied."
    elif lane.blocked:
        summary = (
            "Execution blocked for an on-plan entry. Any external fill must follow "
            "the separately acknowledged OFF_PLAN record workflow."
        )
    elif live:
        summary = (
            f"READY {r.side.value} proposal in simulation. Exact {ent} entry, "
            f"{ex} stop and targets follow below; no broker fill is implied."
        )
    else:
        summary = f"{lane.current} — not a fresh actionable proposal."
    return RowFacts(
        key=r.signal_id,
        section=section,
        kind="SIGNAL",
        side=r.side.value,
        state=state,
        candidate_id=r.candidate_id,
        cells=cells,
        search=_haystack(*cells, *(val for _, val in fields)),
        detail=DetailFacts(
            title=f"SIGNAL {r.signal_id}",
            status=state,
            tone=tone,
            fields=fields,
            notes=tuple(notes),
            lifecycle=_lifecycle(events, r.signal_id, snap.window_start_ms),
            actions=tuple(actions),
            summary=summary,
            time_fields=(("Issued", r.first_ready_ms), ("Expiry", r.expiry_ms)),
        ),
        display_times=display_times,
    )


def _event_row(snap: Snapshot, e: SignalEvent) -> RowFacts:
    start = snap.window_start_ms
    pre = start is None or e.decision_time_ms < start
    state = e.kind.value + (" · PRE-ROLL" if pre else "")
    summary = f"reasons {_codes(e.reason_codes)}"
    cells = (
        e.event_id,
        e.kind.value,
        e.side.value,
        utc_ms_text(e.decision_time_ms),
        state,
        summary,
    )
    gates = ", ".join(f"{g.gate}:{g.result.value}" for g in e.gates) or "none recorded"
    fields = (
        ("Event ID", e.event_id),
        ("Event kind", e.kind.value),
        ("Sequence", str(e.sequence)),
        ("Side", e.side.value),
        ("Candidate ID", e.candidate_id),
        ("Trigger ID", e.trigger_id),
        ("Signal ID", e.signal_id or "none — not issued"),
        ("Decision (receipt) time", utc_ms_text(e.decision_time_ms)),
        ("Event time", utc_ms_text(e.event_time_ms)),
        ("Reason codes", _codes(e.reason_codes)),
        ("Gates", gates),
        ("Quote BID / ASK", f"{price_text(e.quote_bid)} / {price_text(e.quote_ask)}"),
        ("Source", f"{e.source_id} [{snap.source.origin}]"),
    )
    notes = [NO_EVENT_RECORD]
    if pre:
        notes.append("PRE-ROLL history — before the replay window; not an alert.")
    return RowFacts(
        key=e.event_id,
        section=Section.HISTORY,
        kind=e.kind.value,
        side=e.side.value,
        state=state,
        candidate_id=e.candidate_id,
        cells=cells,
        search=_haystack(*cells, *(val for _, val in fields)),
        detail=DetailFacts(
            title=f"EVENT {e.kind.value}",
            status=state,
            tone="neutral",
            fields=fields,
            notes=tuple(notes),
            lifecycle=(),
            actions=(ActionFacts("Record entry", False, "No signal was issued."),),
            summary=(
                f"{e.kind.value.replace('_', ' ').title()} — historical research event; "
                "no SignalRecord or broker order was issued."
            ),
            time_fields=(
                ("Decision (received)", e.decision_time_ms),
                ("Event", e.event_time_ms),
            ),
        ),
        display_times=((HISTORY_COLUMNS.index("Time (UTC)"), e.decision_time_ms),),
    )


def build_signals_facts(
    snap: Snapshot,
    events: Sequence[SignalEvent],
    overlay: Mapping[str, tuple[str, str | None]] | None,
    positions: Sequence[ManualPosition] | None,
    journal_note: str,
) -> SignalsFacts:
    """Developing, current READY/blocked and history rows in engine order (never ranked)."""
    held = list(positions or ())
    developing = tuple(_candidate_row(snap, c) for c in snap.forming)
    current: list[RowFacts] = []
    history: list[tuple[int, int, RowFacts]] = []
    for v in snap.signals:
        lane = signal_lane(v, overlay or {})
        acted = overlay is not None and lane.operator is not None
        if lane.terminal or v.pre_roll or acted:
            row = _signal_row(snap, v, events, overlay, held, Section.HISTORY)
            history.append((v.record.first_ready_ms, len(history), row))
        else:
            current.append(_signal_row(snap, v, events, overlay, held, Section.CURRENT))
    no_record = (
        SignalEventKind.MISSED_DATA_GAP,
        SignalEventKind.MISSED_PRICE_CHASE,
        SignalEventKind.NOT_ISSUED,
    )
    for e in events:
        if e.signal_id is None and e.kind in no_record:
            history.append((e.decision_time_ms, len(history), _event_row(snap, e)))
    # History is chronological, newest first (time order, not a ranking).
    ordered = tuple(
        row for _t, _i, row in sorted(history, key=lambda h: (h[0], h[1]), reverse=True)
    )
    return SignalsFacts(
        developing=developing,
        current=tuple(current),
        history=ordered,
        journal_ok=overlay is not None,
        note=journal_note,
    )
