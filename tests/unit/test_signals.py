"""Signal eligibility on the first executable quote (docs/06 §2-5; S1-08..11/17/18,
SQ-01..16, ADV-03/09/10/11, MD-21, ST-02/03/09/10). All thresholds below are
fixture-only declarations, never broker values."""

from __future__ import annotations

from dataclasses import fields, replace
from decimal import Decimal as D

import pytest

from grog.domain.enums import (
    ExecutionFidelity,
    FeedStatus,
    GapKind,
    GateResult,
    ReasonCode,
    S1EventKind,
    Side,
    SignalEventKind,
    SignalState,
    Timeframe,
)
from grog.domain.models import DataHealthPolicy, GapRecord, SignalRecord
from grog.market_data.health import FeedHealth
from grog.signals.engine import SignalEngine, SignalPolicy
from grog.strategies.s1_pullback import S1Detector, record_to_dict
from quote_stream import T10, Stream, make_bar
from s1_fixtures import HOUR, PATTERN, TRIGGER, WARM, h1_trend, m5

R, K = ReasonCode, SignalEventKind
M5_MS = 5 * 60_000
TEND = T10 + 25 * M5_MS  # trigger bar (index 24) end
FIXTURE_HEALTH = DataHealthPolicy(max_quote_age_ms=5_000, max_first_postclose_delay_ms=2_000)
FIXTURE = SignalPolicy(health=FIXTURE_HEALTH, price_step=D("0.01"))
CLOSE = {Side.BUY: D("4005.5"), Side.SELL: D("3994.5")}


def health(status: FeedStatus = FeedStatus.FRESH, t: int = TEND) -> FeedHealth:
    return FeedHealth(status, (), t, t, t, 0, D("0.2"), None)


class Harness:
    def __init__(
        self, policy: SignalPolicy = FIXTURE, *, side: Side = Side.BUY, m15=(), h1=None, specs=None
    ) -> None:
        mirror = side is Side.SELL
        self.side = side
        self.det = S1Detector("syn-1")
        self.eng = SignalEngine(self.det, policy)
        self.stream = Stream()
        for b in list(h1 if h1 is not None else h1_trend(mirror=mirror)) + list(m15):
            self.det.on_bar(b)
        self.bars = m5(specs or (WARM + PATTERN + [TRIGGER]), mirror=mirror)
        for b in self.bars[:-1]:
            self.det.on_bar(b)

    def quote(self, off: str = "0", t: int = TEND + 500, spread: str = "0.20"):
        """Quote ``off`` price units in the trade direction from the trigger close."""
        bid = CLOSE[self.side] + D(off) if self.side is Side.BUY else CLOSE[self.side] - D(off)
        self.stream.add(t, bid=str(bid), ask=str(bid + D(spread)))
        return self.stream.quotes[-1]

    def first(self, q=None, feed: FeedHealth | None = None, extra_events=()):
        q = q or self.quote()
        bar_events = [self.bars[-1], *extra_events]
        s1 = self.det.process(bar_events, q)
        self.trigger_events = [e for e in s1 if e.kind is S1EventKind.TRIGGER_OBSERVED]
        return self.eng.on_step(q, bar_events, s1, feed or health(t=q.received_time_ms))

    def step(self, q, feed: FeedHealth | None = None, bar_events=()):
        s1 = self.det.process(list(bar_events), q)
        return self.eng.on_step(q, bar_events, s1, feed or health(t=q.received_time_ms))


def gate(ev, name: str):
    return next(g for g in ev.gates if g.gate == name)


# ------------------------------------------------------------------ issuance


M15_RISE = [4000 + i for i in range(50)] + [4049, 4040, 4030, 4040, 4050, 4056, 4060]


def m15_bars(closes):
    base = T10 - len(closes) * 15 * 60_000
    return [
        make_bar(Timeframe.M15, i, str(D(c) + D("0.5")), str(D(c) - D("0.5")), str(c), base_ms=base)
        for i, c in enumerate(closes)
    ]


