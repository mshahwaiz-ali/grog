"""H1 bias / M15 context / feature availability (docs/04 §3, §7, §8; S1-01/02/18/19)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from grog.analysis.contexts import AnalysisEngine, context_to_dict
from grog.analysis.ema_atr import ema_series
from grog.domain.enums import BarQuality, H1Bias, IndicatorStatus, M15Context, Side, Timeframe
from quote_stream import make_bar

H1, M15, M5 = Timeframe.H1, Timeframe.M15, Timeframe.M5
FAR = 10**15  # decision time after everything


def h1_bars(closes: list[Decimal], **kw):
    return [make_bar(H1, i, str(c + 1), str(c - 1), str(c), **kw) for i, c in enumerate(closes)]


def engine_with(bars) -> AnalysisEngine:
    e = AnalysisEngine("syn-1")
    for b in bars:
        e.on_bar(b)
    return e


def linear(n: int, start: str, step: str) -> list[Decimal]:
    return [Decimal(start) + Decimal(step) * i for i in range(n)]


# ------------------------------------------------------------------ H1 bias


def test_h1_up_down_neutral() -> None:
    assert engine_with(h1_bars(linear(260, "4000", "1"))).context(FAR).h1_bias is H1Bias.UP
    assert engine_with(h1_bars(linear(260, "4300", "-1"))).context(FAR).h1_bias is H1Bias.DOWN
    flat = engine_with(h1_bars([Decimal("4000")] * 260)).context(FAR)
    assert flat.h1_bias is H1Bias.NEUTRAL and flat.h1_bias_reasons == ()


def test_h1_mixed_conditions_are_neutral() -> None:
    closes = linear(259, "4000", "1") + [Decimal("4228")]
    ctx = engine_with(h1_bars(closes)).context(FAR)
    e20 = ema_series(closes, 20)
    e50 = ema_series(closes, 50)
    # fast above slow and rising, but the close is below the slow EMA -> mixed
    assert e20[-1] > e50[-1] and e20[-1] > e20[-4] and closes[-1] < e50[-1]
    assert ctx.h1_bias is H1Bias.NEUTRAL


def test_h1_warmup_boundary_249_vs_250() -> None:  # S1-18 partial warm-up
    bars = h1_bars(linear(250, "4000", "1"))
    short = engine_with(bars[:249]).context(FAR)
    assert short.h1_bias is H1Bias.UNKNOWN
    assert short.h1_bias_reasons == ("INSUFFICIENT_H1_HISTORY:249/250",)
    assert short.ema_values[1].status is IndicatorStatus.INSUFFICIENT_HISTORY
    assert engine_with(bars).context(FAR).h1_bias is H1Bias.UP
    assert AnalysisEngine("syn-1").context(FAR).h1_bias_reasons == ("NO_FINALIZED_H1_BAR",)


def test_h1_uses_last_confirmed_bar_not_unfinished_reversal() -> None:  # S1-01
    bars = h1_bars(linear(260, "4300", "-1"))
    e = engine_with(bars)
    decision = bars[-1].available_at_ms + 30 * 60_000  # mid-way through the next H1
    assert e.context(decision).h1_bias is H1Bias.DOWN
    # A huge up bar is finalized but only becomes available later (late quote).
    surge = make_bar(H1, 260, "4900", "4040", "4890", available_delay_ms=45 * 60_000)
    e.on_bar(surge)
    assert e.context(surge.end_ms).h1_bias is H1Bias.DOWN  # not yet available
    assert e.context(surge.end_ms).last_confirmed_h1_id == bars[-1].bar_id
    assert e.context(surge.available_at_ms).last_confirmed_h1_id == surge.bar_id


def test_h1_strength_features_need_valid_atr() -> None:
    ctx = engine_with(h1_bars(linear(260, "4000", "1"))).context(FAR)
    assert ctx.h1_strength_spread_atr is not None and ctx.h1_strength_spread_atr > 0
    flat = [make_bar(H1, i, "4000", "4000", "4000") for i in range(260)]
    ctx2 = engine_with(flat).context(FAR)
    assert (
        ctx2.h1_strength_spread_atr is None
        and ctx2.atr_values[1].status is IndicatorStatus.ZERO_VALUE
    )


# ------------------------------------------------------------------ M15 context

RISE = [4000 + i for i in range(50)] + [4049, 4040, 4030, 4040, 4050, 4056, 4060]
PIVOT_LOW = Decimal("4029.5")  # low of bar index 52, confirmed by bar 54


def m15_bars(closes: list[float | int], mirror: bool = False):
    out = []
    for i, c in enumerate(closes):
        c = Decimal(str(c))
        hi, lo = c + Decimal("0.5"), c - Decimal("0.5")
        if mirror:
            c, hi, lo = 8000 - c, 8000 - lo, 8000 - hi
        out.append(make_bar(M15, i, str(hi), str(lo), str(c)))
    return out


def m15(closes, side: Side, mirror: bool = False):
    ctx = engine_with(m15_bars(closes, mirror)).context(FAR)
    return ctx.m15_buy if side is Side.BUY else ctx.m15_sell


@pytest.mark.parametrize(("side", "mirror"), [(Side.BUY, False), (Side.SELL, True)])
def test_m15_supportive(side: Side, mirror: bool) -> None:
    a = m15(RISE, side, mirror)
    assert a.context is M15Context.SUPPORTIVE and a.reasons == ()
    expected = PIVOT_LOW if not mirror else 8000 - PIVOT_LOW
    assert a.reference_price == expected
    assert a.reference_pivot_id.endswith(":LOW" if side is Side.BUY else ":HIGH")


@pytest.mark.parametrize(("side", "mirror"), [(Side.BUY, False), (Side.SELL, True)])
def test_m15_corrective_and_opposing(side: Side, mirror: bool) -> None:
    ema = ema_series([Decimal(c) for c in RISE + [4038]], 20)[-1]
    assert PIVOT_LOW < Decimal("4038") < ema  # precondition: below EMA but above the pivot low
    corr = m15(RISE + [4038], side, mirror)
    assert corr.context is M15Context.CORRECTIVE
    opp = m15(RISE + [4025], side, mirror)
    assert opp.context is M15Context.OPPOSING
    assert opp.ema < opp.ema_previous if not mirror else opp.ema > opp.ema_previous


def test_m15_pivot_older_than_48_bars_is_unknown() -> None:  # S1-19
    tail = [4060 + i for i in range(1, 60)]
    inside = m15(RISE + tail[: 100 - len(RISE)], Side.BUY)  # 100 bars: index 52 is in window
    assert inside.reference_price == PIVOT_LOW
    outside = m15(RISE + tail[: 101 - len(RISE)], Side.BUY)  # 101 bars: out of window
    assert outside.context is M15Context.UNKNOWN and outside.reference_pivot_id is None
    assert outside.reasons == ("NO_CONFIRMED_M15_PIVOT_LOW_IN_48_BARS",)


def test_m15_insufficient_history_unknown() -> None:
    a = m15(RISE[:49], Side.BUY)
    assert a.context is M15Context.UNKNOWN and a.reasons == ("INSUFFICIENT_M15_HISTORY:49/50",)


def test_m15_pivot_not_used_before_available() -> None:
    bars = m15_bars(RISE)
    late = replace(bars[54], available_at_ms=bars[54].end_ms + 1)  # confirming bar of pivot 52
    bars = (
        bars[:54]
        + [late]
        + [
            replace(b, available_at_ms=max(b.available_at_ms, late.available_at_ms))
            for b in bars[55:]
        ]
    )
    e = engine_with(bars[:55])
    assert e.context(late.end_ms).m15_buy.reference_pivot_id is None
    assert e.context(late.available_at_ms).m15_buy.reference_price == PIVOT_LOW


def test_h1_up_with_m15_corrective_is_recorded_not_vetoed() -> None:  # S1-02 (analysis part)
    e = engine_with(h1_bars(linear(260, "4000", "1")))
    for b in m15_bars(RISE + [4038]):
        e.on_bar(b)
    ctx = e.context(FAR)
    assert ctx.h1_bias is H1Bias.UP and ctx.m15_buy.context is M15Context.CORRECTIVE


# ------------------------------------------------------------------ M5 ATR, flags, provenance


def test_m5_atr_zero_and_insufficient() -> None:  # S1-18
    flat = [make_bar(M5, i, "4000.00", "4000.00", "4000.00") for i in range(20)]
    ctx = engine_with(flat).context(FAR)
    assert ctx.atr_values[0].status is IndicatorStatus.ZERO_VALUE
    assert "M5_ATR14_ZERO_VALUE" in ctx.quality_flags
    few = engine_with(flat[:14]).context(FAR)
    assert few.atr_values[0].status is IndicatorStatus.INSUFFICIENT_HISTORY
    assert engine_with(flat[:15]).context(FAR).atr_values[0].value == 0


def test_gaps_are_flagged() -> None:
    bars = h1_bars(linear(260, "4000", "1"))
    bars[200] = replace(bars[200], quality=BarQuality.GAPPED)
    assert "H1_HISTORY_IRREGULAR" in engine_with(bars).context(FAR).quality_flags
    clean = engine_with(h1_bars(linear(260, "4000", "1"))).context(FAR)
    assert "H1_HISTORY_IRREGULAR" not in clean.quality_flags


def test_ask_side_never_changes_analysis() -> None:
    a = engine_with(h1_bars(linear(260, "4000", "1")) + m15_bars(RISE)).context(FAR)
    b = engine_with(
        h1_bars(linear(260, "4000", "1"), ask_offset="3.00")
        + [replace(x, high_ask=x.high_ask + 7, low_ask=x.low_ask + 7) for x in m15_bars(RISE)]
    ).context(FAR)
    assert context_to_dict(a) == context_to_dict(b)


def test_feature_records_carry_provenance() -> None:
    ctx = engine_with(h1_bars(linear(260, "4000", "1"))).context(FAR)
    ema50 = ctx.ema_values[1]
    assert (ema50.name, ema50.timeframe, ema50.source_id) == ("EMA50", H1, "syn-1")
    assert ema50.bar_id == ctx.last_confirmed_h1_id and ema50.available_at_ms is not None
    assert ctx.calculation_version == "S1_RESEARCH_V0_2/analysis-1"


def test_input_validation() -> None:
    e = AnalysisEngine("syn-1")
    with pytest.raises(ValueError):
        e.on_bar(make_bar(H1, 0, "1", "1", source_id="other"))
    with pytest.raises(ValueError):
        e.on_bar(replace(make_bar(H1, 0, "1", "1"), quality=BarQuality.INVALID))
