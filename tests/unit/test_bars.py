"""Causal multi-timeframe bars (docs/03 §2, docs/04 §3; MD-01/05/06/07/10/13/17/20/22)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from grog.domain.clock import ReplayClock
from grog.domain.enums import BarQuality, GapKind, SourceOrigin, Timeframe
from grog.domain.models import (
    DataHealthPolicy,
    FinalizedBar,
    GapRecord,
    MarketClosure,
)
from grog.market_data.bars import BarAggregator, aggregate, bar_to_dict, bucket_start, gap_to_dict
from grog.market_data.import_csv import parse_canonical_csv
from quote_stream import MIN, T10, S, Stream

M1, M5, M15, H1 = Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1


def bars(agg: BarAggregator, tf: Timeframe) -> tuple[FinalizedBar, ...]:
    return agg.history.all(tf)


def test_bucket_start_is_utc_epoch_aligned() -> None:
    assert bucket_start(T10 + 4 * MIN + 59_999, M5) == T10
    assert bucket_start(T10 + 5 * MIN, M5) == T10 + 5 * MIN
    assert bucket_start(T10 + 59 * MIN, H1) == T10
    assert all(tf.duration_ms % MIN == 0 for tf in Timeframe)


def test_exact_1005_boundary_and_actual_finalizing_quote() -> None:  # MD-06
    s = Stream().add(T10, "4000.00").add(T10 + 4 * MIN + 59_999, "4001.00")
    s.add(T10 + 5 * MIN + 11 * S, "4002.00")  # first post-close quote at 10:05:11
    agg = aggregate("syn-1", s.quotes)
    (m5,) = bars(agg, M5)
    assert (m5.start_ms, m5.end_ms) == (T10, T10 + 5 * MIN)
    assert m5.close_bid == Decimal("4001.00") and m5.tick_count == 2
    assert m5.available_at_ms == T10 + 5 * MIN + 11 * S
    assert m5.closing_event_key == "test#3" and m5.finalization_delay_ms == 11 * S
    h = agg.history
    assert h.last_closed(M5, T10 + 4 * MIN + 59_999) is None  # not evidence at 10:04:59.999
    assert h.last_closed(M5, T10 + 5 * MIN) is None  # mathematical end is not availability
    assert h.last_closed(M5, T10 + 5 * MIN + 10_999) is None
    assert h.last_closed(M5, T10 + 5 * MIN + 11 * S) == m5


def test_quote_exactly_at_end_starts_next_bar() -> None:
    agg = aggregate("syn-1", Stream().add(T10, "1.00").add(T10 + 5 * MIN, "2.00").quotes)
    (m5,) = bars(agg, M5)
    assert m5.close_bid == Decimal("1.00") and m5.available_at_ms == T10 + 5 * MIN


def test_docs_example_newest_usable_bars_at_100720() -> None:  # docs/04 §3, MD-07
    s = Stream().every(T10 - 2 * 60 * MIN, T10 + 7 * MIN + 21 * S, S)
    agg = aggregate("syn-1", s.quotes)
    now = T10 + 7 * MIN + 20 * S
    h = agg.history
    assert h.last_closed(H1, now).start_ms == T10 - 60 * MIN  # 09:00-10:00
    assert h.last_closed(M15, now).start_ms == T10 - 15 * MIN  # 09:45-10:00
    assert h.last_closed(M5, now).start_ms == T10  # 10:00-10:05
    assert h.last_closed(M1, now).start_ms == T10 + 6 * MIN  # 10:06-10:07
    assert all(b.quality is BarQuality.COMPLETE for tf in Timeframe for b in bars(agg, tf))


def test_unfinished_higher_timeframe_never_leaks() -> None:  # MD-07
    s = Stream().every(T10 - 60 * MIN, T10 + 30 * MIN, 10 * S)
    s.add(T10 + 30 * MIN, "4100.00")  # strong move inside the current H1
    agg = aggregate("syn-1", s.quotes)
    now = T10 + 30 * MIN
    assert agg.history.last_closed(H1, now).start_ms == T10 - 60 * MIN
    assert [b.start_ms for b in bars(agg, H1)] == [T10 - 60 * MIN]  # current H1 is not a bar
    assert all(b.end_ms <= now for tf in Timeframe for b in agg.history.available(tf, now))


def test_last_open_bar_is_never_finalized() -> None:
    agg = aggregate("syn-1", Stream().every(T10, T10 + 3 * MIN, S).quotes)
    assert len(bars(agg, M1)) == 2 and bars(agg, M5) == ()


def test_bid_and_ask_extremes_are_independent() -> None:  # MD-17
    s = Stream()
    s.add(T10, "4000.00", "4000.20")
    s.add(T10 + S, "4003.00", "4003.05")  # BID high
    s.add(T10 + 2 * S, "4001.00", "4004.00")  # ASK high from a different tick
    s.add(T10 + 3 * S, "3998.00", "3999.50")  # BID low
    s.add(T10 + 4 * S, "3999.00", "3999.10")  # ASK low
    s.add(T10 + MIN, "4000.00", "4000.20")
    (m1,) = bars(aggregate("syn-1", s.quotes), M1)
    assert (m1.open_bid, m1.high_bid, m1.low_bid, m1.close_bid) == tuple(
        map(Decimal, ("4000.00", "4003.00", "3998.00", "3999.00"))
    )
    assert (m1.open_ask, m1.high_ask, m1.low_ask, m1.close_ask) == tuple(
        map(Decimal, ("4000.20", "4004.00", "3999.10", "3999.10"))
    )


def test_same_ms_quotes_all_counted() -> None:  # MD-01
    s = Stream().add(T10, "1.00").add(T10, "1.01").add(T10, "1.02").add(T10 + MIN, "1.03")
    (m1,) = bars(aggregate("syn-1", s.quotes), M1)
    assert m1.tick_count == 3 and m1.close_bid == Decimal("1.02")


def test_no_synthetic_empty_bars_and_gap_records() -> None:  # MD-08
    s = Stream().add(T10 + 30 * S).add(T10 + 3 * MIN + 30 * S).add(T10 + 5 * MIN + 10 * S)
    agg = aggregate("syn-1", s.quotes)
    assert [b.start_ms for b in bars(agg, M1)] == [T10, T10 + 3 * MIN]  # 10:01/10:02 absent
    gaps = [g for g in agg.gaps if g.timeframe is M1]
    assert [(g.from_ms, g.to_ms, g.missing_bars, g.kind) for g in gaps] == [
        (T10 + MIN, T10 + 3 * MIN, 2, GapKind.DATA_GAP),
        (T10 + 4 * MIN, T10 + 5 * MIN, 1, GapKind.DATA_GAP),
    ]
    assert gaps[0].detected_at_ms == T10 + 3 * MIN + 30 * S
    (m5,) = bars(agg, M5)
    assert m5.quality is BarQuality.GAPPED and m5.missing_m1_buckets == 3
    assert all(b.quality is BarQuality.COMPLETE for b in bars(agg, M1))


def test_declared_closure_is_not_a_data_gap() -> None:  # MD-09
    s = Stream().add(T10 + 30 * S).add(T10 + 3 * MIN + 30 * S).add(T10 + 4 * MIN).add(T10 + 5 * MIN)
    policy = DataHealthPolicy(market_closures=(MarketClosure(T10 + MIN, T10 + 3 * MIN),))
    agg = aggregate("syn-1", s.quotes, policy)
    (gap,) = [g for g in agg.gaps if g.timeframe is M1]
    assert gap.kind is GapKind.MARKET_CLOSED
    (m5,) = bars(agg, M5)
    assert m5.quality is BarQuality.COMPLETE and m5.missing_m1_buckets == 0


def test_provider_ahead_of_receipt_never_available_before_end() -> None:  # MD-05
    s = Stream().add(T10, received_ms=T10).add(T10 + 5 * MIN, received_ms=T10 + 5 * MIN - 10)
    agg = aggregate("syn-1", s.quotes)
    (m5,) = bars(agg, M5)
    assert m5.closed_at_received_ms == T10 + 5 * MIN - 10
    assert m5.available_at_ms == T10 + 5 * MIN and m5.finalization_delay_ms == 0
    assert agg.history.last_closed(M5, T10 + 5 * MIN - 10) is None


def test_backfill_bars_labeled_and_only_available_on_arrival() -> None:  # MD-10
    s = Stream("ref-1")
    s.every(T10, T10 + 2 * MIN, 10 * S, origin=SourceOrigin.REFERENCE_LIVE)
    reconnect = T10 + 10 * MIN
    for i, t in enumerate(range(T10 + 2 * MIN, T10 + 10 * MIN, 10 * S)):
        s.add(t, received_ms=reconnect + i, origin=SourceOrigin.BACKFILL)
    s.add(T10 + 10 * MIN + 1, received_ms=reconnect + 100, origin=SourceOrigin.REFERENCE_LIVE)
    agg = aggregate("ref-1", s.quotes)
    m5 = bars(agg, M5)
    assert [b.source_origin for b in m5] == [SourceOrigin.BACKFILL, SourceOrigin.BACKFILL]
    assert all(b.available_at_ms >= reconnect for b in m5)
    assert agg.history.last_closed(M5, T10 + 5 * MIN + 30 * S) is None  # no on-time bar
    m1 = bars(agg, M1)
    assert m1[0].source_origin is SourceOrigin.REFERENCE_LIVE
    assert m1[1].source_origin is SourceOrigin.BACKFILL  # finalized by a backfill quote


def test_mixed_synthetic_and_historical_rejected() -> None:
    s = Stream().add(T10).add(T10 + S, origin=SourceOrigin.HISTORICAL).add(T10 + MIN)
    with pytest.raises(ValueError, match="mix origins"):
        aggregate("syn-1", s.quotes)


def test_sources_never_merged() -> None:  # MD-13
    a = Stream("broker-a").add(T10, "4000.00").add(T10 + MIN, "4000.00")
    b = Stream("broker-b").add(T10, "4000.50").add(T10 + MIN, "4000.50")
    agg = BarAggregator("broker-a")
    agg.feed(a.quotes)
    with pytest.raises(ValueError, match="broker-b"):
        agg.on_quote(b.quotes[0])
    agg_b = aggregate("broker-b", b.quotes)
    assert bars(agg, M1)[0].close_bid != bars(agg_b, M1)[0].close_bid


@pytest.mark.parametrize("field", ["provider", "received"])
def test_out_of_order_input_rejected(field: str) -> None:
    s = Stream().add(T10 + S, received_ms=T10 + S)
    if field == "provider":
        s.add(T10, received_ms=T10 + 2 * S)
    else:
        s.add(T10 + 2 * S, received_ms=T10)
    with pytest.raises(ValueError, match="out of order"):
        aggregate("syn-1", s.quotes)


def test_us_dst_transition_has_no_effect_on_utc_buckets() -> None:  # MD-20
    dst_end = 1793512800000  # 2026-11-01T06:00:00Z (US clocks fall back at 02:00 EDT)
    s = Stream().every(dst_end - 2 * 60 * MIN, dst_end + 2 * 60 * MIN + MIN, 30 * S)
    agg = aggregate("syn-1", s.quotes)
    h1 = bars(agg, H1)
    assert [b.start_ms for b in h1] == [dst_end - 2 * 3600 * S + i * 3600 * S for i in range(4)]
    assert all(b.end_ms - b.start_ms == 3600 * S for b in h1) and agg.gaps == []


def test_weekend_gap_declared_vs_undeclared() -> None:  # MD-20, MD-09
    fri_close = 1793394000000  # 2026-10-30T21:00:00Z (synthetic closure, not real hours)
    sun_open = fri_close + 49 * 3600 * S
    s = (
        Stream()
        .every(fri_close - 60 * MIN, fri_close, MIN)
        .every(sun_open, sun_open + 61 * MIN, MIN)
    )
    undeclared = aggregate("syn-1", s.quotes)
    (h1_gap,) = [g for g in undeclared.gaps if g.timeframe is H1]
    assert (h1_gap.missing_bars, h1_gap.kind) == (49, GapKind.DATA_GAP)
    policy = DataHealthPolicy(market_closures=(MarketClosure(fri_close, sun_open),))
    declared = aggregate("syn-1", s.quotes, policy)
    assert {g.kind for g in declared.gaps} == {GapKind.MARKET_CLOSED}
    assert len(bars(declared, H1)) == 2  # no fabricated weekend bars


def test_replay_clock_follows_receipt_time() -> None:
    clock = ReplayClock()
    agg = BarAggregator("syn-1", clock=clock)
    assert not clock.started
    agg.feed(Stream().add(T10, received_ms=T10 + 5).add(T10 + S, received_ms=T10 + S + 7).quotes)
    assert clock.now_ms() == T10 + S + 7
    with pytest.raises(ValueError):
        clock.advance_to(T10)
    with pytest.raises(RuntimeError):
        ReplayClock().now_ms()


def _csv(n: int) -> bytes:
    rows = ["provider_time_utc_ms,received_time_utc_ms,bid,ask"]
    for i in range(n):
        t = T10 - 3 * 3600 * S + i * 700 + (i // 997) * 5 * MIN  # periodic synthetic gaps
        price = Decimal("4000.00") + Decimal(i % 377) / 100
        rows.append(f"{t},{t + i % 13},{price},{price + Decimal('0.25')}")
    return ("\n".join(rows) + "\n").encode()


def test_same_bytes_give_identical_bars_and_gaps_twice() -> None:  # MD-22, M02 Done
    data = _csv(20000)

    def run() -> tuple[list, list]:
        quotes = parse_canonical_csv(data, source_id="syn-1", origin="SYNTHETIC").quotes
        agg = aggregate("syn-1", quotes)
        return (
            [bar_to_dict(b) for tf in Timeframe for b in bars(agg, tf)],
            [gap_to_dict(g) for g in agg.gaps],
        )

    first, second = run(), run()
    assert first == second
    assert {d["timeframe"] for d in first[0]} == {"M1", "M5", "M15", "H1"}
    assert first[1], "fixture should contain gaps"


def test_events_returned_in_fixed_order() -> None:
    s = Stream().add(T10).add(T10 + 2 * 60 * MIN)
    agg = BarAggregator("syn-1")
    agg.on_quote(s.quotes[0])
    events = agg.on_quote(s.quotes[1])
    kinds = [(type(e).__name__, e.timeframe.value) for e in events]
    assert kinds == [
        ("FinalizedBar", "M1"),
        ("GapRecord", "M1"),
        ("FinalizedBar", "M5"),
        ("GapRecord", "M5"),
        ("FinalizedBar", "M15"),
        ("GapRecord", "M15"),
        ("FinalizedBar", "H1"),
        ("GapRecord", "H1"),
    ]
    assert isinstance(events[1], GapRecord)
