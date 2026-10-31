"""EMA/ATR versus independent exact-fraction references (docs/04 §4-5; S1-18)."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

from grog.analysis.ema_atr import AtrState, EmaState, atr_series, ema_series, true_range
from grog.analysis.params import S1_RESEARCH_V0_2, AnalysisParams


def prices(n: int, seed: int = 7) -> list[Decimal]:
    """Deterministic synthetic walk in 0.01 steps (fixture values, not market data)."""
    out, x, cents = [], seed, 400_000
    for _ in range(n):
        x = (x * 1103515245 + 12345) % 2**31
        cents += (x % 41) - 20
        out.append(Decimal(cents) / 100)
    return out


def ref_ema(closes: list[Decimal], n: int) -> list[Fraction | None]:
    alpha = Fraction(2, n + 1)
    out: list[Fraction | None] = []
    value: Fraction | None = None
    for i, c in enumerate(closes):
        c = Fraction(c)
        if i < n - 1:
            out.append(None)
            continue
        if i == n - 1:
            value = sum(Fraction(x) for x in closes[:n]) / n
        else:
            value = alpha * c + (1 - alpha) * value
        out.append(value)
    return out


def ref_atr(h: list[Decimal], lo: list[Decimal], c: list[Decimal], n: int) -> list[Fraction | None]:
    trs = [None] + [
        max(Fraction(h[i] - lo[i]), abs(Fraction(h[i] - c[i - 1])), abs(Fraction(lo[i] - c[i - 1])))
        for i in range(1, len(c))
    ]
    out: list[Fraction | None] = [None] * len(c)
    value: Fraction | None = None
    for i in range(1, len(c)):
        if i < n:
            continue
        value = sum(trs[1 : n + 1]) / n if i == n else ((n - 1) * value + trs[i]) / n
        out[i] = value
    return out


def close_enough(a: Decimal | None, b: Fraction | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(Fraction(a) - b) < Fraction(1, 10**24)


@pytest.mark.parametrize("period", [1, 2, 14, 20, 50])
def test_ema_matches_exact_reference(period: int) -> None:
    closes = prices(400)
    got, want = ema_series(closes, period), ref_ema(closes, period)
    assert all(close_enough(a, b) for a, b in zip(got, want, strict=True))


def test_ema_seed_is_sma_at_index_n_minus_1() -> None:
    closes = [Decimal(x) for x in ("1", "2", "3", "4", "5")]
    got = ema_series(closes, 3)
    assert got[:2] == [None, None]
    assert got[2] == Decimal(2)  # SMA(1,2,3)
    assert got[3] == Decimal("3.0")  # 0.5*4 + 0.5*2
    assert got[4] == Decimal("4.00")


def test_ema_insufficient_history_has_no_value() -> None:
    s = EmaState(50)
    assert all(s.update(p) is None for p in prices(49))
    assert s.update(Decimal("4000")) is not None and s.count == 50


@pytest.mark.parametrize("period", [1, 14, 21])
def test_atr_matches_exact_reference(period: int) -> None:
    c = prices(300)
    h = [x + Decimal("0.37") for x in c]
    lo = [x - Decimal("0.41") for x in c]
    got, want = atr_series(h, lo, c, period), ref_atr(h, lo, c, period)
    assert all(close_enough(a, b) for a, b in zip(got, want, strict=True))


def test_true_range_uses_prior_close_for_gaps() -> None:
    assert true_range(Decimal("10"), Decimal("9"), Decimal("9.5")) == Decimal("1")
    assert true_range(Decimal("12"), Decimal("11"), Decimal("9")) == Decimal("3")  # gap up
    assert true_range(Decimal("8"), Decimal("7"), Decimal("10")) == Decimal("3")  # gap down


def test_atr_first_bar_has_no_tr_and_seed_needs_n_trs() -> None:
    s = AtrState(3)
    vals = [
        s.update(Decimal(h), Decimal(lo), Decimal(c))
        for h, lo, c in [
            ("10", "9", "9.5"),
            ("11", "9", "10"),
            ("12", "10", "11"),
            ("12", "11", "11"),
            ("13", "11", "12"),
        ]
    ]
    # TRs: -, 2, 2, 1, 2 -> seed at 4th bar = mean(2,2,1) = 5/3, then (2*5/3+2)/3 = 16/9
    assert vals[:3] == [None, None, None]
    assert abs(Fraction(vals[3]) - Fraction(5, 3)) < Fraction(1, 10**30)
    assert abs(Fraction(vals[4]) - Fraction(16, 9)) < Fraction(1, 10**30)


def test_atr_zero_on_flat_prices() -> (
    None
):  # S1-18: zero ATR is a fact, consumers treat as unavailable
    flat = [Decimal("4000.00")] * 20
    assert atr_series(flat, flat, flat, 14)[-1] == 0


def test_deterministic_and_bid_only_inputs() -> None:
    c = prices(200)
    assert ema_series(c, 20) == ema_series(list(c), 20)


def test_invalid_periods_and_lengths() -> None:
    for bad in (0, -1, True):
        with pytest.raises(ValueError):
            EmaState(bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        atr_series([Decimal(1)], [], [Decimal(1)], 1)


def test_research_profile_values_and_hash() -> None:
    p = S1_RESEARCH_V0_2
    assert (p.h1_ema_fast, p.h1_ema_slow, p.h1_warmup_bars) == (20, 50, 250)
    assert (p.m15_ema, p.m15_warmup_bars, p.m15_pivot_window_bars) == (20, 50, 48)
    assert (p.m5_atr_period, p.pivot_left, p.pivot_right) == (14, 2, 2)
    assert (
        len(p.parameter_set_hash) == 64
        and p.parameter_set_hash == S1_RESEARCH_V0_2.parameter_set_hash
    )
    with pytest.raises(ValueError):
        AnalysisParams(**{**{f: getattr(p, f) for f in p.__dataclass_fields__}, "h1_ema_fast": 50})
