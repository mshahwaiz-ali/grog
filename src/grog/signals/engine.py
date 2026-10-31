"""S1 signal eligibility on the first executable post-trigger quote (docs/06 Sections 2-5).

* The trigger bar's close is never an entry: the first quote received at/after the
  trigger's availability is the only issuance candidate (docs/03 Section 1, docs/06 §4).
* Every hard gate is recorded as PASS / FAIL / UNKNOWN / NOT_APPLICABLE. READY needs all
  blocking gates PASS. OPEN thresholds left unset give UNKNOWN, which never issues READY:
  feed staleness (DataHealthPolicy.max_quote_age_ms), maximum first-quote delay
  (DataHealthPolicy.max_first_postclose_delay_ms) and the declared synthetic price step.
* Spread limit and cost model are OPEN execution-policy gates: when unset they are
  recorded UNKNOWN as non-blocking evidence for SIMULATED research output (docs/06 §3);
  when declared they are enforced. Net R stays UNKNOWN without a declared cost model.
* One READY per candidate/pair, ever. Overlay EXECUTION_BLOCKED is reversible and keeps
  the same signal ID, original prices and expiry; stop touch, structural break, H1
  mismatch and TTL are terminal.
* No score, no probability, no lot sizing, no order placement. Output is SIMULATED.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from decimal import Decimal

from grog.domain.enums import (
    CandidateState,
    ExecutionFidelity,
    FeedStatus,
    GapKind,
    GateResult,
    H1Bias,
    IndicatorStatus,
    M15Context,
    ReasonCode,
    S1EventKind,
    Side,
    SignalEventKind,
    SignalState,
    Timeframe,
)
from grog.domain.ids import canonical_json, sha256_hex
from grog.domain.models import (
    DataHealthPolicy,
    FinalizedBar,
    GapRecord,
    GateCheck,
    NormalizedQuote,
    S1Event,
    SignalEvent,
    SignalRecord,
    TriggerObservation,
)
from grog.market_data.bars import bucket_start
from grog.market_data.health import FeedHealth
from grog.risk.quotes_and_plans import (
    RESEARCH_RISK_V0_2,
    CostModel,
    RiskParams,
    TradePlan,
    build_plan,
    confirmation_retained,
    in_entry_band,
    no_chase_ok,
    stop_touched,
)
from grog.strategies.s1_pullback import S1Detector, record_to_dict

R = ReasonCode
G = GateResult
M5 = Timeframe.M5

_FEED_FAIL = {
    FeedStatus.STALE: R.DATA_STALE,
    FeedStatus.NO_DATA: R.DATA_STALE,
    FeedStatus.DEGRADED: R.DATA_GAP,
    FeedStatus.CLOSED: R.MARKET_CLOSED,
}


@dataclass(frozen=True, slots=True)
class SignalPolicy:
    """Eligibility configuration. Every OPEN threshold defaults to unset (docs/11)."""

    rules_version: str = "S1_SIGNAL_V0_2/eligibility-1"
    health: DataHealthPolicy = field(default_factory=DataHealthPolicy)
    price_step: Decimal | None = None  # declared synthetic increment only (docs/07 §2)
    max_spread: Decimal | None = None  # OPEN
    cost_model: CostModel | None = None  # OPEN
    m15_opposing_strict_veto: bool = False  # separately versioned experiment (SQ-05)
    risk: RiskParams = RESEARCH_RISK_V0_2

    def __post_init__(self) -> None:
        if self.price_step is not None and self.price_step <= 0:
            raise ValueError("price_step must be positive")
        if self.max_spread is not None and self.max_spread < 0:
            raise ValueError("max_spread must be >= 0")

    @property
    def effective_rules_version(self) -> str:
        return self.rules_version + ("+M15_STRICT_VETO" if self.m15_opposing_strict_veto else "")

    @property
    def parameter_set_hash(self) -> str:
        return sha256_hex(canonical_json(record_to_dict(asdict(self))).encode())


@dataclass(slots=True)
class SignalStatus:
    """Mutable current read model (overlay); the SignalRecord itself never changes."""

    state: SignalState
    blocked_reasons: tuple[ReasonCode, ...] = ()
    last_evaluated_ms: int = 0
    terminal_reason: ReasonCode | None = None

    @property
    def blocked(self) -> bool:
        return bool(self.blocked_reasons)


class SignalEngine:
    def __init__(self, detector: S1Detector, policy: SignalPolicy | None = None) -> None:
        self.detector = detector
        self.source_id = detector.source_id
        self.policy = policy or SignalPolicy()
        self.parameter_set_hash = sha256_hex(
            f"{self.policy.parameter_set_hash}|{detector.parameter_set_hash}".encode()
        )
        self.signals: dict[str, SignalRecord] = {}
        self.status: dict[str, SignalStatus] = {}
        self.events: list[SignalEvent] = []
        self._pending: list[TriggerObservation] = []
        self._seen_triggers: set[str] = set()
        self._issued_by_candidate: dict[str, str] = {}
        self._triggers: dict[str, TriggerObservation] = {}
        self.plans: dict[str, TradePlan] = {}

    # ------------------------------------------------------------------ public

    def live_signal_ids(self) -> list[str]:
        return [sid for sid, st in self.status.items() if st.state is SignalState.READY]

    def on_step(
        self,
        quote: NormalizedQuote,
        bar_events: Sequence[object],
        s1_events: Sequence[S1Event],
        health: FeedHealth,
    ) -> list[SignalEvent]:
        """One causal step: everything known at ``quote.received_time_ms``."""
        if quote.source_id != self.source_id:
            raise ValueError("quote from another source")
        out: list[SignalEvent] = []
        h1_changed = any(
            isinstance(b, FinalizedBar) and b.timeframe is Timeframe.H1 for b in bar_events
        )
        for sid in self.live_signal_ids():
            out += self._monitor(self.signals[sid], quote, health, h1_changed)
        for ev in s1_events:
            trig = ev.trigger
            if ev.kind is not S1EventKind.TRIGGER_OBSERVED or trig is None:
                continue
            if trig.trigger_id in self._seen_triggers:
                continue  # replayed / duplicate observation (ST-02, ADV-10)
            self._seen_triggers.add(trig.trigger_id)
            self._pending.append(trig)
        gaps = [g for g in bar_events if isinstance(g, GapRecord)]
        still: list[TriggerObservation] = []
        for trig in self._pending:
            if (
                quote.received_time_ms < trig.available_at_ms
                or quote.provider_time_ms < trig.trigger_bar_end_ms
            ):
                still.append(trig)
                continue
            out += self._first_quote(trig, quote, gaps, health)
        self._pending = still
        return out

    # ------------------------------------------------------------------ helpers

    def _emit(
        self,
        kind: SignalEventKind,
        trig: TriggerObservation,
        quote: NormalizedQuote,
        *,
        signal: SignalRecord | None = None,
        state: SignalState | None = None,
        blocked: bool = False,
        reasons: Sequence[ReasonCode] = (),
        gates: Sequence[GateCheck] = (),
        event_time_ms: int | None = None,
    ) -> SignalEvent:
        seq = len(self.events)
        ev = SignalEvent(
            event_id=f"SIG:{self.source_id}:{seq:08d}:{kind.value}",
            sequence=seq,
            kind=kind,
            source_id=self.source_id,
            side=trig.side,
            candidate_id=trig.candidate_id,
            trigger_id=trig.trigger_id,
            signal_id=signal.signal_id if signal else None,
            decision_time_ms=quote.received_time_ms,
            event_time_ms=quote.provider_time_ms if event_time_ms is None else event_time_ms,
            state=state,
            blocked=blocked,
            reason_codes=tuple(reasons),
            gates=tuple(gates),
            quote_bid=quote.bid,
            quote_ask=quote.ask,
        )
        self.events.append(ev)
        return ev

    @staticmethod
    def _required_bias(side: Side) -> H1Bias:
        return H1Bias.UP if side is Side.BUY else H1Bias.DOWN

    def _feed_reason(self, health: FeedHealth) -> tuple[GateResult, ReasonCode | None]:
        if health.status is FeedStatus.FRESH:
            return G.PASS, None
        if health.status is FeedStatus.UNKNOWN:
            return G.UNKNOWN, R.FEED_HEALTH_UNKNOWN
        return G.FAIL, _FEED_FAIL[health.status]

    # ------------------------------------------------------------------ first quote

    def _first_quote(
        self,
        trig: TriggerObservation,
        quote: NormalizedQuote,
        gaps: Sequence[GapRecord],
        health: FeedHealth,
    ) -> list[SignalEvent]:
        p, side = self.policy, trig.side
        gates: list[GateCheck] = []

        def gate(
            name: str, result: GateResult, reason: ReasonCode | None = None, blocking: bool = True
        ) -> None:
            gates.append(GateCheck(name, result, reason, blocking))

        if trig.candidate_id in self._issued_by_candidate:
            gate("DUPLICATE_PAIR", G.FAIL, R.DUPLICATE_PAIR)
        else:
            gate("DUPLICATE_PAIR", G.PASS)

        # 1. data: feed health, gap between trigger close and this quote, measured delay
        result, reason = self._feed_reason(health)
        gate("FEED_HEALTH", result, reason)
        post_close = [
            g for g in gaps if g.timeframe is Timeframe.M1 and g.to_ms > trig.trigger_bar_end_ms
        ]
        delay = quote.received_time_ms - trig.trigger_bar_end_ms
        limit = p.health.max_first_postclose_delay_ms
        if any(g.kind is GapKind.DATA_GAP for g in post_close):
            gate("FIRST_QUOTE_DELAY", G.FAIL, R.DATA_GAP)
        elif post_close:
            gate("FIRST_QUOTE_DELAY", G.FAIL, R.MARKET_CLOSED)
        elif limit is None:
            gate("FIRST_QUOTE_DELAY", G.UNKNOWN, R.QUOTE_DELAY_UNEVALUATED)
        elif delay > limit:
            gate("FIRST_QUOTE_DELAY", G.FAIL, R.QUOTE_DELAY)
        else:
            gate("FIRST_QUOTE_DELAY", G.PASS)

        # 2. thesis still valid at decision time
        cand = self.detector.candidates.get(trig.candidate_id)
        if cand is None or cand.state is not CandidateState.FORMING:
            gate("CANDIDATE_ACTIVE", G.FAIL, R.CANDIDATE_NOT_ACTIVE)
        else:
            gate("CANDIDATE_ACTIVE", G.PASS)
        ctx = self.detector.engine.context(quote.received_time_ms)
        if ctx.h1_bias is self._required_bias(side):
            gate("H1_DIRECTION", G.PASS)
        else:
            gate("H1_DIRECTION", G.FAIL, R.H1_BIAS_MISMATCH)
        atr = ctx.atr_values[0]
        atr0 = atr.value if atr.status is IndicatorStatus.VALID else None
        if atr0 is not None:
            gate("M5_ATR", G.PASS)
        else:
            gate(
                "M5_ATR",
                G.FAIL,
                R.M5_ATR_ZERO if atr.status is IndicatorStatus.ZERO_VALUE else R.M5_ATR_UNAVAILABLE,
            )

        # 3. price-side plan on the actual quote
        if p.price_step is None:
            gate("PRICE_STEP", G.UNKNOWN, R.CONTRACT_UNDEFINED)
        else:
            gate("PRICE_STEP", G.PASS)
        e0 = quote.ask if side is Side.BUY else quote.bid
        plan = None
        if atr0 is None:
            gate("NO_CHASE", G.UNKNOWN, R.M5_ATR_UNAVAILABLE)
        elif no_chase_ok(side, e0, trig.trigger_close_bid, atr0, p.risk):
            gate("NO_CHASE", G.PASS)
        else:
            gate("NO_CHASE", G.FAIL, R.ENTRY_CHASE)
        if atr0 is not None and p.price_step is not None:
            stop_ref = trig.pullback_extreme if side is Side.BUY else trig.pullback_ask_extreme
            check = build_plan(
                side, quote, stop_ref, trig.two_bar_threshold, atr0, p.price_step, p.risk
            )
            plan = check.plan
            if plan is None:
                gate("STOP_PLAN", G.FAIL, check.reasons[0])
            else:
                gate("STOP_PLAN", G.PASS)
                if confirmation_retained(plan, quote):
                    gate("CONFIRMATION", G.PASS)
                else:
                    gate("CONFIRMATION", G.FAIL, R.CONFIRMATION_LOST)
        else:
            gate(
                "STOP_PLAN",
                G.UNKNOWN,
                R.CONTRACT_UNDEFINED if atr0 is not None else R.M5_ATR_UNAVAILABLE,
            )

        # 4. execution policy (OPEN) and context variants
        if p.max_spread is None:
            gate("SPREAD", G.UNKNOWN, R.SPREAD_LIMIT_UNSET, blocking=False)
        elif quote.spread <= p.max_spread:
            gate("SPREAD", G.PASS)
        else:
            gate("SPREAD", G.FAIL, R.SPREAD_OVER_LIMIT)
        if p.cost_model is None:
            gate("COST_MODEL", G.UNKNOWN, R.COST_UNAVAILABLE, blocking=False)
        else:
            gate("COST_MODEL", G.PASS, blocking=False)
        m15 = ctx.m15_buy if side is Side.BUY else ctx.m15_sell
        if not p.m15_opposing_strict_veto:
            gate("M15_STRICT_VETO", G.NOT_APPLICABLE, blocking=False)
        elif m15.context is M15Context.OPPOSING:
            gate("M15_STRICT_VETO", G.FAIL, R.M15_STRICT_VETO)
        else:
            gate("M15_STRICT_VETO", G.PASS)
        if self.live_signal_ids():
            gate("EXPOSURE", G.FAIL, R.EXPOSURE_REVIEW_REQUIRED)
        else:
            gate("EXPOSURE", G.PASS)

        soft = {
            M15Context.OPPOSING: R.M15_OPPOSING,
            M15Context.UNKNOWN: R.M15_UNKNOWN,
            M15Context.CORRECTIVE: R.M15_CORRECTIVE,
        }.get(m15.context)
        blocking = [g for g in gates if g.blocking and g.result is not G.PASS]
        reasons = [g.reason for g in blocking if g.reason is not None]
        evidence = [g.reason for g in gates if not g.blocking and g.reason is not None]
        if soft is not None:
            evidence.append(soft)
        if blocking or plan is None:
            failed = {g.reason for g in blocking if g.result is G.FAIL}
            if failed & {R.DATA_GAP, R.QUOTE_DELAY} and any(
                g.gate == "FIRST_QUOTE_DELAY" and g.result is G.FAIL for g in blocking
            ):
                kind = SignalEventKind.MISSED_DATA_GAP
            elif R.ENTRY_CHASE in failed:
                kind = SignalEventKind.MISSED_PRICE_CHASE
            else:
                kind = SignalEventKind.NOT_ISSUED
            return [self._emit(kind, trig, quote, reasons=[*reasons, *evidence], gates=gates)]

        signal_id = "SIG-" + sha256_hex(f"{trig.candidate_id}|{trig.trigger_bar_id}".encode())[:20]
        pair = cand.pair  # type: ignore[union-attr]
        evidence_doc = {
            "pair_key": list(pair.pair_key),
            "impulse": str(pair.impulse),
            "pair_atr_m5": str(pair.atr_m5),
            "trigger": record_to_dict(trig),
            "h1_bias": ctx.h1_bias.value,
            "h1_strength_spread_atr": str(ctx.h1_strength_spread_atr),
            "h1_strength_slope_atr": str(ctx.h1_strength_slope_atr),
            "m15_context": m15.context.value,
            "m15_reference_pivot_id": m15.reference_pivot_id,
            "last_confirmed": [
                ctx.last_confirmed_h1_id,
                ctx.last_confirmed_m15_id,
                ctx.last_confirmed_m5_id,
            ],
            "quality_flags": list(ctx.quality_flags),
            "feed_status": health.status.value,
            "spread": str(quote.spread),
            "first_quote_delay_ms": delay,
            "gates": record_to_dict(gates),
        }
        record = SignalRecord(
            signal_id=signal_id,
            candidate_id=trig.candidate_id,
            trigger_id=trig.trigger_id,
            strategy_version=self.detector.params.strategy_version,
            signal_rules_version=p.effective_rules_version,
            side=side,
            original_source_id=self.source_id,
            first_ready_ms=quote.received_time_ms,
            first_quote_provider_ms=quote.provider_time_ms,
            first_quote_event_key=quote.source_event_key,
            original_bid=quote.bid,
            original_ask=quote.ask,
            e0=plan.e0,
            sl0=plan.sl0,
            tp1=plan.tp1,
            tp2=plan.tp2,
            frozen_atr=plan.atr0,
            entry_low=plan.entry_low,
            entry_high=plan.entry_high,
            retention_threshold=plan.retention_threshold,
            structural_low=pair.low.price,
            structural_high=pair.high.price,
            expiry_ms=bucket_start(quote.provider_time_ms, M5) + M5.duration_ms,
            execution_fidelity=ExecutionFidelity.SIMULATED,
            original_risk_price=plan.risk,
            price_step=plan.price_step,
            exit_policy=plan.exit_policy,
            estimated_cost_model_id=p.cost_model.cost_model_id if p.cost_model else None,
            evidence_snapshot_json=canonical_json(evidence_doc),
            parameter_set_hash=self.parameter_set_hash,
        )
        self.signals[signal_id] = record
        self.status[signal_id] = SignalStatus(
            SignalState.READY, last_evaluated_ms=quote.received_time_ms
        )
        self._issued_by_candidate[trig.candidate_id] = signal_id
        self._triggers[signal_id] = trig
        self.plans[signal_id] = plan
        return [
            self._emit(
                SignalEventKind.READY_ISSUED,
                trig,
                quote,
                signal=record,
                state=SignalState.READY,
                reasons=evidence,
                gates=gates,
            )
        ]

    # ------------------------------------------------------------------ while READY

    def _monitor(
        self, sig: SignalRecord, quote: NormalizedQuote, health: FeedHealth, h1_changed: bool
    ) -> list[SignalEvent]:
        st = self.status[sig.signal_id]
        trig = self._triggers[sig.signal_id]
        st.last_evaluated_ms = quote.received_time_ms

        def terminal(
            kind: SignalEventKind,
            state: SignalState,
            reason: ReasonCode,
            event_time: int | None = None,
        ) -> list[SignalEvent]:
            st.state, st.terminal_reason, st.blocked_reasons = state, reason, ()
            return [
                self._emit(
                    kind,
                    trig,
                    quote,
                    signal=sig,
                    state=state,
                    reasons=[reason],
                    event_time_ms=event_time,
                )
            ]

        if quote.provider_time_ms >= sig.expiry_ms:
            return terminal(
                SignalEventKind.EXPIRED, SignalState.EXPIRED, R.SIGNAL_TTL_EXPIRED, sig.expiry_ms
            )
        if h1_changed:
            bias = self.detector.engine.context(quote.received_time_ms).h1_bias
            if bias is not self._required_bias(sig.side):
                return terminal(
                    SignalEventKind.INVALIDATED, SignalState.INVALIDATED, R.H1_BIAS_MISMATCH
                )
        if stop_touched(sig.side, quote, sig.sl0):
            return terminal(
                SignalEventKind.INVALIDATED, SignalState.INVALIDATED, R.PRE_ENTRY_STOP_TOUCH
            )
        structural = (
            quote.bid <= sig.structural_low
            if sig.side is Side.BUY
            else quote.bid >= sig.structural_high
        )
        if structural:
            return terminal(
                SignalEventKind.INVALIDATED, SignalState.INVALIDATED, R.STRUCTURE_INVALIDATED
            )

        plan = self.plans[sig.signal_id]
        reasons: list[ReasonCode] = []
        if not in_entry_band(plan, quote):
            reasons.append(R.OUTSIDE_ENTRY_BAND)
        if not confirmation_retained(plan, quote):
            reasons.append(R.CONFIRMATION_LOST)
        if self.policy.max_spread is not None and quote.spread > self.policy.max_spread:
            reasons.append(R.SPREAD_OVER_LIMIT)
        result, feed_reason = self._feed_reason(health)
        if result is not G.PASS and feed_reason is not None:
            reasons.append(feed_reason)
        new = tuple(reasons)
        if new == st.blocked_reasons:
            return []
        st.blocked_reasons = new
        kind = SignalEventKind.EXECUTION_BLOCKED if new else SignalEventKind.EXECUTION_UNBLOCKED
        return [
            self._emit(
                kind,
                trig,
                quote,
                signal=sig,
                state=SignalState.READY,
                blocked=bool(new),
                reasons=new,
            )
        ]
