"""Quote stream -> bars -> MTF analysis: causal and reproducible (S1-01, S1-17, M03 Done)."""

from __future__ import annotations

from grog.analysis.contexts import AnalysisEngine, context_to_dict
from grog.domain.enums import H1Bias, Timeframe
from grog.market_data.bars import BarAggregator
from quote_stream import MIN, T10, Stream

DAYS = 11


def stress_stream(seed: int = 7) -> Stream:
    """~11 days of 1-minute quotes: LCG random walk, a trend, an outage and late receipts."""
    s = Stream()
    state, cents = seed, 400_000
    for i in range(DAYS * 24 * 60):
        if 5000 <= i < 5040:  # 40-minute data outage -> GAPPED bars
            continue
        state = (state * 1103515245 + 12345) % 2**31
        cents += (state >> 16) % 61 - 30 + (3 if (i // 1440) % 2 == 0 else -2)
        t = T10 + i * MIN
        late = 50_000 if i % 997 == 0 else (state >> 8) % 3  # some late receipts
        spread = 15 + (state >> 4) % 20
        s.add(
            t,
            bid=f"{cents // 100}.{cents % 100:02d}",
            ask=f"{(cents + spread) // 100}.{(cents + spread) % 100:02d}",
            received_ms=t + late if not s.quotes else max(t + late, s.quotes[-1].received_time_ms),
        )
    return s


def run(stream: Stream, every: int = 60) -> tuple[AnalysisEngine, BarAggregator, list[dict]]:
    """Live replay: after each quote feed new bars, sampling contexts at quote receipt times."""
    agg, eng = BarAggregator("syn-1"), AnalysisEngine("syn-1")
    snapshots = []
    for n, q in enumerate(stream.quotes):
        eng.on_events(agg.on_quote(q))
        if n % every == 0:
            snapshots.append(context_to_dict(eng.context(q.received_time_ms)))
    return eng, agg, snapshots


def test_replay_twice_identical() -> None:  # S1-17 (analysis layer)
    a = run(stress_stream())[2]
    b = run(stress_stream())[2]
    assert a == b
    final = a[-1]
    assert final["h1_bias"] in {b.value for b in H1Bias if b is not H1Bias.UNKNOWN}
    assert "H1_HISTORY_IRREGULAR" in final["quality_flags"]  # outage is visible, not hidden


def test_live_context_equals_fresh_engine_on_available_bars() -> None:  # no lookahead
    stream = stress_stream()
    full, agg, live = run(stream)
    times = [q.received_time_ms for n, q in enumerate(stream.quotes) if n % 60 == 0]
    for idx in range(0, len(times), 37):
        t = times[idx]
        fresh = AnalysisEngine("syn-1")
        for tf in (Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1):
            for bar in agg.history.available(tf, t):
                fresh.on_bar(bar)
        expected = context_to_dict(fresh.context(t))
        assert live[idx] == expected
        assert context_to_dict(full.context(t)) == expected  # later data cannot leak back


def test_unfinished_h1_never_used() -> None:  # S1-01 via the real pipeline
    stream = stress_stream()
    eng, agg, _ = run(stream)
    for q in stream.quotes[::500]:
        ctx = eng.context(q.received_time_ms)
        last = agg.history.last_closed(Timeframe.H1, q.received_time_ms)
        assert ctx.last_confirmed_h1_id == (last.bar_id if last else None)
        if last is not None:
            assert last.end_ms <= q.received_time_ms
