"""Replay outcome model on ordered BID/ASK ticks (M06; MD-18, ST-12, no candle-close fill,
costs counted once, end-of-data and gap handling)."""

from __future__ import annotations

from decimal import Decimal as D

from grog.domain.enums import ExitOutcome, GapKind, Side, Timeframe
from grog.domain.models import GapRecord
from grog.replay.runner import ReplayConfig, _Outcomes, run_replay
from grog.risk.quotes_and_plans import CostModel, build_plan
from grog.strategies.s1_pullback import record_to_dict
from quote_stream import T10, Stream

STEP = D("0.01")  # fixture-only increment


def plan_and_quotes(path: list[tuple[str, str]], gap_s: int = 1):
    s = Stream()
    s.add(T10, bid="4000.00", ask="4000.20")  # READY quote (fill under zero delay)
    for i, (b, a) in enumerate(path, start=1):
        s.add(T10 + i * gap_s * 1000, bid=b, ask=a)
    # long: E0 4000.20, SL0 3998.00, R 2.20, TP1 4002.40, TP2 4004.60
    plan = build_plan(Side.BUY, s.quotes[0], D("3998.30"), D("4000"), D("3"), STEP).plan
    assert plan is not None
    return plan, s.quotes


def outcome(path, gaps=(), cost=None, gap_s=1):
    plan, quotes = plan_and_quotes(path, gap_s)
    oc = _Outcomes(quotes, list(gaps))
    return plan, oc.evaluate(plan, 0, cost, trigger_id="T", signal_id="S", counterfactual=False)


def test_target_on_bid_side_after_fill_at_ready_quote_ask() -> None:
    plan, o = outcome([("4002.50", "4002.70"), ("4004.60", "4004.80")])
    assert o.fill_price == D("4000.20")  # READY quote ASK, never a candle close
    assert o.outcome is ExitOutcome.TARGET and o.exit_price == plan.tp2
    assert o.gross_r == D(2) and o.tp1_touched and o.net_r is None


def test_ask_touching_target_is_not_a_long_exit() -> None:
    _, o = outcome([("4004.40", "4004.70")])
    assert o.outcome is ExitOutcome.OPEN and "END_OF_DATA_UNRESOLVED" in o.reasons
    assert o.gross_r is None and o.exit_price is None


def test_ordered_ticks_stop_first_then_target() -> None:
    _, o = outcome([("3998.00", "3998.20"), ("4004.60", "4004.80")])
    assert o.outcome is ExitOutcome.STOP and o.gross_r == D(-1)


def test_stop_gap_fills_at_worse_actual_bid() -> None:
    _, o = outcome([("3997.10", "3997.30")])
    assert o.outcome is ExitOutcome.STOP and o.exit_price == D("3997.10")
    assert o.gross_r < D(-1)  # gap slippage is not hidden


def test_data_gap_during_hold_is_indeterminate() -> None:
    gap = GapRecord("syn-1", Timeframe.M1, T10 + 60_000, T10 + 180_000, 2, GapKind.DATA_GAP, 0)
    _, o = outcome([("4001.00", "4001.20"), ("4004.60", "4004.80")], gaps=[gap], gap_s=200)
    assert o.outcome is ExitOutcome.INDETERMINATE and o.gross_r is None
    assert "DATA_GAP_DURING_HOLD" in o.reasons


def test_market_closed_gap_is_not_indeterminate() -> None:
    gap = GapRecord("syn-1", Timeframe.M1, T10 + 60_000, T10 + 180_000, 2, GapKind.MARKET_CLOSED, 0)
    _, o = outcome([("4004.60", "4004.80")], gaps=[gap], gap_s=200)
    assert o.outcome is ExitOutcome.TARGET


def test_costs_subtracted_exactly_once() -> None:
    cost = CostModel("fixture", round_trip_commission=D("0.22"), slippage=D("0.11"))
    plan, o = outcome([("4004.60", "4004.80")], cost=cost)
    # spread already inside ASK entry / BID exit; declared cost removed once: 0.33 / 2.20
    assert o.gross_r == D(2) and o.net_r == D(2) - D("0.33") / plan.risk


def test_st12_same_ms_quotes_all_processed_and_replay_deterministic() -> None:
    s = Stream()
    for i in range(0, 600):
        t = T10 + (i // 2) * 1000  # pairs of quotes share one provider millisecond
        s.add(t, bid=f"{4000 + (i % 7) / 10:.2f}")
    cfg = ReplayConfig(source_id="syn-1")
    a = run_replay(s.quotes, cfg, data_sha="x")
    b = run_replay(s.quotes, cfg, data_sha="x")
    assert a.processed_quotes == 600
    assert a.run_id == b.run_id and a.summary == b.summary
    assert record_to_dict(list(a.s1_events)) == record_to_dict(list(b.s1_events))


def test_run_identity_changes_with_window_and_data() -> None:
    s = Stream().every(T10, T10 + 60_000, 1000)
    base = run_replay(s.quotes, ReplayConfig(source_id="syn-1"), data_sha="x").run_id
    other_data = run_replay(s.quotes, ReplayConfig(source_id="syn-1"), data_sha="y").run_id
    windowed = run_replay(
        s.quotes, ReplayConfig(source_id="syn-1", from_ms=T10 + 30_000), data_sha="x"
    )
    assert len({base, other_data, windowed.run_id}) == 3
    assert windowed.summary["quotes"]["pre_roll"] == 30
