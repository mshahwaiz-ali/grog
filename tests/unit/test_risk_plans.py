"""Price-side risk-plan math (docs/07 §2-6; S1-12..16, ADV-05, MD-15..18, ST-09/10)."""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from grog.domain.enums import ExitOutcome, ReasonCode, Side, Timeframe
from grog.risk.quotes_and_plans import (
    ContractSpec,
    CostModel,
    TradePlan,
    actual_fill_economics,
    build_plan,
    evaluate_exit_bar,
    evaluate_exit_ticks,
    net_price_move,
    no_chase_ok,
    price_to_money,
    round_to_step,
    stop_touched,
    target_touched,
)
from quote_stream import T10, Stream, make_bar

STEP = D("0.01")  # declared synthetic fixture increment (never a broker value)


def quote(bid: str, ask: str, t: int = T10):
    return Stream().add(t, bid=bid, ask=ask).quotes[0]


def ticks(pairs: list[tuple[str, str]]):
    s = Stream()
    for i, (b, a) in enumerate(pairs):
        s.add(T10 + i * 1000, bid=b, ask=a)
    return s.quotes


def long_plan() -> TradePlan:
    # P_bid 3998.30, ATR 3 -> SL 3998.00; E0 = ASK 4000.20; R 2.20; TP2 4004.60 (ADV-05)
    plan = build_plan(
        Side.BUY, quote("4000.00", "4000.20"), D("3998.30"), D("4000"), D("3"), STEP
    ).plan
    assert plan is not None
    return plan


def test_long_plan_matches_docs_example() -> None:
    p = long_plan()
    assert (p.e0, p.sl0, p.risk, p.tp1, p.tp2) == (
        D("4000.20"),
        D("3998.00"),
        D("2.20"),
        D("4002.40"),
        D("4004.60"),
    )
    assert (p.entry_low, p.entry_high) == (D("3999.90"), D("4000.80"))
    assert p.retention_threshold == D("3999.70")
    assert p.exit_policy == "FULL_AT_TP2_OR_SL"


def test_short_stop_uses_ask_high_plus_buffer() -> None:  # S1-13
    q = quote("4000.00", "4000.30")
    p = build_plan(Side.SELL, q, D("4002.25"), D("4000.5"), D("3"), STEP).plan  # P_ask
    assert p.e0 == D("4000.00") and p.sl0 == D("4002.55")  # 4002.25 + 0.30, rounded up
    bid_based = build_plan(Side.SELL, q, D("4001.95"), D("4000.5"), D("3"), STEP).plan
    assert bid_based.sl0 != p.sl0  # using the BID high would understate the short stop
    assert p.tp2 == p.e0 - 2 * p.risk


def test_directional_rounding_with_declared_step() -> None:  # ST-10
    assert round_to_step(D("3998.004"), STEP, up=False) == D("3998.00")
    assert round_to_step(D("3998.001"), STEP, up=True) == D("3998.01")
    assert round_to_step(D("3998.00"), STEP, up=True) == D("3998.00")
    p = build_plan(
        Side.BUY, quote("4000.00", "4000.20"), D("3998.333"), D("4000"), D("3"), STEP
    ).plan
    assert p.sl0 == D("3998.03")  # 3998.033 down to the declared step
    with pytest.raises(ValueError):
        round_to_step(D("1"), D("0"), up=True)


def test_invalid_plans_rejected() -> None:
    q = quote("4000.00", "4000.20")
    assert build_plan(Side.BUY, q, D("4000.5"), D("4000"), D("3"), STEP).reasons == (
        ReasonCode.PRE_ENTRY_STOP_TOUCH,
    )
    assert build_plan(Side.BUY, q, D("3998"), D("4000"), D("0"), STEP).reasons == (
        ReasonCode.M5_ATR_ZERO,
    )


@pytest.mark.parametrize(
    ("side", "e0", "ok"),
    [
        (Side.BUY, "4000.60", True),
        (Side.BUY, "4000.61", False),
        (Side.SELL, "3999.40", True),
        (Side.SELL, "3999.39", False),
    ],
)
def test_no_chase_bound(side: Side, e0: str, ok: bool) -> None:  # S1-09
    from grog.risk.quotes_and_plans import RESEARCH_RISK_V0_2

    assert no_chase_ok(side, D(e0), D("4000"), D("3"), RESEARCH_RISK_V0_2) is ok