@pytest.mark.parametrize("side", [Side.BUY, Side.SELL])
def test_ready_on_first_executable_quote(side: Side) -> None:  # SQ-01
    h = Harness(side=side)
    [ev] = h.first()
    assert ev.kind is K.READY_ISSUED and ev.state is SignalState.READY
    sig = h.eng.signals[ev.signal_id]
    q = h.stream.quotes[-1]
    assert sig.e0 == (q.ask if side is Side.BUY else q.bid)  # never the bar close
    assert sig.first_ready_ms == q.received_time_ms > TEND
    assert sig.first_quote_event_key == q.source_event_key
    assert sig.expiry_ms == TEND + M5_MS  # next M5 close after READY
    assert sig.execution_fidelity is ExecutionFidelity.SIMULATED
    assert sig.estimated_cost_model_id is None
    assert (sig.sl0 < q.bid) if side is Side.BUY else (sig.sl0 > q.ask)
    assert sig.tp2 == (
        sig.e0 + 2 * sig.original_risk_price
        if side is Side.BUY
        else sig.e0 - 2 * sig.original_risk_price
    )
    assert gate(ev, "SPREAD").result is GateResult.UNKNOWN and not gate(ev, "SPREAD").blocking
    assert gate(ev, "COST_MODEL").reason is R.COST_UNAVAILABLE
    assert R.COST_UNAVAILABLE in ev.reason_codes


def test_short_stop_from_ask_highs() -> None:  # S1-13 in the full flow
    h = Harness(side=Side.SELL)
    [ev] = h.first()
    sig = h.eng.signals[ev.signal_id]
    trig = h.trigger_events[0].trigger
    assert trig.pullback_ask_extreme == trig.pullback_extreme + D("0.20")
    assert sig.sl0 >= trig.pullback_ask_extreme + D("0.10") * sig.frozen_atr


def test_m15_corrective_and_opposing_do_not_veto() -> None:  # S1-02, SQ-04, ADV-11
    corr = Harness(m15=m15_bars(M15_RISE + [4038]))
    [ev] = corr.first()
    assert ev.kind is K.READY_ISSUED and R.M15_CORRECTIVE in ev.reason_codes
    opp = Harness(m15=m15_bars(M15_RISE + [4025]))
    [ev2] = opp.first()
    assert ev2.kind is K.READY_ISSUED and R.M15_OPPOSING in ev2.reason_codes


def test_strict_m15_veto_is_a_separately_versioned_variant() -> None:  # SQ-05
    policy = replace(FIXTURE, m15_opposing_strict_veto=True)
    h = Harness(policy, m15=m15_bars(M15_RISE + [4025]))
    [ev] = h.first()
    assert ev.kind is K.NOT_ISSUED and R.M15_STRICT_VETO in ev.reason_codes
    assert policy.effective_rules_version.endswith("+M15_STRICT_VETO")
    assert policy.parameter_set_hash != FIXTURE.parameter_set_hash


def test_soft_context_never_changes_economics() -> None:  # SQ-12, ADV-09, SQ-15
    results = []
    for m15 in ((), m15_bars(M15_RISE), m15_bars(M15_RISE + [4038]), m15_bars(M15_RISE + [4025])):
        h = Harness(m15=m15)
        [ev] = h.first()
        s = h.eng.signals[ev.signal_id]
        results.append((ev.kind, s.signal_id, s.e0, s.sl0, s.tp1, s.tp2, s.expiry_ms))
    assert len(set(results)) == 1
    names = {f.name for f in fields(SignalRecord)}
    assert not {n for n in names if "score" in n or "prob" in n or "confidence" in n}


# ------------------------------------------------------------------ OPEN thresholds unset


def test_default_policy_never_issues_ready() -> None:  # approved conservative handling
    h = Harness(SignalPolicy())
    [ev] = h.first(feed=health(FeedStatus.UNKNOWN))
    assert ev.kind is K.NOT_ISSUED and not h.eng.signals
    assert {R.FEED_HEALTH_UNKNOWN, R.QUOTE_DELAY_UNEVALUATED, R.CONTRACT_UNDEFINED} <= set(
        ev.reason_codes
    )
    assert gate(ev, "FIRST_QUOTE_DELAY").result is GateResult.UNKNOWN


def test_missing_price_step_blocks() -> None:  # SQ-10 / ST-09
    h = Harness(replace(FIXTURE, price_step=None))
    [ev] = h.first()
    assert ev.kind is K.NOT_ISSUED and R.CONTRACT_UNDEFINED in ev.reason_codes


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (FeedStatus.STALE, R.DATA_STALE),
        (FeedStatus.DEGRADED, R.DATA_GAP),
        (FeedStatus.CLOSED, R.MARKET_CLOSED),
        (FeedStatus.UNKNOWN, R.FEED_HEALTH_UNKNOWN),
    ],
)
def test_unhealthy_feed_blocks_issuance(status, reason) -> None:  # SQ-03, S1-18 stale
    h = Harness()
    [ev] = h.first(feed=health(status))
    assert ev.kind is not K.READY_ISSUED and reason in ev.reason_codes


