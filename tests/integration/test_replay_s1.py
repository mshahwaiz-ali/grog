"""Quotes -> bars -> analysis -> S1 detector: causal and reproducible (S1-17, M04 Done)."""

from __future__ import annotations

from collections import Counter

from grog.domain.enums import CandidateState, S1EventKind, Side
from grog.market_data.bars import BarAggregator
from grog.strategies.s1_pullback import S1Detector, record_to_dict
from quote_stream import Stream, stress_stream


def run(stream: Stream, limit: int | None = None) -> S1Detector:
    agg, det = BarAggregator("syn-1"), S1Detector("syn-1")
    for q in stream.quotes[:limit]:
        det.process(agg.on_quote(q), q)
    return det


def test_replay_twice_identical_trace() -> None:  # S1-17
    a, b = run(stress_stream()), run(stress_stream())
    assert record_to_dict(a.events) == record_to_dict(b.events)
    assert record_to_dict(list(a.candidates.values())) == record_to_dict(
        list(b.candidates.values())
    )
    counts = Counter(e.kind for e in a.events)
    # The stress fixture exercises formation and terminal paths, not only the happy path.
    assert counts[S1EventKind.CANDIDATE_CREATED] > 0 and counts[S1EventKind.PAIR_REJECTED] > 0
    assert counts[S1EventKind.INVALIDATED] + counts[S1EventKind.EXPIRED] > 0
    assert counts[S1EventKind.SUPERSEDED] > 0 and counts[S1EventKind.TRIGGER_OBSERVED] > 0


def test_prefix_replay_is_causal() -> None:
    """Events emitted from a truncated stream are exactly the prefix of the full run."""
    stream = stress_stream()
    full = record_to_dict(run(stream).events)
    for limit in (3000, 7777, 12000):
        part = record_to_dict(run(stream, limit).events)
        assert full[: len(part)] == part
        cutoff = stream.quotes[limit - 1].received_time_ms
        assert all(e["decision_time_ms"] <= cutoff for e in part)


def test_trace_invariants() -> None:
    det = run(stress_stream())
    forming: dict[Side, set[str]] = {Side.BUY: set(), Side.SELL: set()}
    terminal: set[str] = set()
    triggers = Counter()
    for e in det.events:
        assert e.decision_time_ms >= e.event_time_ms or e.kind is S1EventKind.INVALIDATED
        if e.candidate_id in terminal:
            raise AssertionError(f"terminal candidate resurrected: {e}")
        if e.new_state is CandidateState.FORMING:
            forming[e.side].add(e.candidate_id)
        elif e.new_state is not None:
            forming[e.side].discard(e.candidate_id)
            terminal.add(e.candidate_id)
        assert len(forming[e.side]) <= 1  # at most one FORMING per side
        if e.kind is S1EventKind.TRIGGER_OBSERVED:
            triggers[e.candidate_id] += 1
            t = e.trigger
            assert t.available_at_ms == e.decision_time_ms >= t.trigger_bar_end_ms
    assert all(n == 1 for n in triggers.values())
    keys = [c.pair.pair_key for c in det.candidates.values()]
    assert len(keys) == len(set(keys))  # one candidate per frozen pair