def test_stop_and_target_use_broker_side_prices() -> None:  # S1-12, MD-17
    p = long_plan()
    spread_spike = quote("3998.00", "4001.00")  # mid 3999.50 is well above the stop
    assert stop_touched(Side.BUY, spread_spike, p.sl0)
    assert not stop_touched(Side.BUY, quote("3998.01", "3998.21"), p.sl0)
    short_q = quote("4002.00", "4002.55")
    assert stop_touched(Side.SELL, short_q, D("4002.55"))  # ASK only, BID far below
    assert not stop_touched(Side.SELL, quote("4002.50", "4002.54"), D("4002.55"))
    assert target_touched(Side.BUY, quote("4004.60", "4004.80"), p.tp2)
    assert not target_touched(Side.BUY, quote("4004.59", "4004.79"), p.tp2)  # ASK irrelevant
    assert target_touched(Side.SELL, quote("3995.00", "3995.60"), D("3995.60"))


def test_tp1_touch_is_not_a_partial_win() -> None:  # S1-14
    p = long_plan()
    path = ticks(
        [
            ("4001.00", "4001.20"),
            ("4002.40", "4002.60"),
            ("4003.00", "4003.20"),
            ("3999.00", "3999.20"),
            ("3998.00", "3998.20"),
        ]
    )
    res = evaluate_exit_ticks(p, path)
    assert res.outcome is ExitOutcome.STOP and res.tp1_touched
    assert res.gross_r == D("-1") and res.exit_price == p.sl0
    win = evaluate_exit_ticks(p, ticks([("4002.40", "4002.6"), ("4004.60", "4004.8")]))
    assert win.outcome is ExitOutcome.TARGET and win.gross_r == D("2")
    assert evaluate_exit_ticks(p, ticks([("4001", "4001.2")])).outcome is ExitOutcome.OPEN


def test_same_bar_stop_and_target_is_indeterminate() -> None:  # S1-16, MD-18
    p = long_plan()
    both = make_bar(Timeframe.M1, 0, "4004.70", "3997.90", "4000")
    assert evaluate_exit_bar(p, both) is ExitOutcome.INDETERMINATE
    assert evaluate_exit_bar(p, make_bar(Timeframe.M1, 0, "4004.70", "3999", "4004")) is (
        ExitOutcome.TARGET
    )
    assert evaluate_exit_bar(p, make_bar(Timeframe.M1, 0, "4001", "3997.9", "3998")) is (
        ExitOutcome.STOP
    )
    # The same range resolved by ordered ticks is determinate.
    ordered = ticks([("3997.90", "3998.10"), ("4004.70", "4004.90")])
    assert evaluate_exit_ticks(p, ordered).outcome is ExitOutcome.STOP


def test_late_worse_fill_recomputes_without_rewriting_original() -> None:  # S1-15, ADV-05
    p = long_plan()
    econ = actual_fill_economics(p, D("4001.10"))
    assert econ.actual_risk == D("3.10") and econ.actual_reward_tp2 == D("3.50")
    assert econ.actual_r_multiple_tp2.quantize(D("0.01")) == D("1.13")
    assert econ.off_plan and ReasonCode.OUTSIDE_ENTRY_BAND in econ.reasons
    assert (p.e0, p.sl0, p.tp2, p.risk) == (D("4000.20"), D("3998.00"), D("4004.60"), D("2.20"))
    inside = actual_fill_economics(p, D("4000.50"))
    assert not inside.off_plan and inside.reasons == ()


def test_spread_counted_once() -> None:  # MD-16
    # Long buys ASK 4000.20 and sells BID 4004.60: the spread is already inside.
    gross, net = net_price_move(Side.BUY, D("4000.20"), D("4004.60"), None)
    assert gross == D("4.40") and net is None  # UNKNOWN without a declared cost model
    cost = CostModel("fixture-cost", round_trip_commission=D("0.10"), slippage=D("0.05"))
    assert net_price_move(Side.BUY, D("4000.20"), D("4004.60"), cost)[1] == D("4.25")
    assert net_price_move(Side.SELL, D("4000.00"), D("3995.60"), cost)[0] == D("4.40")


def test_money_requires_contract_and_fx() -> None:  # ST-09, MD-15
    none = price_to_money(D("2.2"), D("1"), None, "USD")
    assert none.native_amount is None and none.reasons == (ReasonCode.CONTRACT_UNDEFINED,)
    eur = ContractSpec(D("100"), "EUR")
    m = price_to_money(D("2.2"), D("0.5"), eur, "USD")
    assert (m.native_amount, m.native_currency, m.reporting_amount) == (D("110.0"), "EUR", None)
    assert m.reasons == (ReasonCode.FX_RATE_UNAVAILABLE,)
    conv = price_to_money(D("2.2"), D("0.5"), eur, "USD", D("1.1"))
    assert conv.reporting_amount == D("121.00")
    same = price_to_money(D("2.2"), D("1"), ContractSpec(D("100"), "USD"), "USD")
    assert same.reporting_amount == D("220.0")