def test_h1_unknown_never_reaches_ready() -> None:  # S1-18 partial warm-up, SQ-03
    h = Harness(h1=h1_trend(n=249))
    assert h.first() == [] and not h.eng.signals  # detector never observed a trigger


# ------------------------------------------------------------------ missed first quote


@pytest.mark.parametrize("side", [Side.BUY, Side.SELL])
def test_late_first_quote_is_missed_data_gap(side: Side) -> None:  # S1-08, MD-21, SQ-11
    h = Harness(side=side)
    q = h.quote(t=TEND + 2_001)
    [ev] = h.first(q)
    assert ev.kind is K.MISSED_DATA_GAP and R.QUOTE_DELAY in ev.reason_codes
    assert not h.eng.signals  # the historical close is never a fill
    ok = Harness(side=side)
    assert ok.first(ok.quote(t=TEND + 2_000))[0].kind is K.READY_ISSUED  # boundary inclusive


def test_gap_after_trigger_close_is_missed_even_without_delay_limit() -> None:
    policy = replace(FIXTURE, health=DataHealthPolicy(max_quote_age_ms=5_000))
    h = Harness(policy)
    q = h.quote(t=TEND + 3 * 60_000)
    gap = GapRecord(
        "syn-1", Timeframe.M1, TEND, TEND + 3 * 60_000, 3, GapKind.DATA_GAP, q.received_time_ms
    )
    [ev] = h.first(q, extra_events=[gap])
    assert ev.kind is K.MISSED_DATA_GAP and R.DATA_GAP in ev.reason_codes


@pytest.mark.parametrize("side", [Side.BUY, Side.SELL])
def test_first_quote_beyond_chase_bound(side: Side) -> None:  # S1-09
    h = Harness(side=side)
    # ATR14 M5 here is ~1.61, so the 0.20 ATR bound is ~0.32 from the trigger close.
    [ev] = h.first(h.quote("0.40", spread="0.00"))
    assert ev.kind is K.MISSED_PRICE_CHASE and R.ENTRY_CHASE in ev.reason_codes


def test_first_quote_spread_over_declared_limit_no_ready() -> None:  # ADV-03, SQ-16
    h = Harness(replace(FIXTURE, max_spread=D("0.20")))
    [ev] = h.first(h.quote(spread="0.25"))
    assert ev.kind is K.NOT_ISSUED and R.SPREAD_OVER_LIMIT in ev.reason_codes
    # Spread normalizing later does not create a backdated or late READY (baseline).
    assert h.step(h.quote(t=TEND + 900)) == [] and not h.eng.signals


# ------------------------------------------------------------------ while READY


def ready(side: Side = Side.BUY, policy: SignalPolicy = FIXTURE, **kw):
    h = Harness(policy, side=side, **kw)
    [ev] = h.first()
    assert ev.kind is K.READY_ISSUED
    return h, h.eng.signals[ev.signal_id]


@pytest.mark.parametrize("side", [Side.BUY, Side.SELL])
def test_block_unblock_keeps_same_signal(side: Side) -> None:  # S1-10, SQ-07, ST-03
    h, sig = ready(side)
    snapshot = record_to_dict(sig)
    [blk] = h.step(h.quote("0.80", t=TEND + 1_000))  # beyond +0.20 ATR band
    assert blk.kind is K.EXECUTION_BLOCKED and blk.signal_id == sig.signal_id
    assert R.OUTSIDE_ENTRY_BAND in blk.reason_codes and h.eng.status[sig.signal_id].blocked
    assert h.step(h.quote("0.85", t=TEND + 1_500)) == []  # same reasons: no duplicate event
    [unb] = h.step(h.quote("0", t=TEND + 2_000))
    assert unb.kind is K.EXECUTION_UNBLOCKED and unb.signal_id == sig.signal_id
    assert record_to_dict(h.eng.signals[sig.signal_id]) == snapshot  # E0/SL/TP/TTL immutable
    assert len(h.eng.signals) == 1


def test_confirmation_loss_and_spread_widening_are_reversible() -> None:  # ADV-03
    h, sig = ready(policy=replace(FIXTURE, max_spread=D("0.50")))
    [b1] = h.step(h.quote("0", t=TEND + 1_000, spread="0.70"))
    assert R.SPREAD_OVER_LIMIT in b1.reason_codes
    [u] = h.step(h.quote("0", t=TEND + 1_500))
    assert u.kind is K.EXECUTION_UNBLOCKED
    [b2] = h.step(h.quote("-0.70", t=TEND + 2_000))  # BID below threshold - 0.10 ATR
    assert R.CONFIRMATION_LOST in b2.reason_codes and b2.state is SignalState.READY


