"""S1 research detector (docs/05 Sections 3-6; docs/08 S1-01..07, S1-17..20)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from grog.domain.enums import (
    BarQuality,
    CandidateState,
    H1Bias,
    IndicatorStatus,
    M15Context,
    ReasonCode,
    S1EventKind,
    Side,
    Timeframe,
)
from grog.domain.models import NormalizedQuote
from grog.strategies.s1_pullback import S1_V0_2, S1Detector, record_to_dict
from quote_stream import T10, make_bar

R, K = ReasonCode, S1EventKind
H1, M15, M5 = Timeframe.H1, Timeframe.M15, Timeframe.M5
HOUR = 3_600_000

WARM = [("4000.5", "3999.5", "4000", "4000")] * 16  # equal highs/lows: no pivots, ATR ~ 1
PATTERN = [  # (high, low, open, close) indices 16..23: L at 17 (3998), H at 21 (4006)
    ("4000.5", "3999.0", "4000", "3999.5"),
    ("4000.0", "3998.0", "3999.5", "3999.0"),
    ("4001.0", "3999.0", "3999", "4000.5"),
    ("4003.0", "4000.5", "4000.5", "4002.5"),
    ("4005.0", "4002.0", "4002.5", "4004.5"),
    ("4006.0", "4003.5", "4004.5", "4004.0"),
    ("4005.0", "4003.0", "4004.0", "4003.5"),
    ("4004.0", "4002.5", "4003.5", "4003.0"),  # confirms H; P = 4002.5, d = 0.4375
]
TRIGGER = ("4005.8", "4002.8", "4003.0", "4005.5")  # close 4005.5 > max(4005, 4004), bullish
L_PRICE, H_PRICE, IMPULSE = Decimal("3998.0"), Decimal("4006.0"), Decimal("8.0")
H_CONFIRM = 23  # index of the bar that confirms H


def flip(spec: tuple[str, str, str, str]) -> tuple[str, str, str, str]:
    h, lo, o, c = (Decimal(x) for x in spec)
    return tuple(str(8000 - x) for x in (lo, h, o, c))  # type: ignore[return-value]


def m5(specs, base_ms: int = T10, mirror: bool = False, ask_offset: str = "0.20"):
    out = []
    for i, spec in enumerate(specs):
        h, lo, o, c = flip(spec) if mirror else spec
        out.append(make_bar(M5, i, h, lo, c, o, base_ms=base_ms, ask_offset=ask_offset))
    return out


def h1_trend(up: bool = True, n: int = 260, end_ms: int = T10, mirror: bool = False):
    step = 1 if up else -1
    bars = []
    for i in range(n):
        c = Decimal(4000 + step * i) if up else Decimal(4300 + step * i)
        if mirror:
            c = 8000 - c
        bars.append(make_bar(H1, i, str(c + 1), str(c - 1), str(c), base_ms=end_ms - n * HOUR))
    return bars


def run(specs, *, h1=None, m15=(), mirror: bool = False, ask_offset: str = "0.20"):
    det = S1Detector("syn-1")
    for b in list(h1 if h1 is not None else h1_trend(mirror=mirror)) + list(m15):
        det.on_bar(b)
    for b in m5(specs, mirror=mirror, ask_offset=ask_offset):
        det.on_bar(b)
    return det


def kinds(det, side: Side = Side.BUY, kind: S1EventKind | None = None):
    return [e for e in det.events if e.side is side and (kind is None or e.kind is kind)]


SIDES = [(Side.BUY, False), (Side.SELL, True)]


# ------------------------------------------------------------------ pair formation


@pytest.mark.parametrize(("side", "mirror"), SIDES)
def test_pair_frozen_at_confirmation(side: Side, mirror: bool) -> None:  # S1-03 + identity
    before = run(WARM + PATTERN[:-1], mirror=mirror)
    assert not kinds(before, side, K.CANDIDATE_CREATED)  # only 1 of 2 right bars closed
    det = run(WARM + PATTERN, mirror=mirror)
    [created] = kinds(det, side, K.CANDIDATE_CREATED)
    cand = det.candidates[created.candidate_id]
    pair = cand.pair
    first, second = (17, 21)
    m5_ids = [b.bar_id for b in m5(WARM + PATTERN)]
    assert pair.pair_key == (
        "v0.2-proposal",
        "LONG" if side is Side.BUY else "SHORT",
        m5_ids[first],
        m5_ids[second],
    )
    assert pair.impulse == IMPULSE and pair.impulse_bars == 4
    assert pair.available_at_ms == T10 + (H_CONFIRM + 1) * 5 * 60_000
    assert created.decision_time_ms == pair.available_at_ms
    assert cand.state is CandidateState.FORMING and cand.depth == Decimal("0.4375")
    assert created.strategy_id == "S1" and created.parameter_set_hash == S1_V0_2.parameter_set_hash


def test_pair_never_mutated_by_later_bars() -> None:
    det = run(WARM + PATTERN + [TRIGGER, ("4010", "4004", "4005", "4009")])
    created = kinds(det, Side.BUY, K.CANDIDATE_CREATED)[0]
    cand = det.candidates[created.candidate_id]
    assert cand.pair.high.price == H_PRICE and cand.pair.low.price == L_PRICE


def test_pair_rejections() -> None:
    # Pattern before ATR14 warm-up: ATR unavailable at confirmation (S1-18).
    det = run(WARM[:4] + PATTERN)  # pair confirmed at bar 11 < 15 bars needed for ATR14
    rej = kinds(det, Side.BUY, K.PAIR_REJECTED)
    assert rej and R.M5_ATR_UNAVAILABLE in rej[-1].reason_codes
    # First pivot high without any earlier pivot low.
    only_high = WARM + [("4001", "4000", "4000", "4000.5"), ("4003", "4000.5", "4001", "4002")]
    only_high += [("4002", "4000.6", "4001", "4001")] * 2
    det = run(only_high)
    assert kinds(det, Side.BUY, K.PAIR_REJECTED)[0].reason_codes == (R.NO_PRECEDING_PIVOT,)


def test_impulse_below_atr_rejected() -> None:
    small = [
        tuple(str(Decimal("4000") + (Decimal(x) - 4000) / 10) for x in s) for s in PATTERN
    ]  # same shape, impulse 0.8 < ATR ~ 1
    wide = [("4002", "3999.85", "4000", "4000")] * 16  # ATR ~ 1.3 at confirmation
    det = run(wide + small)
    assert R.IMPULSE_BELOW_ATR in kinds(det, Side.BUY, K.PAIR_REJECTED)[-1].reason_codes


def test_impulse_older_than_12_bars_rejected() -> None:
    rise = [
        (str(4001 + i), str(3999 + i), str(3999 + i), str(4000 + i)) for i in range(1, 14)
    ]  # strictly rising: no pivots between L and H
    top = [("4020", "4011", "4012", "4013"), ("4015", "4012", "4013", "4013")] * 1
    specs = WARM + PATTERN[:2] + rise + [top[0], top[1], ("4014", "4012.5", "4013", "4013")]
    det = run(specs)
    rej = kinds(det, Side.BUY, K.PAIR_REJECTED)
    assert rej and R.IMPULSE_TOO_OLD in rej[-1].reason_codes


def test_gapped_bar_inside_pair_rejected() -> None:
    bars = m5(WARM + PATTERN)
    bars[19] = replace(bars[19], quality=BarQuality.GAPPED)
    det = S1Detector("syn-1")
    for b in h1_trend() + bars:
        det.on_bar(b)
    assert R.DATA_GAP in kinds(det, Side.BUY, K.PAIR_REJECTED)[-1].reason_codes
    assert not kinds(det, Side.BUY, K.CANDIDATE_CREATED)


def test_atr_zero_rejects_pair(monkeypatch: pytest.MonkeyPatch) -> None:  # S1-18
    det = S1Detector("syn-1")
    real = det.engine.context

    def zero_atr(t: int):
        ctx = real(t)
        atr = replace(ctx.atr_values[0], value=Decimal(0), status=IndicatorStatus.ZERO_VALUE)
        return replace(ctx, atr_values=(atr, *ctx.atr_values[1:]))

    monkeypatch.setattr(det.engine, "context", zero_atr)
    for b in h1_trend() + m5(WARM + PATTERN):
        det.on_bar(b)
    assert R.M5_ATR_ZERO in kinds(det, Side.BUY, K.PAIR_REJECTED)[-1].reason_codes


# ------------------------------------------------------------------ trigger


@pytest.mark.parametrize(("side", "mirror"), SIDES)
def test_closed_bar_trigger(side: Side, mirror: bool) -> None:
    det = run(WARM + PATTERN + [TRIGGER], mirror=mirror)
    [obs] = kinds(det, side, K.TRIGGER_OBSERVED)
    t = obs.trigger
    assert t is not None and t.side is side
    assert t.trigger_close_bid == (Decimal("4005.5") if not mirror else Decimal("3994.5"))
    assert t.two_bar_threshold == (Decimal("4005.0") if not mirror else Decimal("3995.0"))
    assert t.available_at_ms == obs.decision_time_ms == T10 + 25 * 5 * 60_000
    assert t.h1_bias is (H1Bias.UP if side is Side.BUY else H1Bias.DOWN)
    assert t.atr_m5_status is IndicatorStatus.VALID and t.atr_m5 > 0
    # Not READY: the detector never emits signal states.
    assert all(e.new_state in (None, *CandidateState) for e in det.events)


@pytest.mark.parametrize(
    ("bar", "reason"),
    [
        (("4006.5", "4002.8", "4003.0", "4004.9"), R.TRIGGER_CLOSE_NOT_BEYOND),  # S1-07 wick only
        (("4005.8", "4002.8", "4003.0", "4005.0"), R.TRIGGER_CLOSE_NOT_BEYOND),  # equal: strict
        (("4005.8", "4002.8", "4005.6", "4005.5"), R.TRIGGER_BODY_WRONG_DIRECTION),
    ],
)
@pytest.mark.parametrize("mirror", [False, True])
def test_no_trigger_without_closed_break(bar, reason: ReasonCode, mirror: bool) -> None:
    side = Side.SELL if mirror else Side.BUY
    det = run(WARM + PATTERN + [bar], mirror=mirror)
    assert not kinds(det, side, K.TRIGGER_OBSERVED)
    assert reason in kinds(det, side, K.CANDIDATE_UPDATED)[-1].reason_codes


@pytest.mark.parametrize(("side", "mirror"), SIDES)
def test_trigger_bar_wick_updates_p_before_acceptance(side: Side, mirror: bool) -> None:  # S1-05
    deeper = ("4005.8", "4001.0", "4003.0", "4005.5")  # P -> 4001, d = 0.625 still healthy
    det = run(WARM + PATTERN + [deeper], mirror=mirror)
    [obs] = kinds(det, side, K.TRIGGER_OBSERVED)
    assert obs.trigger.depth == Decimal("0.625")
    too_deep = ("4005.8", "3999.5", "3999.6", "4005.5")  # d = 0.8125 > 0.75
    det = run(WARM + PATTERN + [too_deep], mirror=mirror)
    assert not kinds(det, side, K.TRIGGER_OBSERVED)
    assert kinds(det, side, K.INVALIDATED)[-1].reason_codes == (R.PULLBACK_INVALID,)


def test_shallow_pullback_is_forming_not_triggered() -> None:
    shallow = PATTERN[:-2] + [
        ("4005.5", "4004.5", "4005", "4005"),
        ("4005.0", "4004.6", "4005", "4004.8"),
    ]
    det = run(WARM + shallow + [("4006.5", "4004.7", "4004.8", "4005.8")])
    upd = kinds(det, Side.BUY, K.CANDIDATE_UPDATED)[-1]
    assert R.PULLBACK_SHALLOW in upd.reason_codes and upd.new_state is CandidateState.FORMING
    assert not kinds(det, Side.BUY, K.TRIGGER_OBSERVED)


@pytest.mark.parametrize(("side", "mirror"), SIDES)
def test_h1_must_match_side(side: Side, mirror: bool) -> None:  # S1-01 / S1-18 warm-up
    opposite = h1_trend(up=False, mirror=mirror)
    det = run(WARM + PATTERN + [TRIGGER], h1=opposite, mirror=mirror)
    assert not kinds(det, side, K.TRIGGER_OBSERVED)
    assert R.H1_BIAS_MISMATCH in kinds(det, side, K.CANDIDATE_UPDATED)[-1].reason_codes
    det = run(WARM + PATTERN + [TRIGGER], h1=h1_trend(n=249, mirror=mirror), mirror=mirror)
    codes = kinds(det, side, K.CANDIDATE_UPDATED)[-1].reason_codes
    assert {R.H1_BIAS_MISMATCH, R.HISTORY_INCOMPLETE} <= set(codes)
    assert not kinds(det, side, K.TRIGGER_OBSERVED)


def test_unfinished_h1_reversal_is_ignored() -> None:  # S1-01
    trigger_end = T10 + 25 * 5 * 60_000
    down = h1_trend(up=False)
    surge = make_bar(H1, 260, "4900", "4040", "4890", base_ms=T10 - 260 * HOUR)
    surge = replace(surge, available_at_ms=trigger_end + 1)  # finalized but not yet available
    det = run(WARM + PATTERN + [TRIGGER], h1=down + [surge])
    assert not kinds(det, Side.BUY, K.TRIGGER_OBSERVED)
    assert kinds(det, Side.BUY, K.CANDIDATE_UPDATED)[-1].h1_bias is H1Bias.DOWN


def test_same_ms_h1_bar_is_used_by_m5_trigger() -> None:
    """An H1 bar finalized by the same quote as the M5 trigger bar is part of its context."""
    trigger_end = T10 + HOUR
    base = trigger_end - 25 * 5 * 60_000
    h1 = h1_trend(n=250, end_ms=trigger_end)
    det = S1Detector("syn-1")
    for b in h1[:-1]:
        det.on_bar(b)
    bars = m5(WARM + PATTERN + [TRIGGER], base_ms=base)
    for b in bars[:-1]:
        det.on_bar(b)
    assert h1[-1].available_at_ms == bars[-1].available_at_ms
    det.process([bars[-1], h1[-1]])  # aggregator order: M5 before H1
    [obs] = kinds(det, Side.BUY, K.TRIGGER_OBSERVED)
    assert obs.trigger.h1_bias is H1Bias.UP and obs.last_confirmed_h1_id == h1[-1].bar_id


def test_m15_corrective_does_not_veto() -> None:  # S1-02
    rise = [4000 + i for i in range(50)] + [4049, 4040, 4030, 4040, 4050, 4056, 4060, 4038]
    m15 = [
        make_bar(
            M15,
            i,
            str(c + Decimal("0.5")),
            str(c - Decimal("0.5")),
            str(c),
            base_ms=T10 - len(rise) * 15 * 60_000,
        )
        for i, c in enumerate(Decimal(x) for x in rise)
    ]
    det = run(WARM + PATTERN + [TRIGGER], m15=m15)
    [obs] = kinds(det, Side.BUY, K.TRIGGER_OBSERVED)
    assert obs.trigger.m15_context is M15Context.CORRECTIVE
    assert R.M15_CORRECTIVE in obs.reason_codes
    # Without any M15 data the context is UNKNOWN: disclosed, still not a veto.
    [obs2] = kinds(run(WARM + PATTERN + [TRIGGER]), Side.BUY, K.TRIGGER_OBSERVED)
    assert obs2.m15_context is M15Context.UNKNOWN and R.M15_UNKNOWN in obs2.reason_codes


def test_at_most_one_trigger_per_candidate() -> None:
    again = ("4008", "4005", "4005.6", "4007.5")
    det = run(WARM + PATTERN + [TRIGGER, again])
    assert len(kinds(det, Side.BUY, K.TRIGGER_OBSERVED)) == 1
    assert R.TRIGGER_ALREADY_OBSERVED in kinds(det, Side.BUY, K.CANDIDATE_UPDATED)[-1].reason_codes


# ------------------------------------------------------------------ invalidation / expiry


FLAT = ("4004.0", "4003.0", "4003.5", "4003.5")  # equal bars: no pivots, no bullish body


@pytest.mark.parametrize(("side", "mirror"), SIDES)
def test_depth_invalidation_is_terminal(side: Side, mirror: bool) -> None:  # S1-06, S1-20
    deep = ("4003.0", "3999.9", "4002.5", "4000.5")  # d = 0.7625 > 0.75
    det = run(WARM + PATTERN + [deep, TRIGGER, ("4008", "4004", "4004.5", "4007.5")], mirror=mirror)
    inv = kinds(det, side, K.INVALIDATED)
    assert len(inv) == 1 and inv[0].reason_codes == (R.PULLBACK_INVALID,)
    assert inv[0].new_state is CandidateState.INVALIDATED
    after = [e for e in kinds(det, side) if e.sequence > inv[0].sequence]
    assert not [e for e in after if e.candidate_id == inv[0].candidate_id]
    assert not kinds(det, side, K.TRIGGER_OBSERVED)


@pytest.mark.parametrize(("side", "mirror"), SIDES)
def test_observed_bid_at_frozen_endpoint_invalidates(side: Side, mirror: bool) -> None:
    det = run(WARM + PATTERN, mirror=mirror)
    endpoint = L_PRICE if not mirror else 8000 - L_PRICE
    t = T10 + (H_CONFIRM + 1) * 5 * 60_000 + 1000

    def quote(bid: Decimal, n: int) -> NormalizedQuote:
        return NormalizedQuote(
            source_id="syn-1",
            canonical_symbol="XAUUSD",
            raw_symbol="XAUUSD",
            provider_time_ms=t + n,
            received_time_ms=t + n,
            ingest_order=n,
            bid=bid,
            ask=bid + Decimal("0.2"),
            source_origin=make_bar(M5, 0, "1", "1").source_origin,
            source_event_key=f"q#{n}",
        )

    near = endpoint + Decimal("0.01") if not mirror else endpoint - Decimal("0.01")
    assert det.on_quote(quote(near, 1)) == []
    [ev] = det.on_quote(quote(endpoint, 2))  # BUY: BID <= L ; SELL: BID >= H
    assert ev.kind is K.INVALIDATED and ev.reason_codes == (R.STRUCTURE_INVALIDATED,)
    assert ev.decision_time_ms == t + 2
    for b in m5(WARM + PATTERN + [TRIGGER], mirror=mirror)[-1:]:
        det.on_bar(b)
    assert not kinds(det, side, K.TRIGGER_OBSERVED)  # never resurrects


def test_expiry_after_more_than_12_post_pivot_bars() -> None:  # S1-20
    specs = WARM + PATTERN + [FLAT] * 10  # post-H bars: 2 + 10 = 12
    det = run(specs)
    assert kinds(det, Side.BUY, K.CANDIDATE_UPDATED)[-1].post_pivot_bars == 12
    assert not kinds(det, Side.BUY, K.EXPIRED)
    det = run(specs + [FLAT, ("4006", "4003.2", "4003.4", "4005.5")])
    [exp] = kinds(det, Side.BUY, K.EXPIRED)
    assert exp.post_pivot_bars == 13 and exp.reason_codes == (R.FORMING_TTL_EXPIRED,)
    assert not kinds(det, Side.BUY, K.TRIGGER_OBSERVED)  # same pair never triggers afterwards
    assert Side.BUY not in det.active


@pytest.mark.parametrize(("side", "mirror"), SIDES)
def test_newer_pair_supersedes_forming(side: Side, mirror: bool) -> None:  # S1-04
    more = [
        ("4004.5", "4002.0", "4003", "4002.5"),
        ("4003.5", "4001.0", "4002.5", "4002.0"),  # pivot low at 25 (4001)
        ("4005.0", "4002.0", "4002.5", "4004.8"),
        ("4007.5", "4004.0", "4004.8", "4007.0"),
        ("4009.0", "4006.0", "4007.0", "4008.5"),
        ("4011.0", "4008.0", "4008.5", "4010.0"),  # pivot high at 29 (4011)
        ("4010.0", "4007.5", "4010.0", "4008.0"),
        ("4009.5", "4007.0", "4008.0", "4008.0"),  # confirms H2
    ]
    no_h1: list = []
    det = run(WARM + PATTERN + more, h1=no_h1, mirror=mirror)
    created = kinds(det, side, K.CANDIDATE_CREATED)
    [sup] = kinds(det, side, K.SUPERSEDED)
    assert len(created) == 2 and sup.candidate_id == created[0].candidate_id
    assert sup.reason_codes == (R.SUPERSEDED_BY_NEWER_PAIR,)
    assert sup.sequence < created[1].sequence
    new = det.candidates[created[1].candidate_id]
    assert new.pair.impulse == Decimal("10.0") and det.active[side] is new
    assert det.candidates[created[0].candidate_id].state is CandidateState.SUPERSEDED
    # At every point at most one FORMING candidate per side.
    forming: dict[str, str] = {}
    for e in kinds(det, side):
        if e.new_state is CandidateState.FORMING:
            forming[e.candidate_id] = e.candidate_id
        elif e.candidate_id in forming:
            del forming[e.candidate_id]
        assert len(forming) <= 1


# ------------------------------------------------------------------ determinism / provenance


def test_ask_prices_never_change_s1_output() -> None:
    a = run(WARM + PATTERN + [TRIGGER])
    b = run(WARM + PATTERN + [TRIGGER], ask_offset="5.00")

    def bid_only(det):
        out = record_to_dict(det.events)
        for e in out:
            if e["trigger"]:
                e["trigger"].pop("pullback_ask_extreme")  # parallel ASK record for SELL stops
        return out

    assert bid_only(a) == bid_only(b)
    ta, tb = (kinds(d, Side.BUY, K.TRIGGER_OBSERVED)[0].trigger for d in (a, b))
    assert tb.pullback_ask_extreme - ta.pullback_ask_extreme == Decimal("4.80")


def test_utc_only_no_local_calendar_effects() -> None:
    """Same bars across a US DST change (2026-11-01 06:00Z) vs. ten days earlier."""

    def strip(det):
        return [(e.kind, e.side, e.reason_codes, e.pullback_extreme, e.depth) for e in det.events]

    out = []
    for base in (T10 + 20 * HOUR - 16 * 5 * 60_000, T10 - 10 * 24 * HOUR):
        det = S1Detector("syn-1")
        for b in h1_trend(end_ms=base) + m5(WARM + PATTERN + [TRIGGER], base_ms=base):
            det.on_bar(b)
        out.append(strip(det))
    assert out[0] == out[1] and any(k is K.TRIGGER_OBSERVED for k, *_ in out[0])


def test_rejects_foreign_or_out_of_order_input() -> None:
    det = S1Detector("syn-1")
    with pytest.raises(ValueError):
        det.on_bar(make_bar(M5, 0, "1", "1", source_id="other"))
    det.on_bar(make_bar(M5, 1, "1", "1"))
    with pytest.raises(ValueError):
        det.on_bar(make_bar(M5, 0, "1", "1"))
