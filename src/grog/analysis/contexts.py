"""No-lookahead MTF analysis engine: H1 bias and M15 context (docs/04 Sections 3, 7, 8).

Feed finalized bars in availability order (as produced by ``BarAggregator``);
query :meth:`AnalysisEngine.context` at any decision time. Only bars, indicator
values and pivots with ``available_at_ms <= decision_time_ms`` are used, so a
context never depends on unfinished or not-yet-received bars. UNKNOWN is
explicit and never replaced by a flattering default.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from grog.analysis.ema_atr import AtrState, EmaState
from grog.analysis.params import CALC_CONTEXT, S1_RESEARCH_V0_2, AnalysisParams
from grog.analysis.pivots import PivotDetector
from grog.domain.enums import (
    TIMEFRAMES,
    BarQuality,
    H1Bias,
    IndicatorStatus,
    M15Context,
    PivotSide,
    Side,
    Timeframe,
)
from grog.domain.models import (
    AnalysisContext,
    FinalizedBar,
    IndicatorValue,
    M15Assessment,
    Pivot,
)

H1, M15, M5 = Timeframe.H1, Timeframe.M15, Timeframe.M5


class _Series:
    """Finalized bars of one timeframe plus per-bar indicator values and gap prefix counts."""

    def __init__(self, timeframe: Timeframe, emas: Iterable[int], atrs: Iterable[int]) -> None:
        self.timeframe = timeframe
        self.bars: list[FinalizedBar] = []
        self.available: list[int] = []
        self.emas = {n: (EmaState(n), []) for n in emas}
        self.atrs = {n: (AtrState(n), []) for n in atrs}
        self.irregular_prefix: list[int] = [0]  # irregular_prefix[i] = irregular bars in [0, i)

    def append(self, bar: FinalizedBar) -> None:
        if self.available and bar.available_at_ms < self.available[-1]:
            raise ValueError("bars must be fed in availability order")
        if self.bars and bar.start_ms <= self.bars[-1].start_ms:
            raise ValueError("bars must arrive in increasing start order")
        irregular = bar.quality is not BarQuality.COMPLETE or (
            bool(self.bars) and bar.start_ms != self.bars[-1].end_ms
        )
        self.bars.append(bar)
        self.available.append(bar.available_at_ms)
        self.irregular_prefix.append(self.irregular_prefix[-1] + int(irregular))
        for state, values in self.emas.values():
            values.append(state.update(bar.close_bid))
        for state, values in self.atrs.values():
            values.append(state.update(bar.high_bid, bar.low_bid, bar.close_bid))

    def count_at(self, decision_ms: int) -> int:
        return bisect.bisect_right(self.available, decision_ms)

    def irregular_in_last(self, count: int, window: int) -> bool:
        lo = max(0, count - window)
        return self.irregular_prefix[count] - self.irregular_prefix[lo] > 0


class AnalysisEngine:
    def __init__(self, source_id: str, params: AnalysisParams = S1_RESEARCH_V0_2) -> None:
        self.source_id = source_id
        self.params = params
        p = params
        self._series = {
            Timeframe.M1: _Series(Timeframe.M1, (), ()),
            M5: _Series(M5, (), (p.m5_atr_period,)),
            M15: _Series(M15, (p.m15_ema,), ()),
            H1: _Series(H1, (p.h1_ema_fast, p.h1_ema_slow), (p.h1_atr_period,)),
        }
        self._pivots = {
            tf: PivotDetector(source_id, tf, p.pivot_left, p.pivot_right, p.calculation_version)
            for tf in (M5, M15)
        }

    # ------------------------------------------------------------------ input

    def on_bar(self, bar: FinalizedBar) -> list[Pivot]:
        """Add one finalized bar; return pivots it newly confirmed (M5/M15 only)."""
        if bar.source_id != self.source_id:
            raise ValueError(f"bar from source {bar.source_id!r} fed to {self.source_id!r}")
        if bar.quality is BarQuality.INVALID:
            raise ValueError("INVALID bars must not reach analysis")
        self._series[bar.timeframe].append(bar)
        detector = self._pivots.get(bar.timeframe)
        return detector.on_bar(bar) if detector else []

    def on_events(self, events: Iterable[object]) -> list[Pivot]:
        """Convenience: accept ``BarAggregator`` output (gap records are ignored here)."""
        found: list[Pivot] = []
        for event in events:
            if isinstance(event, FinalizedBar):
                found.extend(self.on_bar(event))
        return found

    def bars(self, timeframe: Timeframe, decision_ms: int) -> tuple[FinalizedBar, ...]:
        s = self._series[timeframe]
        return tuple(s.bars[: s.count_at(decision_ms)])

    def pivots(self, timeframe: Timeframe, decision_ms: int) -> tuple[Pivot, ...]:
        return tuple(p for p in self._pivots[timeframe].pivots if p.available_at_ms <= decision_ms)

    # ------------------------------------------------------------------ features

    def _indicator(
        self, s: _Series, kind: str, period: int, count: int, required: int
    ) -> IndicatorValue:
        values = (s.emas if kind == "EMA" else s.atrs)[period][1]
        bar = s.bars[count - 1] if count else None
        value = values[count - 1] if count else None
        if value is None or count < required:
            status = IndicatorStatus.INSUFFICIENT_HISTORY
        elif value == 0:
            status = IndicatorStatus.ZERO_VALUE
        else:
            status = IndicatorStatus.VALID
        return IndicatorValue(
            name=f"{kind}{period}",
            timeframe=s.timeframe,
            source_id=self.source_id,
            bar_id=bar.bar_id if bar else None,
            event_time_ms=bar.end_ms if bar else None,
            available_at_ms=bar.available_at_ms if bar else None,
            value=value,
            status=status,
            bars_seen=count,
            required_bars=required,
            calculation_version=self.params.calculation_version,
        )

    def _h1_bias(
        self, count: int
    ) -> tuple[H1Bias, tuple[str, ...], Decimal | None, Decimal | None]:
        p, s = self.params, self._series[H1]
        if count == 0:
            return H1Bias.UNKNOWN, ("NO_FINALIZED_H1_BAR",), None, None
        if count < p.h1_warmup_bars:
            return (
                H1Bias.UNKNOWN,
                (f"INSUFFICIENT_H1_HISTORY:{count}/{p.h1_warmup_bars}",),
                None,
                None,
            )
        t = count - 1
        fast = s.emas[p.h1_ema_fast][1]
        slow = s.emas[p.h1_ema_slow][1][t]
        f_now, f_prev = fast[t], fast[t - p.h1_slope_lookback_bars]
        close = s.bars[t].close_bid
        if f_now is None or f_prev is None or slow is None:
            return H1Bias.UNKNOWN, ("EMA_NOT_SEEDED",), None, None
        if f_now > slow and f_now > f_prev and close > slow:
            bias = H1Bias.UP
        elif f_now < slow and f_now < f_prev and close < slow:
            bias = H1Bias.DOWN
        else:
            bias = H1Bias.NEUTRAL
        atr = s.atrs[p.h1_atr_period][1][t]
        spread = slope = None
        if atr is not None and atr > 0:
            spread = CALC_CONTEXT.divide(abs(f_now - slow), atr)
            slope = CALC_CONTEXT.divide(f_now - f_prev, atr)
        return bias, (), spread, slope

    def _m15(self, side: Side, count: int, decision_ms: int) -> M15Assessment:
        p, s = self.params, self._series[M15]

        def unknown(reason: str, **kw: Any) -> M15Assessment:
            return M15Assessment(
                side, M15Context.UNKNOWN, None, None, None, None, None, None, (reason,), **kw
            )

        if count < p.m15_warmup_bars:
            return unknown(f"INSUFFICIENT_M15_HISTORY:{count}/{p.m15_warmup_bars}")
        ema_values = s.emas[p.m15_ema][1]
        t = count - 1
        ema, ema_prev = ema_values[t], ema_values[t - 1]
        close = s.bars[t].close_bid
        if ema is None or ema_prev is None:
            return unknown("M15_EMA_NOT_SEEDED")
        want = PivotSide.LOW if side is Side.BUY else PivotSide.HIGH
        first_index = count - p.m15_pivot_window_bars
        candidates = [
            pv
            for pv in self._pivots[M15].pivots
            if pv.side is want and pv.available_at_ms <= decision_ms and pv.bar_index >= first_index
        ]
        if not candidates:
            return M15Assessment(
                side,
                M15Context.UNKNOWN,
                None,
                None,
                None,
                close,
                ema,
                ema_prev,
                (f"NO_CONFIRMED_M15_PIVOT_{want.value}_IN_{p.m15_pivot_window_bars}_BARS",),
            )
        ref = max(candidates, key=lambda pv: pv.bar_index)
        if side is Side.BUY:
            against = ema < ema_prev  # EMA20 declined since the preceding finalized M15 bar
            if close < ref.price and against:
                ctx = M15Context.OPPOSING
            elif close < ema or against:
                ctx = M15Context.CORRECTIVE
            else:
                ctx = M15Context.SUPPORTIVE
        else:
            against = ema > ema_prev
            if close > ref.price and against:
                ctx = M15Context.OPPOSING
            elif close > ema or against:
                ctx = M15Context.CORRECTIVE
            else:
                ctx = M15Context.SUPPORTIVE
        return M15Assessment(
            side, ctx, ref.pivot_id, ref.price, ref.available_at_ms, close, ema, ema_prev, ()
        )

    # ------------------------------------------------------------------ query

    def context(self, decision_time_ms: int) -> AnalysisContext:
        p = self.params
        counts = {tf: self._series[tf].count_at(decision_time_ms) for tf in TIMEFRAMES}
        h1, m15, m5 = self._series[H1], self._series[M15], self._series[M5]

        def last_id(s: _Series, n: int) -> str | None:
            return s.bars[n - 1].bar_id if n else None

        bias, reasons, spread, slope = self._h1_bias(counts[H1])
        buy = self._m15(Side.BUY, counts[M15], decision_time_ms)
        sell = self._m15(Side.SELL, counts[M15], decision_time_ms)
        emas = (
            self._indicator(h1, "EMA", p.h1_ema_fast, counts[H1], p.h1_warmup_bars),
            self._indicator(h1, "EMA", p.h1_ema_slow, counts[H1], p.h1_warmup_bars),
            self._indicator(m15, "EMA", p.m15_ema, counts[M15], p.m15_warmup_bars),
        )
        atrs = (
            self._indicator(m5, "ATR", p.m5_atr_period, counts[M5], p.m5_atr_period + 1),
            self._indicator(h1, "ATR", p.h1_atr_period, counts[H1], p.h1_atr_period + 1),
        )
        flags = []
        if h1.irregular_in_last(counts[H1], p.h1_warmup_bars):
            flags.append("H1_HISTORY_IRREGULAR")
        if m15.irregular_in_last(counts[M15], max(p.m15_warmup_bars, p.m15_pivot_window_bars)):
            flags.append("M15_HISTORY_IRREGULAR")
        if m5.irregular_in_last(counts[M5], p.m5_atr_period + 1):
            flags.append("M5_HISTORY_IRREGULAR")
        for value in (*emas, *atrs):
            if value.status is not IndicatorStatus.VALID:
                flags.append(f"{value.timeframe.value}_{value.name}_{value.status.value}")
        pivots = self.pivots(M15, decision_time_ms) + self.pivots(M5, decision_time_ms)
        return AnalysisContext(
            source_id=self.source_id,
            decision_time_ms=decision_time_ms,
            last_confirmed_h1_id=last_id(h1, counts[H1]),
            last_confirmed_m15_id=last_id(m15, counts[M15]),
            last_confirmed_m5_id=last_id(m5, counts[M5]),
            h1_bias=bias,
            h1_bias_reasons=reasons,
            h1_strength_spread_atr=spread,
            h1_strength_slope_atr=slope,
            m15_buy=buy,
            m15_sell=sell,
            ema_values=emas,
            atr_values=atrs,
            confirmed_pivots=pivots,
            relevant_level_ids=tuple(
                a.reference_pivot_id for a in (buy, sell) if a.reference_pivot_id is not None
            ),
            quality_flags=tuple(flags),
            calculation_version=p.calculation_version,
            parameter_set_hash=p.parameter_set_hash,
        )


def context_to_dict(ctx: AnalysisContext) -> dict[str, Any]:
    """Canonical serialization (exact decimal strings) for replay-equivalence checks."""

    def conv(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, tuple):
            return [conv(v) for v in value]
        if hasattr(value, "__dataclass_fields__"):
            return {k: conv(getattr(value, k)) for k in value.__dataclass_fields__}
        if hasattr(value, "value") and isinstance(value.value, str):
            return value.value
        return value

    return conv(ctx)
