"""Confirmed 2/2 pivots (docs/04 §6; S1-03, ties, causality, replay)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from grog.analysis.pivots import PivotDetector
from grog.domain.enums import BarQuality, PivotSide, Timeframe
from quote_stream import make_bar

M5 = Timeframe.M5
V = "test-v"


def detector() -> PivotDetector:
    return PivotDetector("syn-1", M5, 2, 2, V)


def feed(highs_lows: list[tuple[str, str]], **kw) -> tuple[PivotDetector, list[list]]:
    d = detector()
    out = [d.on_bar(make_bar(M5, i, h, lo, **kw)) for i, (h, lo) in enumerate(highs_lows)]
    return d, out


def test_pivot_high_confirmed_only_after_k_plus_2() -> None:  # S1-03
    hl = [("10", "9"), ("11", "9"), ("13", "9"), ("12", "9"), ("11", "9")]
    d, per_bar = feed(hl[:4])
    assert all(p == [] or all(x.side is PivotSide.LOW for x in p) for p in per_bar)
    assert not [p for p in d.pivots if p.side is PivotSide.HIGH]  # only 1 right bar closed
    new = d.on_bar(make_bar(M5, 4, *hl[4]))
    (high,) = [p for p in new if p.side is PivotSide.HIGH]
    assert high.bar_index == 2 and high.price == Decimal("13")
    assert high.confirming_bar_id == "syn-1:M5:" + str(make_bar(M5, 4, "1", "1").start_ms)
    assert high.confirmed_at_ms == make_bar(M5, 4, "1", "1").end_ms
    assert high.available_at_ms == high.confirmed_at_ms
    assert high.pivot_id == f"{make_bar(M5, 2, '1', '1').bar_id}:HIGH"
    assert high.calculation_version == V and not high.window_irregular


def test_pivot_low_mirror() -> None:
    _, per_bar = feed([("20", "10"), ("20", "9"), ("20", "7"), ("20", "8"), ("20", "9")])
    (low,) = per_bar[4]
    assert low.side is PivotSide.LOW and low.price == Decimal("7") and low.bar_index == 2


def test_available_at_follows_late_confirming_bar() -> None:
    d = detector()
    for i, hl in enumerate([("10", "9"), ("11", "9"), ("13", "9"), ("12", "9")]):
        d.on_bar(make_bar(M5, i, *hl))
    (p,) = [
        x
        for x in d.on_bar(make_bar(M5, 4, "11", "9", available_delay_ms=40_000))
        if x.side is PivotSide.HIGH
    ]
    assert p.available_at_ms == p.confirmed_at_ms + 40_000


@pytest.mark.parametrize(
    "highs",
    [
        ["10", "11", "13", "13", "11"],  # equal right neighbour
        ["10", "13", "13", "12", "11"],  # equal left neighbour
        ["13", "11", "13", "12", "11"],  # equal two bars left
        ["10", "11", "13", "12", "13"],  # equal two bars right
    ],
)
def test_equal_highs_are_not_pivots(highs: list[str]) -> None:
    d, _ = feed([(h, "1") for h in highs])
    assert [p for p in d.pivots if p.side is PivotSide.HIGH] == []


def test_same_bar_high_and_low_pivots_are_separate() -> None:
    _, per_bar = feed([("11", "9"), ("11", "9"), ("15", "5"), ("11", "9"), ("11", "9")])
    assert [p.side for p in per_bar[4]] == [PivotSide.HIGH, PivotSide.LOW]
    assert per_bar[4][0].pivot_id != per_bar[4][1].pivot_id


def test_irregular_window_flagged() -> None:
    d = detector()
    bars = [make_bar(M5, i, h, "1") for i, h in enumerate(["10", "11", "13", "12", "11"])]
    bars[3] = replace(bars[3], quality=BarQuality.GAPPED)
    (p,) = [x for b in bars for x in d.on_bar(b) if x.side is PivotSide.HIGH]
    assert p.window_irregular
    d2 = detector()
    skipped = [
        make_bar(M5, i, h, "1")
        for i, h in zip([0, 1, 2, 4, 5], ["10", "11", "13", "12", "11"], strict=True)
    ]
    (p2,) = [x for b in skipped for x in d2.on_bar(b) if x.side is PivotSide.HIGH]
    assert p2.window_irregular and p2.bar_index == 2  # index counts finalized bars only


def test_ask_prices_do_not_affect_bid_pivots() -> None:
    hl = [("10", "9"), ("11", "9"), ("13", "9"), ("12", "9"), ("11", "9")]
    a, _ = feed(hl)
    b, _ = feed(hl, ask_offset="5.00")
    assert a.pivots == b.pivots


def test_replay_equivalence_and_order_checks() -> None:
    hl = [(str(10 + (i * 7) % 5), str(5 - (i * 3) % 4)) for i in range(200)]
    a, _ = feed(hl)
    b, _ = feed(hl)
    assert a.pivots == b.pivots and a.pivots
    d = detector()
    d.on_bar(make_bar(M5, 1, "1", "1"))
    with pytest.raises(ValueError):
        d.on_bar(make_bar(M5, 1, "1", "1"))
    with pytest.raises(ValueError):
        d.on_bar(make_bar(Timeframe.M15, 5, "1", "1"))
