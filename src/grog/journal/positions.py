"""Local manual-position journal: entries, skips, partials, modifications, closes and
restart reconciliation (docs/07 Sections 1, 6-8; docs/09 Sections 3.6 and 7; docs/02 §9).

Safety contract:

* Every record is an explicit operator statement saved to the **local** SQLite journal.
  Nothing here talks to a broker, places/modifies/cancels an order or infers a fill from
  a price touch (docs/07 §1, §7.7).
* One transaction per action: the append-only ``position_events`` row and the
  ``manual_positions`` projection are written together or not at all (ST-04).
* Each form submission carries a stable ``action_id``. Re-submitting the same action is
  idempotent; re-using an action ID for different content is rejected (ST-05).
* The original signal record is never changed. A linked entry only *reads* its frozen
  plan to classify ON_PLAN / OFF_PLAN and compute actual-entry economics (docs/07 §5).
* Missing values stay UNKNOWN: blank fees are not zero, no currency P/L without a
  verified contract (ST-09), no net R without known fees and contract value.
* On program start open positions are restored as RECONCILIATION_REQUIRED until the
  operator verifies them (docs/07 §8, ST-06, UI-18).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from grog.analysis.params import CALC_CONTEXT
from grog.domain.enums import ExecutionFidelity, H1Bias, Side
from grog.domain.ids import canonical_json, sha256_hex
from grog.domain.models import NormalizedQuote, SignalRecord
from grog.journal.store import Store
from grog.risk.quotes_and_plans import ContractSpec, MoneyAmount, price_to_money

__all__ = [
    "DecisionRecord",
    "EntryPreview",
    "EntryRequest",
    "JournalError",
    "ManualPosition",
    "Mark",
    "PlanRef",
    "PlanStatus",
    "PositionAction",
    "PositionEventRecord",
    "PositionJournal",
    "PositionState",
    "entry_preview",
    "mark_position",
    "new_action_id",
    "parse_amount",
]

ZERO = Decimal(0)
REPORTING_CURRENCY = "UNKNOWN"  # no account/reporting currency is configured (OPEN)


class PositionState(StrEnum):
    MONITORING = "MONITORING"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    CLOSED = "CLOSED"


class PositionAction(StrEnum):
    ENTRY = "ENTRY"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    MODIFY = "MODIFY"
    CLOSE = "CLOSE"
    RESTORED_UNVERIFIED = "RESTORED_UNVERIFIED"
    CONFIRMED_OPEN = "CONFIRMED_OPEN"


class PlanStatus(StrEnum):
    ON_PLAN = "ON_PLAN"
    OFF_PLAN = "OFF_PLAN"


class JournalError(Exception):
    """A rejected or unsaved journal action. ``code`` is stable; nothing was changed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def new_action_id() -> str:
    """Stable ID created once when a form opens; every resubmission reuses it."""
    return uuid.uuid4().hex


# --------------------------------------------------------------------------- validation


def parse_amount(
    text: str | None,
    field_name: str,
    *,
    required: bool = True,
    allow_zero: bool = False,
) -> Decimal | None:
    """Exact finite decimal. Rejects NaN/Infinity/negatives (and zero unless allowed).
    Blank optional input is ``None`` (UNKNOWN), never zero."""
    raw = (text or "").strip()
    if not raw:
        if required:
            raise JournalError("MISSING_VALUE", f"{field_name} is required")
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise JournalError("INVALID_NUMBER", f"{field_name} {raw!r} is not a decimal") from exc
    if not value.is_finite():
        raise JournalError("INVALID_NUMBER", f"{field_name} must be finite")
    if value < 0 or (value == 0 and not allow_zero):
        rule = ">= 0" if allow_zero else "> 0"
        raise JournalError("INVALID_NUMBER", f"{field_name} must be {rule}")
    return value


def _norm(value: Decimal) -> str:
    """Exact TEXT without exponent noise; ``0`` for any zero."""
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _sign(side: Side) -> int:
    return 1 if side is Side.BUY else -1


def _div(a: Decimal, b: Decimal) -> Decimal:
    return CALC_CONTEXT.divide(a, b)


# --------------------------------------------------------------------------- plan reference


