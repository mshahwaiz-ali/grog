"""S1 Trend Pullback research detector, exactly docs/05 Sections 3-6 (S1 v0.2-proposal).

RESEARCH ONLY: deterministic offline/synthetic replay. Produces candidate state
transitions and immutable closed-bar **trigger observations**. It never issues a
READY signal (first executable quote and eligibility are docs/06, milestone M05),
never sizes or places orders, and never uses an incomplete or not-yet-available bar.

Feed it the events produced by ``BarAggregator.on_quote`` together with the quote
that produced them (:meth:`S1Detector.process`). All bars of a batch are first given
to the analysis engine, then M5 bars are evaluated at their ``available_at_ms`` and
finally the quote's BID is checked against the frozen structural endpoints.

Conventions chosen where docs/05 is silent (documented in the M04 report):

* Bar counts ("<= 12 bars", ">= 2 post-pivot bars", "> 12 post-pivot bars") count
  finalized M5 bars in series order; missing buckets are never fabricated.
* A pair whose pivots or intervening bars are irregular (GAPPED / non-contiguous)
  is rejected with ``DATA_GAP``; a trigger needs bars j, j-1, j-2 COMPLETE and contiguous.
* Order per M5 bar: update P (including the bar), structural/depth invalidation,
  TTL expiry, then trigger; afterwards pivots newly confirmed by the bar form pairs.
* At most one trigger observation per candidate (no duplicate on later bars).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal
from typing import Any

from grog.analysis.contexts import AnalysisEngine
from grog.analysis.params import CALC_CONTEXT, S1_RESEARCH_V0_2, AnalysisParams
from grog.domain.enums import (
    TERMINAL_CANDIDATE_STATES,
    BarQuality,
    CandidateState,
    H1Bias,
    IndicatorStatus,
    M15Context,
    PivotSide,
    ReasonCode,
    S1EventKind,
    Side,
    Timeframe,
)
from grog.domain.ids import canonical_json, sha256_hex
from grog.domain.models import (
    AnalysisContext,
    FinalizedBar,
    FrozenPair,
    NormalizedQuote,
    Pivot,
    S1Candidate,
    S1Event,
    TriggerObservation,
)

R = ReasonCode
M5 = Timeframe.M5


@dataclass(frozen=True, slots=True)
class S1Params:
    """S1 v0.2 **proposed research** values (docs/05 Sections 4-6). Not validated."""

    strategy_id: str = "S1"
    strategy_version: str = "v0.2-proposal"
    impulse_atr_multiple: Decimal = Decimal("1.0")  # I >= 1.0 * ATR14_M5
    max_impulse_bars: int = 12  # (H.index - L.index) <= 12
    min_post_pivot_bars: int = 2
    depth_min: Decimal = Decimal("0.25")
    depth_max: Decimal = Decimal("0.75")
    max_forming_post_bars: int = 12  # expires after MORE than 12 post-pivot bars
    trigger_lookback_bars: int = 2  # previous two finalized M5 bars
    analysis: AnalysisParams = field(default=S1_RESEARCH_V0_2)

    @property
    def parameter_set_hash(self) -> str:
        data = {k: str(v) if isinstance(v, Decimal) else v for k, v in asdict(self).items()}
        data["analysis"] = self.analysis.parameter_set_hash
        return sha256_hex(canonical_json(data).encode())


S1_V0_2 = S1Params()

_HEALTH_TERMINAL = {R.STRUCTURE_INVALIDATED, R.PULLBACK_INVALID}


class S1Detector:
    def __init__(
        self,
        source_id: str,
        params: S1Params = S1_V0_2,
        engine: AnalysisEngine | None = None,
    ) -> None:
        self.source_id = source_id
        self.params = params
        self.engine = engine or AnalysisEngine(source_id, params.analysis)
        if self.engine.source_id != source_id:
            raise ValueError("analysis engine belongs to another source")
        self.parameter_set_hash = params.parameter_set_hash
        self.m5: list[FinalizedBar] = []
        self.m5_pivots: list[Pivot] = []
        self.active: dict[Side, S1Candidate] = {}
        self.candidates: dict[str, S1Candidate] = {}
        self.events: list[S1Event] = []
        self._seen_pairs: set[tuple[str, ...]] = set()

    # ------------------------------------------------------------------ input

    def process(self, events: list[object], quote: NormalizedQuote | None = None) -> list[S1Event]:
        """One aggregator step: bars (and gap records, ignored) finalized by ``quote``."""
        bars = [e for e in events if isinstance(e, FinalizedBar)]
        new_pivots: dict[str, list[Pivot]] = {}
        for bar in bars:
            pivots = self.engine.on_bar(bar)
            if bar.timeframe is M5:
                new_pivots[bar.bar_id] = [p for p in pivots if p.timeframe is M5]
        out: list[S1Event] = []
        for bar in bars:
            if bar.timeframe is M5:
                out += self._on_m5(bar, new_pivots[bar.bar_id])
        if quote is not None:
            out += self._on_quote(quote)
        return out

    def on_bar(self, bar: FinalizedBar) -> list[S1Event]:
        return self.process([bar])

    def on_quote(self, quote: NormalizedQuote) -> list[S1Event]:
        return self.process([], quote)

    # ------------------------------------------------------------------ helpers

    def _irregular(self, i: int) -> bool:
        bar = self.m5[i]
        if bar.quality is not BarQuality.COMPLETE:
            return True
        return i > 0 and bar.start_ms != self.m5[i - 1].end_ms

    def _any_irregular(self, lo: int, hi: int) -> bool:
        return any(self._irregular(i) for i in range(max(lo, 0), min(hi, len(self.m5) - 1) + 1))

    def _emit(
        self,
        kind: S1EventKind,
        side: Side,
        ctx: AnalysisContext,
        event_time_ms: int,
        reasons: list[ReasonCode],
        *,
        before: S1Candidate | None = None,
        after: S1Candidate | None = None,
        pair: FrozenPair | None = None,
        trigger: TriggerObservation | None = None,
    ) -> S1Event:
        cand = after or before
        m15 = ctx.m15_buy if side is Side.BUY else ctx.m15_sell
        atr = ctx.atr_values[0]
        seq = len(self.events)
        pair_key = cand.pair.pair_key if cand else pair.pair_key if pair else None
        event = S1Event(
            event_id=f"S1:{self.source_id}:{seq:08d}:{kind.value}",
            sequence=seq,
            kind=kind,
            strategy_id=self.params.strategy_id,
            strategy_version=self.params.strategy_version,
            source_id=self.source_id,
            side=side,
            decision_time_ms=ctx.decision_time_ms,
            event_time_ms=event_time_ms,
            candidate_id=cand.candidate_id if cand else None,
            pair_key=pair_key,
            previous_state=before.state if before else None,
            new_state=after.state if after else None,
            reason_codes=tuple(reasons),
            h1_bias=ctx.h1_bias,
            m15_context=m15.context,
            last_confirmed_h1_id=ctx.last_confirmed_h1_id,
            last_confirmed_m15_id=ctx.last_confirmed_m15_id,
            last_confirmed_m5_id=ctx.last_confirmed_m5_id,
            atr_m5=atr.value,
            pullback_extreme=cand.pullback_extreme if cand else None,
            depth=cand.depth if cand else None,
            post_pivot_bars=cand.post_pivot_bars if cand else None,
            trigger=trigger,
            quality_flags=ctx.quality_flags,
            parameter_set_hash=self.parameter_set_hash,
        )
        self.events.append(event)
        return event

    def _store(self, cand: S1Candidate) -> S1Candidate:
        self.candidates[cand.candidate_id] = cand
        if cand.state in TERMINAL_CANDIDATE_STATES:
            if self.active.get(cand.side) is not None and (
                self.active[cand.side].candidate_id == cand.candidate_id
            ):
                del self.active[cand.side]
        else:
            self.active[cand.side] = cand
        return cand

    @staticmethod
    def _soft(side: Side, ctx: AnalysisContext) -> list[ReasonCode]:
        m15 = (ctx.m15_buy if side is Side.BUY else ctx.m15_sell).context
        return {
            M15Context.CORRECTIVE: [R.M15_CORRECTIVE],
            M15Context.OPPOSING: [R.M15_OPPOSING],
            M15Context.UNKNOWN: [R.M15_UNKNOWN],
        }.get(m15, [])

    def _pullback(self, pair: FrozenPair, j: int) -> tuple[Decimal, Decimal, int, ReasonCode]:
        """P, depth and health over completed post-pivot bars up to and including j."""
        p = self.params
        final = pair.final_pivot
        post = self.m5[final.bar_index + 1 : j + 1]
        if pair.side is Side.BUY:
            extreme = min(b.low_bid for b in post)
            depth = CALC_CONTEXT.divide(pair.high.price - extreme, pair.impulse)
            broken = extreme <= pair.low.price
        else:
            extreme = max(b.high_bid for b in post)
            depth = CALC_CONTEXT.divide(extreme - pair.low.price, pair.impulse)
            broken = extreme >= pair.high.price
        if broken:
            health = R.STRUCTURE_INVALIDATED
        elif depth > p.depth_max:
            health = R.PULLBACK_INVALID
        elif len(post) < p.min_post_pivot_bars:
            health = R.PULLBACK_TOO_FEW_BARS
        elif depth < p.depth_min:
            health = R.PULLBACK_SHALLOW
        else:
            health = R.PULLBACK_HEALTHY
        return extreme, depth, len(post), health

    # ------------------------------------------------------------------ M5 bar

    def _on_m5(self, bar: FinalizedBar, pivots: list[Pivot]) -> list[S1Event]:
        self.m5.append(bar)
        j = len(self.m5) - 1
        ctx = self.engine.context(bar.available_at_ms)
        if ctx.last_confirmed_m5_id != bar.bar_id:
            raise ValueError("M5 bars must be processed in availability order")
        out: list[S1Event] = []
        for side in (Side.BUY, Side.SELL):
            cand = self.active.get(side)
            if cand is not None:
                out += self._advance(cand, bar, j, ctx)
        for pivot in pivots:
            out += self._on_pivot(pivot, bar, ctx)
        self.m5_pivots.extend(pivots)
        return out

    def _advance(
        self, cand: S1Candidate, bar: FinalizedBar, j: int, ctx: AnalysisContext
    ) -> list[S1Event]:
        p, pair, side = self.params, cand.pair, cand.side
        extreme, depth, count, health = self._pullback(pair, j)
        progressed = replace(
            cand,
            pullback_extreme=extreme,
            depth=depth,
            post_pivot_bars=count,
            last_closed_m5_id=bar.bar_id,
            last_changed_ms=bar.available_at_ms,
        )
        if health in _HEALTH_TERMINAL:
            done = self._store(
                replace(progressed, state=CandidateState.INVALIDATED, reason_codes=(health,))
            )
            return [
                self._emit(
                    S1EventKind.INVALIDATED,
                    side,
                    ctx,
                    bar.end_ms,
                    [health],
                    before=cand,
                    after=done,
                )
            ]
        if count > p.max_forming_post_bars:
            reasons = [R.FORMING_TTL_EXPIRED]
            done = self._store(
                replace(progressed, state=CandidateState.EXPIRED, reason_codes=tuple(reasons))
            )
            return [
                self._emit(
                    S1EventKind.EXPIRED, side, ctx, bar.end_ms, reasons, before=cand, after=done
                )
            ]

        reasons: list[ReasonCode] = [health]
        trigger: TriggerObservation | None = None
        if cand.trigger is not None:
            reasons.append(R.TRIGGER_ALREADY_OBSERVED)
        else:
            blocking = self._trigger_blockers(cand, bar, j, ctx)
            reasons += blocking
            if not blocking and health is R.PULLBACK_HEALTHY:
                trigger = self._make_trigger(cand, bar, j, ctx, extreme, depth)
                reasons.append(R.TRIGGER_CONFIRMED)
        reasons += self._soft(side, ctx)
        updated = self._store(
            replace(progressed, reason_codes=tuple(reasons), trigger=cand.trigger or trigger)
        )
        out = [
            self._emit(
                S1EventKind.CANDIDATE_UPDATED,
                side,
                ctx,
                bar.end_ms,
                reasons,
                before=cand,
                after=updated,
            )
        ]
        if trigger is not None:
            out.append(
                self._emit(
                    S1EventKind.TRIGGER_OBSERVED,
                    side,
                    ctx,
                    bar.end_ms,
                    [R.TRIGGER_CONFIRMED, *self._soft(side, ctx)],
                    before=updated,
                    after=updated,
                    trigger=trigger,
                )
            )
        return out

    def _trigger_blockers(
        self,
        cand: S1Candidate,
        bar: FinalizedBar,
        j: int,
        ctx: AnalysisContext,
    ) -> list[ReasonCode]:
        p, pair = self.params, cand.pair
        blockers: list[ReasonCode] = []
        if bar.available_at_ms <= pair.available_at_ms or j <= pair.final_pivot.bar_index + 2:
            blockers.append(R.TRIGGER_NOT_ELIGIBLE_BAR)
        wanted = H1Bias.UP if cand.side is Side.BUY else H1Bias.DOWN
        if ctx.h1_bias is not wanted:
            blockers.append(R.H1_BIAS_MISMATCH)
            if ctx.h1_bias is H1Bias.UNKNOWN:
                blockers.append(R.HISTORY_INCOMPLETE)
        n = p.trigger_lookback_bars
        if j < n or self._any_irregular(j - n, j):
            blockers.append(R.DATA_GAP)
        else:
            prev = self.m5[j - n : j]
            if cand.side is Side.BUY:
                closes_beyond = bar.close_bid > max(b.high_bid for b in prev)
                body_ok = bar.close_bid > bar.open_bid
            else:
                closes_beyond = bar.close_bid < min(b.low_bid for b in prev)
                body_ok = bar.close_bid < bar.open_bid
            if not closes_beyond:
                blockers.append(R.TRIGGER_CLOSE_NOT_BEYOND)
            if not body_ok:
                blockers.append(R.TRIGGER_BODY_WRONG_DIRECTION)
        return blockers

    def _make_trigger(
        self,
        cand: S1Candidate,
        bar: FinalizedBar,
        j: int,
        ctx: AnalysisContext,
        extreme: Decimal,
        depth: Decimal,
    ) -> TriggerObservation:
        n = self.params.trigger_lookback_bars
        prev = self.m5[j - n : j]
        if cand.side is Side.BUY:
            threshold = max(b.high_bid for b in prev)
            m15 = ctx.m15_buy
        else:
            threshold = min(b.low_bid for b in prev)
            m15 = ctx.m15_sell
        atr = ctx.atr_values[0]
        return TriggerObservation(
            trigger_id="S1T-" + sha256_hex(f"{cand.candidate_id}|{bar.bar_id}".encode())[:20],
            candidate_id=cand.candidate_id,
            side=cand.side,
            trigger_bar_id=bar.bar_id,
            trigger_bar_end_ms=bar.end_ms,
            available_at_ms=bar.available_at_ms,
            trigger_open_bid=bar.open_bid,
            trigger_close_bid=bar.close_bid,
            two_bar_threshold=threshold,
            reference_bar_ids=(self.m5[j - 1].bar_id, self.m5[j - 2].bar_id),
            pullback_extreme=extreme,
            depth=depth,
            atr_m5=atr.value,
            atr_m5_status=atr.status,
            h1_bias=ctx.h1_bias,
            m15_context=m15.context,
            m15_reference_pivot_id=m15.reference_pivot_id,
        )

    # ------------------------------------------------------------------ pivots / pairs

    def _on_pivot(self, pivot: Pivot, bar: FinalizedBar, ctx: AnalysisContext) -> list[S1Event]:
        p = self.params
        side = Side.BUY if pivot.side is PivotSide.HIGH else Side.SELL
        want = PivotSide.LOW if side is Side.BUY else PivotSide.HIGH
        prior = [q for q in self.m5_pivots if q.side is want and q.bar_index < pivot.bar_index]
        if not prior:
            return [
                self._emit(
                    S1EventKind.PAIR_REJECTED,
                    side,
                    ctx,
                    pivot.confirmed_at_ms,
                    [R.NO_PRECEDING_PIVOT],
                )
            ]
        other = max(prior, key=lambda q: q.bar_index)
        low, high = (other, pivot) if side is Side.BUY else (pivot, other)
        impulse = high.price - low.price
        span = pivot.bar_index - other.bar_index
        atr = ctx.atr_values[0]
        reasons: list[ReasonCode] = []
        if impulse <= 0:
            reasons.append(R.IMPULSE_NOT_POSITIVE)
        if atr.status is IndicatorStatus.INSUFFICIENT_HISTORY or atr.value is None:
            reasons.append(R.M5_ATR_UNAVAILABLE)
        elif atr.status is IndicatorStatus.ZERO_VALUE:
            reasons.append(R.M5_ATR_ZERO)
        elif impulse > 0 and impulse < p.impulse_atr_multiple * atr.value:
            reasons.append(R.IMPULSE_BELOW_ATR)
        if span > p.max_impulse_bars:
            reasons.append(R.IMPULSE_TOO_OLD)
        if (
            low.window_irregular
            or high.window_irregular
            or self._any_irregular(other.bar_index - 2, pivot.bar_index + 2)
        ):
            reasons.append(R.DATA_GAP)
        pair = FrozenPair(
            strategy_version=p.strategy_version,
            side=side,
            low=low,
            high=high,
            impulse=impulse,
            atr_m5=atr.value if atr.value is not None else Decimal(0),
            impulse_bars=span,
            confirmed_at_ms=pivot.confirmed_at_ms,
            available_at_ms=pivot.available_at_ms,
        )
        if not reasons and pair.pair_key in self._seen_pairs:
            reasons.append(R.DUPLICATE_PAIR)
        if reasons:
            return [
                self._emit(
                    S1EventKind.PAIR_REJECTED, side, ctx, pivot.confirmed_at_ms, reasons, pair=pair
                )
            ]
        self._seen_pairs.add(pair.pair_key)

        out: list[S1Event] = []
        old = self.active.get(side)
        if old is not None:
            gone = self._store(
                replace(
                    old,
                    state=CandidateState.SUPERSEDED,
                    reason_codes=(R.SUPERSEDED_BY_NEWER_PAIR,),
                    last_changed_ms=pivot.available_at_ms,
                )
            )
            out.append(
                self._emit(
                    S1EventKind.SUPERSEDED,
                    side,
                    ctx,
                    pivot.confirmed_at_ms,
                    [R.SUPERSEDED_BY_NEWER_PAIR],
                    before=old,
                    after=gone,
                )
            )

        j = len(self.m5) - 1
        extreme, depth, count, health = self._pullback(pair, j)
        ident = canonical_json(
            [
                self.source_id,
                p.strategy_id,
                p.strategy_version,
                side.value,
                low.pivot_id,
                high.pivot_id,
            ]
        )
        cand = S1Candidate(
            candidate_id=f"S1-{side.value}-" + sha256_hex(ident.encode())[:20],
            strategy_id=p.strategy_id,
            strategy_version=p.strategy_version,
            source_id=self.source_id,
            side=side,
            state=CandidateState.FORMING,
            pair=pair,
            pullback_extreme=extreme,
            depth=depth,
            post_pivot_bars=count,
            last_closed_m5_id=bar.bar_id,
            first_detected_ms=pivot.available_at_ms,
            last_changed_ms=pivot.available_at_ms,
            reason_codes=(health, *self._soft(side, ctx)),
            trigger=None,
            parameter_set_hash=self.parameter_set_hash,
            source_origin=bar.source_origin,
        )
        created = self._store(cand)
        out.append(
            self._emit(
                S1EventKind.CANDIDATE_CREATED,
                side,
                ctx,
                pivot.confirmed_at_ms,
                list(cand.reason_codes),
                after=created,
            )
        )
        if health in _HEALTH_TERMINAL:
            done = self._store(
                replace(created, state=CandidateState.INVALIDATED, reason_codes=(health,))
            )
            out.append(
                self._emit(
                    S1EventKind.INVALIDATED,
                    side,
                    ctx,
                    pivot.confirmed_at_ms,
                    [health],
                    before=created,
                    after=done,
                )
            )
        return out

    # ------------------------------------------------------------------ quotes

    def _on_quote(self, quote: NormalizedQuote) -> list[S1Event]:
        """Hard structural invalidation on an actually observed BID (docs/05 Section 5)."""
        if quote.source_id != self.source_id:
            raise ValueError("quote from another source")
        out: list[S1Event] = []
        ctx: AnalysisContext | None = None
        for side in (Side.BUY, Side.SELL):
            cand = self.active.get(side)
            if cand is None or quote.received_time_ms < cand.pair.available_at_ms:
                continue
            pair = cand.pair
            hit = (
                (quote.bid <= pair.low.price)
                if side is Side.BUY
                else (quote.bid >= pair.high.price)
            )
            if not hit:
                continue
            ctx = ctx or self.engine.context(quote.received_time_ms)
            done = self._store(
                replace(
                    cand,
                    state=CandidateState.INVALIDATED,
                    reason_codes=(R.STRUCTURE_INVALIDATED,),
                    last_changed_ms=quote.received_time_ms,
                )
            )
            out.append(
                self._emit(
                    S1EventKind.INVALIDATED,
                    side,
                    ctx,
                    quote.provider_time_ms,
                    [R.STRUCTURE_INVALIDATED],
                    before=cand,
                    after=done,
                )
            )
        return out


def record_to_dict(value: Any) -> Any:
    """Canonical, exact (Decimal as string) serialization for replay comparison."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (tuple, list)):
        return [record_to_dict(v) for v in value]
    if hasattr(value, "__dataclass_fields__"):
        out = {k: record_to_dict(getattr(value, k)) for k in value.__dataclass_fields__}
        if hasattr(value, "pivot_id"):
            out["pivot_id"] = value.pivot_id
        return out
    return value