@pytest.mark.parametrize("side", [Side.BUY, Side.SELL])
def test_pre_entry_stop_touch_is_terminal(side: Side) -> None:  # S1-11, SQ-08
    h, sig = ready(side)
    dist = (CLOSE[side] - sig.sl0) if side is Side.BUY else (sig.sl0 - CLOSE[side] - D("0.20"))
    [inv] = h.step(h.quote(str(-dist), t=TEND + 1_000))  # BUY: BID == SL; SELL: ASK == SL
    assert inv.kind is K.INVALIDATED and inv.reason_codes == (R.PRE_ENTRY_STOP_TOUCH,)
    assert h.eng.status[sig.signal_id].state is SignalState.INVALIDATED
    assert h.step(h.quote("0", t=TEND + 2_000)) == []  # never resurrects


def test_ttl_expiry_at_next_m5_close() -> None:
    h, sig = ready()
    assert h.step(h.quote("0", t=sig.expiry_ms - 1)) == []
    [exp] = h.step(h.quote("0", t=sig.expiry_ms))
    assert exp.kind is K.EXPIRED and exp.event_time_ms == sig.expiry_ms
    assert exp.reason_codes == (R.SIGNAL_TTL_EXPIRED,)
    assert h.step(h.quote("0", t=sig.expiry_ms + 10)) == []


def test_confirmed_h1_change_invalidates_but_unclosed_does_not() -> None:  # SQ-09
    h1 = h1_trend(end_ms=TEND - HOUR + 2 * 60_000)
    h, sig = ready(h1=h1)
    flip = make_bar(
        Timeframe.H1, 260, "4300", "3950", "3960", base_ms=TEND - HOUR + 2 * 60_000 - 260 * HOUR
    )
    # Before its close the falling H1 bar is not evidence.
    assert h.step(h.quote("0", t=TEND + 60_000)) == []
    q = h.quote("0", t=flip.end_ms + 100)
    [inv] = h.step(q, bar_events=[replace(flip, available_at_ms=q.received_time_ms)])
    assert inv.kind is K.INVALIDATED and inv.reason_codes == (R.H1_BIAS_MISMATCH,)


# ------------------------------------------------------------------ duplicates / exposure


def test_replayed_trigger_never_duplicates() -> None:  # ST-02, SQ-06, ADV-10, S1-20
    h, sig = ready()
    q = h.quote("0", t=TEND + 700)
    again = h.eng.on_step(q, [], h.trigger_events, health(t=q.received_time_ms))
    assert again == [] and len(h.eng.signals) == 1
    issued = [e for e in h.eng.events if e.kind is K.READY_ISSUED]
    assert len(issued) == 1


def test_contradictory_opportunity_requires_review() -> None:  # SQ-14
    h, sig = ready()
    trig = h.trigger_events[0]
    fake = replace(
        trig,
        trigger=replace(trig.trigger, trigger_id="other", side=Side.SELL, candidate_id="S1-SELL-x"),
    )
    q = h.quote("0", t=TEND + 800)
    out = h.eng.on_step(q, [], [fake], health(t=q.received_time_ms))
    [ev] = [e for e in out if e.trigger_id == "other"]
    assert ev.kind is K.NOT_ISSUED and R.EXPOSURE_REVIEW_REQUIRED in ev.reason_codes
    assert len(h.eng.signals) == 1  # no invented ranking or compounded position


def test_first_quote_waits_for_trigger_availability() -> None:
    h = Harness()
    late_bar = replace(h.bars[-1], available_at_ms=TEND + 1_000)
    h.bars[-1] = late_bar
    q0 = h.quote("0", t=TEND + 400)  # provider after close but received before availability
    q0 = replace(q0, received_time_ms=TEND + 400)
    s1 = h.det.process([late_bar], replace(q0, received_time_ms=TEND + 1_000))
    out = h.eng.on_step(q0, [late_bar], s1, health(t=q0.received_time_ms))
    assert out == []  # not causally after the trigger became knowable
    q1 = h.quote("0", t=TEND + 1_200)
    [ev] = h.eng.on_step(q1, [], [], health(t=q1.received_time_ms))
    assert ev.kind is K.READY_ISSUED and h.eng.signals[ev.signal_id].first_ready_ms == TEND + 1_200