@dataclass(frozen=True, slots=True)
class PlanRef:
    """Read-only copy of the frozen original plan a manual entry is compared with."""

    signal_id: str
    source_id: str
    strategy_version: str
    side: Side
    e0: Decimal
    sl0: Decimal
    tp1: Decimal
    tp2: Decimal
    entry_low: Decimal
    entry_high: Decimal
    original_risk: Decimal
    first_ready_ms: int
    expiry_ms: int
    fidelity: str

    @classmethod
    def from_record(cls, r: SignalRecord) -> PlanRef:
        return cls(
            signal_id=r.signal_id,
            source_id=r.original_source_id,
            strategy_version=r.strategy_version,
            side=r.side,
            e0=r.e0,
            sl0=r.sl0,
            tp1=r.tp1,
            tp2=r.tp2,
            entry_low=r.entry_low,
            entry_high=r.entry_high,
            original_risk=r.original_risk_price,
            first_ready_ms=r.first_ready_ms,
            expiry_ms=r.expiry_ms,
            fidelity=r.execution_fidelity.value,
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in d.items()} | {
            "side": self.side.value
        }

    @classmethod
    def from_dict(cls, d: dict) -> PlanRef:
        dec = {"e0", "sl0", "tp1", "tp2", "entry_low", "entry_high", "original_risk"}
        kw = {k: (Decimal(v) if k in dec else v) for k, v in d.items()}
        kw["side"] = Side(d["side"])
        return cls(**kw)


# --------------------------------------------------------------------------- entry preview


@dataclass(frozen=True, slots=True)
class EntryPreview:
    """What the operator sees before confirming (docs/02 §9 Record Entry)."""

    plan_status: PlanStatus
    off_plan_reasons: tuple[str, ...]
    original_e0: Decimal | None
    actual_price: Decimal
    entry_difference: Decimal | None  # adverse > 0 (paid more for BUY / received less SELL)
    original_risk: Decimal | None
    actual_risk: Decimal | None  # gross price risk vs the stop actually in force
    original_target_r: Decimal | None
    actual_target_r: Decimal | None  # to TP2 actually in force, gross, before fees
    stop: Decimal | None
    target: Decimal | None
    warnings: tuple[str, ...]


