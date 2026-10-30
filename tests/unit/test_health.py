"""Feed health and finalization timing (docs/03 §3, §10; MD-03/04/08/09/21)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from grog.domain.enums import FeedStatus, FinalizationTiming, Timeframe
from grog.domain.models import DataHealthPolicy, MarketClosure
from grog.market_data.bars import BarHistory, aggregate
from grog.market_data.health import assess_feed, classify_finalization, unresolved_data_gap
from grog.market_data.import_csv import CsvImportError, parse_canonical_csv
from quote_stream import MIN, T10, S, Stream

# Explicit TEST-ONLY thresholds. Real values are OPEN (docs/11 §6.2) and never defaulted.
TEST_POLICY = DataHealthPolicy(max_quote_age_ms=5 * S, max_first_postclose_delay_ms=5 * S)


def health(agg, now, policy):
    return assess_feed(agg.last_quote, agg.gaps, agg.history, now, policy)


def test_no_data() -> None:
    h = assess_feed(None, [], BarHistory(), T10, DataHealthPolicy())
    assert h.status is FeedStatus.NO_DATA and not h.allows_new_signals


def test_unset_threshold_is_unknown_not_fresh() -> None:
    agg = aggregate("syn-1", Stream().add(T10).quotes)
    h = health(agg, T10 + 2 * S, DataHealthPolicy())
    assert h.status is FeedStatus.UNKNOWN and h.reasons == ("STALE_THRESHOLD_UNSET",)
    assert h.quote_age_ms == 2 * S and not h.allows_new_signals
    assert h.spread == Decimal("0.20")


def test_fresh_and_stale_boundary() -> None:
    agg = aggregate("syn-1", Stream().add(T10).quotes)
    assert health(agg, T10 + 5 * S, TEST_POLICY).status is FeedStatus.FRESH
    stale = health(agg, T10 + 5 * S + 1, TEST_POLICY)
    assert stale.status is FeedStatus.STALE and not stale.allows_new_signals


def test_declared_closure_is_closed_not_outage() -> None:  # MD-09
    agg = aggregate("syn-1", Stream().add(T10).quotes)
    policy = DataHealthPolicy(
        max_quote_age_ms=5 * S, market_closures=(MarketClosure(T10 + MIN, T10 + 60 * MIN),)
    )
    assert health(agg, T10 + 30 * MIN, policy).status is FeedStatus.CLOSED
    assert health(agg, T10 + 61 * MIN, policy).status is FeedStatus.STALE


def test_lookahead_assessment_rejected() -> None:
    agg = aggregate("syn-1", Stream().add(T10 + S).quotes)
    with pytest.raises(ValueError, match="lookahead"):
        health(agg, T10, TEST_POLICY)


def health_at(stream: Stream, now: int, policy: DataHealthPolicy):
    """Replay only the quotes received by ``now`` (causal), then assess."""
    agg = aggregate("syn-1", [q for q in stream.quotes if q.received_time_ms <= now])
    return agg, health(agg, now, policy)


def test_data_gap_degrades_until_a_complete_m5_follows() -> None:  # MD-08
    s = Stream().every(T10, T10 + 2 * MIN, S).every(T10 + 6 * MIN, T10 + 16 * MIN, S)
    _, before = health_at(s, T10 + 2 * MIN, TEST_POLICY)
    assert before.status is FeedStatus.FRESH  # gap not yet knowable
    _, during = health_at(s, T10 + 6 * MIN + 30 * S, TEST_POLICY)
    assert during.status is FeedStatus.DEGRADED and not during.allows_new_signals
    assert during.unresolved_gap is not None
    assert (during.unresolved_gap.from_ms, during.unresolved_gap.to_ms) == (
        T10 + 2 * MIN,
        T10 + 6 * MIN,
    )
    # M5 10:05 contains missing minute 10:05 -> GAPPED; M5 10:10 is complete at 10:15.
    agg, later = health_at(s, T10 + 14 * MIN, TEST_POLICY)
    assert later.status is FeedStatus.DEGRADED
    assert [b.quality.value for b in agg.history.all(Timeframe.M5)] == [
        "GAPPED",
        "GAPPED",
    ]
    agg, restored = health_at(s, T10 + 15 * MIN, TEST_POLICY)
    assert restored.status is FeedStatus.FRESH and restored.unresolved_gap is None
    assert unresolved_data_gap(agg.gaps, agg.history, T10 + 15 * MIN) is None


def test_stale_has_priority_over_degraded() -> None:
    s = Stream().every(T10, T10 + 2 * MIN, S).add(T10 + 6 * MIN)
    agg = aggregate("syn-1", s.quotes)
    h = health(agg, T10 + 7 * MIN, TEST_POLICY)
    assert h.status is FeedStatus.STALE and "UNRESOLVED_DATA_GAP" in h.reasons


def test_late_first_postclose_quote_is_missed_data_gap() -> None:  # MD-21
    s = (
        Stream()
        .add(T10, "4000.00")
        .add(T10 + 4 * MIN, "4001.00")
        .add(T10 + 5 * MIN + 40 * S, "4010.00")
    )
    agg = aggregate("syn-1", s.quotes)
    (m5,) = agg.history.all(Timeframe.M5)
    assert m5.close_bid == Decimal("4001.00")  # no fictitious price at 10:05:00
    assert m5.available_at_ms == T10 + 5 * MIN + 40 * S
    assert classify_finalization(m5, DataHealthPolicy()) is FinalizationTiming.NOT_EVALUATED
    assert classify_finalization(m5, TEST_POLICY) is FinalizationTiming.MISSED_DATA_GAP
    closed = DataHealthPolicy(
        max_first_postclose_delay_ms=5 * S,
        market_closures=(MarketClosure(T10 + 5 * MIN, T10 + 6 * MIN),),
    )
    assert classify_finalization(m5, closed) is FinalizationTiming.MARKET_CLOSED


def test_finalization_delay_boundary_is_on_time() -> None:
    s = Stream().add(T10).add(T10 + 5 * MIN + 5 * S)
    (m5,) = aggregate("syn-1", s.quotes).history.all(Timeframe.M5)
    assert classify_finalization(m5, TEST_POLICY) is FinalizationTiming.ON_TIME


def test_invalid_quotes_never_reach_bars() -> None:  # MD-04
    data = b"provider_time_utc_ms,received_time_utc_ms,bid,ask\n1,1,4000.2,4000.1\n"
    with pytest.raises(CsvImportError):
        parse_canonical_csv(data, source_id="syn-1", origin="SYNTHETIC")


def test_one_side_change_keeps_actual_other_side() -> None:  # MD-03 (CSV v1 has both sides)
    s = Stream().add(T10, "4000.00", "4000.30").add(T10 + S, "4000.10", "4000.30").add(T10 + MIN)
    (m1,) = aggregate("syn-1", s.quotes).history.all(Timeframe.M1)
    assert (m1.close_bid, m1.close_ask) == (Decimal("4000.10"), Decimal("4000.30"))
    assert m1.close_ask - m1.close_bid == Decimal("0.20")  # no invented zero spread
