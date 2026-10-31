"""R0 audit regressions F-04 and F-07 (docs/14; docs/07 §6, §6.1; docs/02 §6, §8).

* Every mark carries an explicit freshness; only a FRESH feed under declared thresholds
  yields a FRESH mark. UNKNOWN health (thresholds unset) is UNVERIFIED, never fresh.
* BUY marks at BID, SELL at ASK, whatever the freshness.
* R uses explicit denominators: per-unit move over the frozen per-unit initial risk;
  realized and remaining-position unrealized R over the ORIGINAL full-position risk, so
  they add up; net R is UNKNOWN.
* A price touch never closes a position.
Fixture values are the documented docs/07 §5 illustration, not a live quote.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from grog.analysis.params import CALC_CONTEXT
from grog.domain.clock import FixedClock
from grog.domain.enums import Side, SourceOrigin
from grog.domain.models import NormalizedQuote
from grog.journal.positions import (
    MARK_FRESHNESS,
    EntryRequest,
    PlanRef,
    PositionJournal,
    PositionState,
    TouchTracker,
    mark_freshness,
    mark_position,
    new_action_id,
    r_breakdown,
)
from grog.journal.store import STATE_DB_FILENAME, Store

D = Decimal
T0 = 1_767_607_200_000  # 2026-01-05 10:00:00 UTC (fixture)
SRC = "syn-1"
PLAN = PlanRef(  # docs/07 §5 illustration
    signal_id="S1-BUY-fixture",
    source_id=SRC,
    strategy_version="S1_MTF_V0_2",
    side=Side.BUY,
    e0=D("4000.20"),
    sl0=D("3998.00"),
    tp1=D("4002.40"),
    tp2=D("4004.60"),
    entry_low=D("4000.20"),
    entry_high=D("4000.42"),
    original_risk=D("2.20"),
    first_ready_ms=T0,
    expiry_ms=T0 + 300_000,
    fidelity="SIMULATED",
)


def entry(**kw) -> EntryRequest:
    base = dict(
        action_id=new_action_id(),
        side=Side.BUY,
        price=D("4000.30"),
        qty=D("0.30"),
        fill_ms=T0 + 5_000,
        source_id=SRC,
        plan=PLAN,
        signal_ready=True,
    )
    base.update(kw)
    return EntryRequest(**base)


def quote(bid: str, ask: str, ms: int = T0 + 30_000) -> NormalizedQuote:
    return NormalizedQuote(
        source_id=SRC,
        canonical_symbol="XAUUSD",
        raw_symbol="XAUUSD",
        provider_time_ms=ms,
        received_time_ms=ms,
        ingest_order=1,
        bid=D(bid),
        ask=D(ask),
        source_origin=SourceOrigin.SYNTHETIC,
        source_event_key=f"k{ms}",
    )


@pytest.fixture
def journal(tmp_path: Path):
    store = Store.open(tmp_path / "state" / STATE_DB_FILENAME, FixedClock(1_793_450_000_000))
    yield PositionJournal(store)
    store.close()


@pytest.mark.parametrize(
    ("feed", "ended", "label"),
    [
        ("FRESH", False, "FRESH"),
        ("FRESH", True, "REPLAY_ENDED"),
        ("UNKNOWN", False, "UNVERIFIED"),
        (None, False, "UNVERIFIED"),
        ("STALE", False, "STALE"),
        ("DEGRADED", False, "DEGRADED"),
        ("CLOSED", False, "MARKET_CLOSED"),
        ("NO_DATA", False, "OFFLINE"),
        ("STALE", True, "STALE"),  # a worse feed state is never hidden by playback
    ],
)
def test_mark_freshness_mapping(feed, ended, label) -> None:
    assert mark_freshness(feed, replay_ended=ended) == label
    assert label in MARK_FRESHNESS


def test_only_fresh_feed_gives_fresh_mark_and_others_carry_a_reason(journal) -> None:
    pos, _ = journal.record_entry(entry())
    q = quote("4001.20", "4001.40")
    fresh = mark_position(pos, q, feed_status="FRESH")
    assert fresh.fresh and fresh.reason is None
    for feed in ("UNKNOWN", "STALE", "DEGRADED", "CLOSED", "NO_DATA"):
        m = mark_position(pos, q, feed_status=feed)
        assert not m.fresh and m.reason, feed
        assert m.closeable == D("4001.20")  # last known mark is shown, labeled not fresh
    ended = mark_position(pos, q, feed_status="FRESH", replay_ended=True)
    assert ended.freshness == "REPLAY_ENDED" and "REPLAY ENDED" in ended.reason
    none = mark_position(pos, None)
    assert none.freshness == "UNAVAILABLE" and none.closeable is None


def test_bid_ask_sides_for_marks(journal) -> None:
    buy, _ = journal.record_entry(entry())
    sell, _ = journal.record_entry(
        entry(action_id=new_action_id(), side=Side.SELL, plan=None, stop=D("4002.50"))
    )
    q = quote("4001.20", "4001.40")
    assert mark_position(buy, q).closeable == D("4001.20")
    assert mark_position(buy, q).closeable_side == "BID"
    m = mark_position(sell, q)
    assert m.closeable == D("4001.40") and m.closeable_side == "ASK"
    assert m.unrealized_price_units == (D("4000.30") - D("4001.40")) * D("0.30")


def test_r_denominators_are_explicit_and_add_up(journal) -> None:
    # Entry ASK 4000.30 x 0.30, SL 3998.00 => per-unit risk 2.30, full risk 0.69 units.
    pos, _ = journal.record_entry(entry())
    assert pos.initial_risk == D("2.30")
    pid = pos.position_id
    p1, _ = journal.record_partial(
        new_action_id(), pid, price=D("4002.60"), qty=D("0.10"), fill_ms=T0 + 60_000
    )
    q = quote("4001.45", "4001.65", T0 + 90_000)
    m = mark_position(p1, q)
    rb = r_breakdown(p1, m)
    div = CALC_CONTEXT.divide
    assert rb.original_risk_units == D("0.690")
    assert rb.move_r == div(D("1.15"), D("2.30"))  # 0.5R per unit
    assert rb.realized_r == div(D("2.30") * D("0.10"), D("0.690"))  # 1/3 R
    assert rb.unrealized_r == div(D("1.15") * D("0.20"), D("0.690"))  # 1/3 R
    assert rb.total_r == CALC_CONTEXT.add(rb.realized_r, rb.unrealized_r)
    assert rb.net_r is None  # UNKNOWN: fees/contract not verified
    # A later stop move never rewrites the denominator.
    p2, _ = journal.record_modify(
        new_action_id(), pid, effective_ms=T0 + 95_000, new_stop=D("3990")
    )
    assert r_breakdown(p2, mark_position(p2, q)).original_risk_units == D("0.690")


def test_closed_position_total_equals_realized_and_open_without_mark_is_unknown(journal) -> None:
    pos, _ = journal.record_entry(entry())
    no_mark = r_breakdown(pos, mark_position(pos, None))
    assert no_mark.total_r is None and no_mark.realized_r == 0  # no exits yet: zero, known
    closed, _ = journal.record_close(
        new_action_id(), pos.position_id, price=D("4004.60"), qty=D("0.30"), fill_ms=T0 + 60_000
    )
    rb = r_breakdown(closed)
    assert rb.unrealized_r == 0 and rb.total_r == CALC_CONTEXT.add(0, rb.realized_r)


def test_touch_never_closes_position(journal) -> None:
    pos, _ = journal.record_entry(entry())
    tracker = TouchTracker()
    sl_touch = quote("3997.90", "3998.10", T0 + 30_000)
    tracker.track([pos])
    tracker.on_quote(sl_touch)
    assert "STOP" in tracker.touched(pos)
    again = journal.get(pos.position_id)
    assert again.state is not PositionState.CLOSED and again.remaining_qty == D("0.30")
    assert [e.action.value for e in journal.events(pos.position_id)] == ["ENTRY"]