def entry_preview(
    side: Side,
    price: Decimal,
    fill_ms: int,
    plan: PlanRef | None,
    *,
    stop: Decimal | None = None,
    target: Decimal | None = None,
    signal_ready: bool = False,
    signal_blocked: bool = False,
    known_clock_ms: int | None = None,
) -> EntryPreview:
    """Classify the actual fill against the immutable plan and compute actual economics.

    ON_PLAN only when linked to a READY, unblocked signal, same side, filled inside the
    original entry band, inside [first READY, expiry] and with the recommended SL/TP.
    Anything else is OFF_PLAN (docs/06 §4, docs/07 §5, §10.3.6). The plan is not changed.
    """
    reasons: list[str] = []
    warnings: list[str] = []
    sl = stop if stop is not None else (plan.sl0 if plan else None)
    tp = target if target is not None else (plan.tp2 if plan else None)
    if plan is None:
        reasons.append("NO_READY_SIGNAL_LINK")
    else:
        if side is not plan.side:
            reasons.append("SIDE_DIFFERS_FROM_SIGNAL")
        if not signal_ready:
            reasons.append("SIGNAL_NOT_READY")
        if signal_blocked:
            reasons.append("EXECUTION_BLOCKED_AT_RECORD")
        if not plan.entry_low <= price <= plan.entry_high:
            reasons.append("OUTSIDE_ENTRY_BAND")
        if fill_ms > plan.expiry_ms:
            reasons.append("AFTER_SIGNAL_EXPIRY")
        if fill_ms < plan.first_ready_ms:
            reasons.append("BEFORE_FIRST_READY")
        if stop is not None and stop != plan.sl0:
            reasons.append("STOP_DIFFERS_FROM_PLAN")
        if target is not None and target != plan.tp2:
            reasons.append("TARGET_DIFFERS_FROM_PLAN")
    sign = _sign(side)
    actual_risk = None
    if sl is not None:
        risk = (price - sl) * sign
        if risk > 0:
            actual_risk = risk
        else:
            warnings.append("STOP_ON_WRONG_SIDE_OF_FILL: actual risk UNKNOWN")
    actual_target_r = None
    if actual_risk is not None and tp is not None:
        reward = (tp - price) * sign
        actual_target_r = _div(reward, actual_risk)
        if reward <= 0:
            warnings.append("TARGET_ALREADY_PASSED_AT_FILL")
    if known_clock_ms is not None and fill_ms > known_clock_ms:
        warnings.append("FILL_TIME_AHEAD_OF_KNOWN_CLOCK")
    original_target_r = (
        _div((plan.tp2 - plan.e0) * _sign(plan.side), plan.original_risk) if plan else None
    )
    return EntryPreview(
        plan_status=PlanStatus.OFF_PLAN if reasons else PlanStatus.ON_PLAN,
        off_plan_reasons=tuple(reasons),
        original_e0=plan.e0 if plan else None,
        actual_price=price,
        entry_difference=(price - plan.e0) * sign if plan else None,
        original_risk=plan.original_risk if plan else None,
        actual_risk=actual_risk,
        original_target_r=original_target_r,
        actual_target_r=actual_target_r,
        stop=sl,
        target=tp,
        warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------- read models


@dataclass(frozen=True, slots=True)
class ManualPosition:
    """Projection of one locally recorded position (docs/09 §3.6). Not a broker position."""

    position_id: str
    linked_signal_id: str | None
    signal_link: str  # PLAN | INFORMATIONAL | NONE
    source_id: str
    mode: str
    fidelity: str
    plan_status: PlanStatus
    off_plan_reasons: tuple[str, ...]
    side: Side
    entry_price: Decimal
    entry_ms: int
    entry_recorded_ms: int
    initial_qty: Decimal
    remaining_qty: Decimal
    initial_sl: Decimal | None
    current_sl: Decimal | None
    tp1: Decimal | None
    current_tp: Decimal | None
    initial_risk: Decimal | None  # frozen at entry; later stop changes never rewrite it
    fees_known: Decimal  # sum of fees the operator stated
    fees_unknown_count: int  # actions whose fees were left UNKNOWN
    realized_price_units: Decimal  # sum of signed (exit - entry) x qty, gross
    state: PositionState
    last_event_ms: int
    last_recorded_ms: int
    events: int
    broker: str | None
    plan: PlanRef | None
    h1_bias_at_entry: str | None

    @property
    def is_open(self) -> bool:
        return self.state is not PositionState.CLOSED

    @property
    def fees_text(self) -> str:
        if self.fees_unknown_count and self.fees_known == 0:
            return "UNKNOWN"
        if self.fees_unknown_count:
            return f"{_norm(self.fees_known)} + UNKNOWN"
        return _norm(self.fees_known)

    @property
    def realized_r(self) -> Decimal | None:
        """Gross realized R of closed quantity relative to the full initial risk."""
        closed = self.initial_qty - self.remaining_qty
        if self.initial_risk is None or closed == 0:
            return None
        return _div(self.realized_price_units, self.initial_risk * self.initial_qty)

    def to_dict(self) -> dict:
        out = {}
        for k in self.__dataclass_fields__:
            v = getattr(self, k)
            if isinstance(v, Decimal):
                v = _norm(v) if k.endswith("qty") else str(v)
            elif isinstance(v, StrEnum):
                v = v.value
            elif isinstance(v, PlanRef):
                v = v.to_dict()
            elif isinstance(v, tuple):
                v = list(v)
            out[k] = v
        return out

    @classmethod
    def from_dict(cls, d: dict) -> ManualPosition:
        dec = {
            "entry_price",
            "initial_qty",
            "remaining_qty",
            "initial_sl",
            "current_sl",
            "tp1",
            "current_tp",
            "initial_risk",
            "fees_known",
            "realized_price_units",
        }
        kw = {}
        for k, v in d.items():
            if k in dec:
                v = None if v is None else Decimal(v)
            kw[k] = v
        kw["side"] = Side(d["side"])
        kw["state"] = PositionState(d["state"])
        kw["plan_status"] = PlanStatus(d["plan_status"])
        kw["off_plan_reasons"] = tuple(d["off_plan_reasons"])
        kw["plan"] = None if d["plan"] is None else PlanRef.from_dict(d["plan"])
        return cls(**kw)


@dataclass(frozen=True, slots=True)
class PositionEventRecord:
    event_id: str
    position_id: str
    sequence: int
    action: PositionAction
    effective_at_ms: int
    recorded_at_ms: int
    qty: Decimal | None
    price: Decimal | None
    fees: Decimal | None
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    decision_id: str
    signal_id: str
    source_id: str
    mode: str
    decision: str
    effective_at_ms: int
    recorded_at_ms: int
    reason: str | None


@dataclass(frozen=True, slots=True)
class EntryRequest:
    action_id: str
    side: Side
    price: Decimal
    qty: Decimal
    fill_ms: int
    source_id: str
    mode: str = "REPLAY"
    fidelity: str = ExecutionFidelity.SIMULATED.value
    plan: PlanRef | None = None  # on-plan candidate link (Record Entry on READY)
    informational_signal_id: str | None = None  # unlinked entry: link never changes signal
    signal_ready: bool = False
    signal_blocked: bool = False
    stop: Decimal | None = None
    target: Decimal | None = None
    fees: Decimal | None = None
    broker: str | None = None
    note: str | None = None
    known_clock_ms: int | None = None
    h1_bias_at_entry: H1Bias | None = None

    def payload(self) -> dict:
        return {
            "side": self.side.value,
            "price": str(self.price),
            "qty": _norm(self.qty),
            "fill_ms": self.fill_ms,
            "source_id": self.source_id,
            "mode": self.mode,
            "fidelity": self.fidelity,
            "plan": None if self.plan is None else self.plan.to_dict(),
            "informational_signal_id": self.informational_signal_id,
            "signal_ready": self.signal_ready,
            "signal_blocked": self.signal_blocked,
            "stop": None if self.stop is None else str(self.stop),
            "target": None if self.target is None else str(self.target),
            "fees": None if self.fees is None else str(self.fees),
            "broker": self.broker or None,
            "note": self.note or None,
            "known_clock_ms": self.known_clock_ms,
            "h1_bias_at_entry": None if self.h1_bias_at_entry is None else self.h1_bias_at_entry,
        }


# --------------------------------------------------------------------------- monitoring


@dataclass(frozen=True, slots=True)
class Mark:
    """Closeable-side mark of an open position (docs/07 §6). Observations, not advice."""

    closeable: Decimal | None  # BID for BUY, ASK for SELL
    closeable_side: str
    quote_ms: int | None
    unrealized_price_units: Decimal | None  # signed (mark - entry) x remaining qty
    unrealized_r: Decimal | None  # gross, per unit, vs frozen initial risk
    money: MoneyAmount | None
    reason: str | None  # why the mark is UNAVAILABLE / UNKNOWN


def mark_position(
    pos: ManualPosition,
    quote: NormalizedQuote | None,
    *,
    contract: ContractSpec | None = None,
    stale: bool = False,
) -> Mark:
    side_label = "BID" if pos.side is Side.BUY else "ASK"
    if quote is None or quote.source_id != pos.source_id:
        why = "no quote from this position's source" if quote else "no quote loaded"
        return Mark(None, side_label, None, None, None, None, f"monitoring UNAVAILABLE: {why}")
    if quote.received_time_ms < pos.entry_ms:
        return Mark(
            None,
            side_label,
            quote.received_time_ms,
            None,
            None,
            None,
            "monitoring UNAVAILABLE: replay clock is before the recorded fill time",
        )
    mark = quote.bid if pos.side is Side.BUY else quote.ask
    move = (mark - pos.entry_price) * _sign(pos.side)
    units = move * pos.remaining_qty
    r = _div(move, pos.initial_risk) if pos.initial_risk else None
    money = price_to_money(move, pos.remaining_qty, contract, REPORTING_CURRENCY)
    reason = "PRICES STALE — monitoring degraded" if stale else None
    return Mark(mark, side_label, quote.received_time_ms, units, r, money, reason)


# --------------------------------------------------------------------------- projection


def _apply(pos: ManualPosition | None, ev: PositionEventRecord) -> ManualPosition:
    p = ev.payload
    if ev.action is PositionAction.ENTRY:
        plan = None if p["plan"] is None else PlanRef.from_dict(p["plan"])
        side = Side(p["side"])
        price = Decimal(p["price"])
        prev = entry_preview(
            side,
            price,
            p["fill_ms"],
            plan,
            stop=None if p["stop"] is None else Decimal(p["stop"]),
            target=None if p["target"] is None else Decimal(p["target"]),
            signal_ready=p["signal_ready"],
            signal_blocked=p["signal_blocked"],
        )
        fees = None if p["fees"] is None else Decimal(p["fees"])
        return ManualPosition(
            position_id=ev.position_id,
            linked_signal_id=plan.signal_id if plan else p["informational_signal_id"],
            signal_link="PLAN"
            if plan
            else ("INFORMATIONAL" if p["informational_signal_id"] else "NONE"),
            source_id=p["source_id"],
            mode=p["mode"],
            fidelity=p["fidelity"],
            plan_status=prev.plan_status,
            off_plan_reasons=prev.off_plan_reasons,
            side=side,
            entry_price=price,
            entry_ms=p["fill_ms"],
            entry_recorded_ms=ev.recorded_at_ms,
            initial_qty=Decimal(p["qty"]),
            remaining_qty=Decimal(p["qty"]),
            initial_sl=prev.stop,
            current_sl=prev.stop,
            tp1=plan.tp1 if plan else None,
            current_tp=prev.target,
            initial_risk=prev.actual_risk,
            fees_known=fees or ZERO,
            fees_unknown_count=0 if fees is not None else 1,
            realized_price_units=ZERO,
            state=PositionState.MONITORING,
            last_event_ms=ev.effective_at_ms,
            last_recorded_ms=ev.recorded_at_ms,
            events=1,
            broker=p["broker"],
            plan=plan,
            h1_bias_at_entry=p["h1_bias_at_entry"],
        )
    assert pos is not None
    base = replace(
        pos,
        last_event_ms=max(pos.last_event_ms, ev.effective_at_ms),
        last_recorded_ms=ev.recorded_at_ms,
        events=pos.events + 1,
    )
    if ev.action in (PositionAction.PARTIAL_CLOSE, PositionAction.CLOSE):
        assert ev.qty is not None and ev.price is not None
        remaining = pos.remaining_qty - ev.qty
        realized = (ev.price - pos.entry_price) * _sign(pos.side) * ev.qty
        return replace(
            base,
            remaining_qty=remaining,
            realized_price_units=pos.realized_price_units + realized,
            fees_known=pos.fees_known + (ev.fees or ZERO),
            fees_unknown_count=pos.fees_unknown_count + (0 if ev.fees is not None else 1),
            state=PositionState.CLOSED if remaining == 0 else PositionState.MONITORING,
        )
    if ev.action is PositionAction.MODIFY:
        sl = p.get("new_stop")
        tp = p.get("new_target")
        return replace(
            base,
            current_sl=pos.current_sl if sl is None else Decimal(sl),
            current_tp=pos.current_tp if tp is None else Decimal(tp),
            state=PositionState.MONITORING,
        )
    if ev.action is PositionAction.RESTORED_UNVERIFIED:
        return replace(base, state=PositionState.RECONCILIATION_REQUIRED)
    if ev.action is PositionAction.CONFIRMED_OPEN:
        return replace(base, state=PositionState.MONITORING)
    raise AssertionError(ev.action)


def _event_row_values(ev: PositionEventRecord) -> tuple:
    return (
        ev.event_id,
        ev.position_id,
        ev.sequence,
        ev.action.value,
        ev.effective_at_ms,
        ev.recorded_at_ms,
        None if ev.qty is None else _norm(ev.qty),
        None if ev.price is None else str(ev.price),
        None if ev.fees is None else str(ev.fees),
        canonical_json(ev.payload),
        ev.event_id,
    )


def _event_from_row(row: sqlite3.Row) -> PositionEventRecord:
    return PositionEventRecord(
        event_id=row["event_id"],
        position_id=row["position_id"],
        sequence=row["sequence"],
        action=PositionAction(row["action_type"]),
        effective_at_ms=row["effective_at_ms"],
        recorded_at_ms=row["recorded_at_ms"],
        qty=None if row["qty_text"] is None else Decimal(row["qty_text"]),
        price=None if row["price_text"] is None else Decimal(row["price_text"]),
        fees=None if row["fees_text"] is None else Decimal(row["fees_text"]),
        payload=json.loads(row["payload_json"]),
    )


def _content_hash(kind: str, payload: dict) -> str:
    return sha256_hex(canonical_json({"kind": kind, "payload": payload}).encode())


# --------------------------------------------------------------------------- service


class PositionJournal:
    """Validated journal domain service. The UI calls only these methods."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self._conn = store._conn  # single serialized writer owned by the Store

    # ------------------------------------------------------------------ reads

    def positions(self, *, include_closed: bool = True) -> list[ManualPosition]:
        sql = "SELECT snapshot_json FROM manual_positions"
        if not include_closed:
            sql += " WHERE state != 'CLOSED'"
        rows = self._conn.execute(sql + " ORDER BY entry_ms, position_id")
        return [ManualPosition.from_dict(json.loads(r["snapshot_json"])) for r in rows]

    def open_positions(self) -> list[ManualPosition]:
        return self.positions(include_closed=False)

    def get(self, position_id: str) -> ManualPosition | None:
        row = self._conn.execute(
            "SELECT snapshot_json FROM manual_positions WHERE position_id = ?", (position_id,)
        ).fetchone()
        return None if row is None else ManualPosition.from_dict(json.loads(row["snapshot_json"]))

    def events(self, position_id: str | None = None) -> list[PositionEventRecord]:
        if position_id is None:
            rows = self._conn.execute(
                "SELECT * FROM position_events ORDER BY effective_at_ms, recorded_at_ms, "
                "position_id, sequence"
            )
        else:
            rows = self._conn.execute(
                "SELECT * FROM position_events WHERE position_id = ? ORDER BY sequence",
                (position_id,),
            )
        return [_event_from_row(r) for r in rows]

    def decisions(self) -> list[DecisionRecord]:
        rows = self._conn.execute(
            "SELECT * FROM signal_decisions ORDER BY effective_at_ms, recorded_at_ms"
        )
        return [
            DecisionRecord(
                r["decision_id"],
                r["signal_id"],
                r["source_id"],
                r["mode"],
                r["decision"],
                r["effective_at_ms"],
                r["recorded_at_ms"],
                r["reason"],
            )
            for r in rows
        ]

    def signal_status(self, source_id: str, signal_id: str) -> str | None:
        """``USER_SKIPPED`` / ``ENTERED`` operator status of a signal, if any."""
        if self._conn.execute(
            "SELECT 1 FROM signal_decisions WHERE source_id = ? AND signal_id = ?",
            (source_id, signal_id),
        ).fetchone():
            return "USER_SKIPPED"
        if self._conn.execute(
            "SELECT 1 FROM manual_positions WHERE source_id = ? AND linked_signal_id = ? "
            "AND signal_link = 'PLAN'",
            (source_id, signal_id),
        ).fetchone():
            return "ENTERED"
        return None

    # ------------------------------------------------------------------ helpers

    def _existing(self, action_id: str, content: str) -> bool:
        """True when this exact action is already saved (idempotent resubmission)."""
        for table, key in (("position_events", "dedupe_key"), ("signal_decisions", "dedupe_key")):
            row = self._conn.execute(
                f"SELECT payload_json FROM {table} WHERE {key} = ?", (action_id,)
            ).fetchone()
            if row is not None:
                if json.loads(row["payload_json"]).get("content_sha256") == content:
                    return True
                raise JournalError(
                    "DUPLICATE_ACTION_ID",
                    "this action ID was already used for a different record; nothing changed",
                )
        return False

    _EVENT_SQL = (
        "INSERT INTO position_events (event_id, position_id, sequence, action_type, "
        "effective_at_ms, recorded_at_ms, qty_text, price_text, fees_text, payload_json, "
        "dedupe_key) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
    )

    def _write(self, ev: PositionEventRecord, fail_after_event: bool = False) -> ManualPosition:
        """Append one event and update the projection in a single transaction (ST-04).
        Any failure rolls back both; the caller reports "NOT saved"."""
        try:
            with self.store.transaction() as conn:
                before = None if ev.action is PositionAction.ENTRY else self.get(ev.position_id)
                new = _apply(before, ev)
                if new.remaining_qty < 0:
                    raise JournalError("QTY_EXCEEDS_REMAINING", "negative remaining size")
                snap = canonical_json(new.to_dict())
                if ev.action is PositionAction.ENTRY:
                    conn.execute(
                        "INSERT INTO manual_positions (position_id, linked_signal_id, "
                        "signal_link, source_id, mode, source_fidelity, plan_status, side, "
                        "initial_qty_text, remaining_qty_text, entry_price_text, entry_ms, "
                        "entry_recorded_ms, state, snapshot_json, updated_at_ms) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            new.position_id,
                            new.linked_signal_id,
                            new.signal_link,
                            new.source_id,
                            new.mode,
                            new.fidelity,
                            new.plan_status.value,
                            new.side.value,
                            _norm(new.initial_qty),
                            _norm(new.remaining_qty),
                            str(new.entry_price),
                            new.entry_ms,
                            new.entry_recorded_ms,
                            new.state.value,
                            snap,
                            ev.recorded_at_ms,
                        ),
                    )
                conn.execute(self._EVENT_SQL, _event_row_values(ev))
                if fail_after_event:
                    raise sqlite3.OperationalError("injected failure after event insert")
                if ev.action is not PositionAction.ENTRY:
                    conn.execute(
                        "UPDATE manual_positions SET remaining_qty_text = ?, state = ?, "
                        "snapshot_json = ?, updated_at_ms = ? WHERE position_id = ?",
                        (
                            _norm(new.remaining_qty),
                            new.state.value,
                            snap,
                            ev.recorded_at_ms,
                            new.position_id,
                        ),
                    )
        except sqlite3.Error as exc:
            raise JournalError(
                "NOT_SAVED",
                f"Position record NOT saved ({exc}); nothing was changed. Close other Grog "
                "instances or check disk space, then retry.",
            ) from exc
        return new

    def _open_position(self, position_id: str) -> ManualPosition:
        pos = self.get(position_id)
        if pos is None:
            raise JournalError("POSITION_NOT_FOUND", f"no recorded position {position_id}")
        if not pos.is_open:
            raise JournalError("POSITION_CLOSED", f"{position_id} is already CLOSED")
        return pos

    def _next_seq(self, position_id: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) AS s FROM position_events WHERE position_id = ?",
            (position_id,),
        ).fetchone()
        return int(row["s"]) + 1

    # ------------------------------------------------------------------ actions

    def record_entry(self, req: EntryRequest) -> tuple[ManualPosition, bool]:
        """Record Entry (on READY) or Unlinked/off-plan entry. Returns ``(position, created)``."""
        if req.qty <= 0 or req.price <= 0:
            raise JournalError("INVALID_NUMBER", "price and quantity must be > 0")
        if req.fees is not None and req.fees < 0:
            raise JournalError("INVALID_NUMBER", "fees must be >= 0")
        payload = req.payload()
        content = _content_hash("ENTRY", payload)
        if self._existing(req.action_id, content):
            row = self._conn.execute(
                "SELECT position_id FROM position_events WHERE dedupe_key = ?", (req.action_id,)
            ).fetchone()
            return self.get(row["position_id"]), False  # type: ignore[return-value]
        if req.plan is not None:
            status = self.signal_status(req.source_id, req.plan.signal_id)
            if status is not None:
                raise JournalError(
                    "SIGNAL_ALREADY_" + status.removeprefix("USER_"),
                    f"{req.plan.signal_id} is already {status}; use n for an unlinked "
                    "OFF_PLAN record",
                )
        position_id = "POS-" + req.action_id[:12].upper()
        ev = PositionEventRecord(
            event_id=req.action_id,
            position_id=position_id,
            sequence=1,
            action=PositionAction.ENTRY,
            effective_at_ms=req.fill_ms,
            recorded_at_ms=self.store.now_ms(),
            qty=req.qty,
            price=req.price,
            fees=req.fees,
            payload=payload | {"content_sha256": content},
        )
        return self._write(ev), True

    def record_skip(
        self,
        action_id: str,
        plan: PlanRef,
        *,
        effective_ms: int,
        mode: str = "REPLAY",
        reason: str | None = None,
    ) -> tuple[DecisionRecord, bool]:
        payload = {
            "signal": plan.to_dict(),
            "effective_ms": effective_ms,
            "mode": mode,
            "reason": reason or None,
        }
        content = _content_hash("USER_SKIPPED", payload)
        if not self._existing(action_id, content):
            status = self.signal_status(plan.source_id, plan.signal_id)
            if status is not None:
                raise JournalError(
                    "SIGNAL_ALREADY_" + status.removeprefix("USER_"),
                    f"{plan.signal_id} is already {status}",
                )
            try:
                with self.store.transaction() as conn:
                    conn.execute(
                        "INSERT INTO signal_decisions (decision_id, signal_id, source_id, mode, "
                        "decision, effective_at_ms, recorded_at_ms, reason, payload_json, "
                        "dedupe_key) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            action_id,
                            plan.signal_id,
                            plan.source_id,
                            mode,
                            "USER_SKIPPED",
                            effective_ms,
                            self.store.now_ms(),
                            reason or None,
                            canonical_json(payload | {"content_sha256": content}),
                            action_id,
                        ),
                    )
            except sqlite3.Error as exc:
                raise JournalError(
                    "NOT_SAVED", f"Skip NOT saved ({exc}); nothing was changed. Retry."
                ) from exc
            created = True
        else:
            created = False
        rec = next(d for d in self.decisions() if d.decision_id == action_id)
        return rec, created

    def _exit(
        self,
        action: PositionAction,
        action_id: str,
        position_id: str,
        price: Decimal,
        qty: Decimal,
        fill_ms: int,
        fees: Decimal | None,
        note: str | None,
        _fail_after_event: bool = False,
    ) -> tuple[ManualPosition, bool]:
        payload = {
            "price": str(price),
            "qty": _norm(qty),
            "fill_ms": fill_ms,
            "fees": None if fees is None else str(fees),
            "note": note or None,
        }
        content = _content_hash(action.value + position_id, payload)
        if self._existing(action_id, content):
            return self.get(position_id), False  # type: ignore[return-value]
        if price <= 0 or qty <= 0:
            raise JournalError("INVALID_NUMBER", "price and quantity must be > 0")
        if fees is not None and fees < 0:
            raise JournalError("INVALID_NUMBER", "fees must be >= 0")
        pos = self._open_position(position_id)
        if qty > pos.remaining_qty:
            raise JournalError(
                "QTY_EXCEEDS_REMAINING",
                f"quantity {_norm(qty)} exceeds remaining {_norm(pos.remaining_qty)}",
            )
        if action is PositionAction.CLOSE and qty != pos.remaining_qty:
            raise JournalError(
                "CLOSE_QTY_MISMATCH",
                f"close must cover the full remaining {_norm(pos.remaining_qty)}; "
                "use p for a partial close",
            )
        if action is PositionAction.PARTIAL_CLOSE and qty == pos.remaining_qty:
            raise JournalError(
                "PARTIAL_IS_FULL", "quantity equals the remaining size; use x to record a close"
            )
        if fill_ms < pos.entry_ms:
            raise JournalError("TIME_BEFORE_ENTRY", "exit time is before the recorded fill time")
        ev = PositionEventRecord(
            event_id=action_id,
            position_id=position_id,
            sequence=self._next_seq(position_id),
            action=action,
            effective_at_ms=fill_ms,
            recorded_at_ms=self.store.now_ms(),
            qty=qty,
            price=price,
            fees=fees,
            payload=payload | {"content_sha256": content},
        )
        return self._write(ev, fail_after_event=_fail_after_event), True

    def record_partial(self, action_id, position_id, *, price, qty, fill_ms, fees=None, note=None):
        return self._exit(
            PositionAction.PARTIAL_CLOSE, action_id, position_id, price, qty, fill_ms, fees, note
        )

    def record_close(self, action_id, position_id, *, price, qty, fill_ms, fees=None, note=None):
        return self._exit(
            PositionAction.CLOSE, action_id, position_id, price, qty, fill_ms, fees, note
        )

    def record_modify(
        self,
        action_id: str,
        position_id: str,
        *,
        effective_ms: int,
        new_stop: Decimal | None = None,
        new_target: Decimal | None = None,
        note: str | None = None,
    ) -> tuple[ManualPosition, bool]:
        payload = {
            "new_stop": None if new_stop is None else str(new_stop),
            "new_target": None if new_target is None else str(new_target),
            "effective_ms": effective_ms,
            "note": note or None,
        }
        content = _content_hash("MODIFY" + position_id, payload)
        if self._existing(action_id, content):
            return self.get(position_id), False  # type: ignore[return-value]
        if new_stop is None and new_target is None:
            raise JournalError("MISSING_VALUE", "enter a new stop and/or target")
        for v in (new_stop, new_target):
            if v is not None and v <= 0:
                raise JournalError("INVALID_NUMBER", "stop/target must be > 0")
        pos = self._open_position(position_id)
        if effective_ms < pos.entry_ms:
            raise JournalError("TIME_BEFORE_ENTRY", "effective time is before the fill time")
        payload["further_away"] = stop_further_away(pos, new_stop)
        ev = PositionEventRecord(
            event_id=action_id,
            position_id=position_id,
            sequence=self._next_seq(position_id),
            action=PositionAction.MODIFY,
            effective_at_ms=effective_ms,
            recorded_at_ms=self.store.now_ms(),
            qty=None,
            price=None,
            fees=None,
            payload=payload | {"content_sha256": content},
        )
        return self._write(ev), True

    def confirm_open(
        self, action_id: str, position_id: str, *, effective_ms: int, note: str | None = None
    ) -> tuple[ManualPosition, bool]:
        """Operator verified at the broker that the position is open exactly as recorded."""
        payload = {"effective_ms": effective_ms, "note": note or None}
        content = _content_hash("CONFIRMED_OPEN" + position_id, payload)
        if self._existing(action_id, content):
            return self.get(position_id), False  # type: ignore[return-value]
        pos = self._open_position(position_id)
        if pos.state is not PositionState.RECONCILIATION_REQUIRED:
            raise JournalError("NOT_REQUIRED", f"{position_id} does not need reconciliation")
        ev = PositionEventRecord(
            action_id,
            position_id,
            self._next_seq(position_id),
            PositionAction.CONFIRMED_OPEN,
            effective_ms,
            self.store.now_ms(),
            None,
            None,
            None,
            payload | {"content_sha256": content},
        )
        return self._write(ev), True

    def restore_on_startup(self) -> list[ManualPosition]:
        """docs/07 §8: every open position becomes RECONCILIATION_REQUIRED at program
        start; already-unverified positions are left as they are (no duplicate events)."""
        restored = []
        for pos in self.open_positions():
            if pos.state is PositionState.MONITORING:
                now = self.store.now_ms()
                ev = PositionEventRecord(
                    new_action_id(),
                    pos.position_id,
                    self._next_seq(pos.position_id),
                    PositionAction.RESTORED_UNVERIFIED,
                    now,
                    now,
                    None,
                    None,
                    None,
                    {"reason": "PROGRAM_RESTART", "note": "verify at broker"},
                )
                pos = self._write(ev)
            restored.append(pos)
        return restored


def stop_further_away(pos: ManualPosition, new_stop: Decimal | None) -> bool:
    """docs/02 §9 Modify: warn when the stop moves further from the entry (more risk)."""
    if new_stop is None or pos.current_sl is None:
        return False
    return (pos.current_sl - new_stop) * _sign(pos.side) > 0


def current_risk(pos: ManualPosition, stop: Decimal | None) -> Decimal | None:
    """Gross price risk per unit from actual entry to a stop (UNKNOWN when not protective)."""
    if stop is None:
        return None
    risk = (pos.entry_price - stop) * _sign(pos.side)
    return risk if risk > 0 else None


def exit_preview(
    pos: ManualPosition, price: Decimal, qty: Decimal
) -> tuple[Decimal, Decimal, Decimal | None]:
    """(remaining after exit, realized gross price units, realized gross R vs full initial risk)."""
    units = (price - pos.entry_price) * _sign(pos.side) * qty
    r = _div(units, pos.initial_risk * pos.initial_qty) if pos.initial_risk else None
    return pos.remaining_qty - qty, units, r
