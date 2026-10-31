"""Quotes -> bars -> analysis -> S1 -> signal eligibility (S1-17, M05 Done)."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from grog.domain.enums import ExecutionFidelity, SignalEventKind
from grog.domain.models import DataHealthPolicy
from grog.signals.engine import SignalPolicy
from grog.signals.pipeline import S1ResearchPipeline
from grog.strategies.s1_pullback import record_to_dict
from quote_stream import Stream, stress_stream

# Fixture-only declarations (docs/11 thresholds remain OPEN; never broker values).
FIXTURE = SignalPolicy(
    health=DataHealthPolicy(max_quote_age_ms=120_000, max_first_postclose_delay_ms=60_000),
    price_step=Decimal("0.01"),
)


def run(stream: Stream, policy: SignalPolicy | None = None) -> S1ResearchPipeline:
    pipe = S1ResearchPipeline("syn-1", policy)
    for q in stream.quotes:
        pipe.on_quote(q)
    return pipe


def test_replay_twice_identical_signals() -> None:  # S1-17
    a, b = run(stress_stream(), FIXTURE), run(stress_stream(), FIXTURE)
    assert record_to_dict(a.signals.events) == record_to_dict(b.signals.events)
    assert record_to_dict(list(a.signals.signals.values())) == record_to_dict(
        list(b.signals.signals.values())
    )
    kinds = Counter(e.kind for e in a.signals.events)
    triggers = sum(
        1 for e in a.detector.events if e.trigger is not None and e.kind.value == "TRIGGER_OBSERVED"
    )
    # Every trigger observation gets exactly one first-quote decision.
    decided = sum(
        kinds[k]
        for k in (
            SignalEventKind.READY_ISSUED,
            SignalEventKind.NOT_ISSUED,
            SignalEventKind.MISSED_DATA_GAP,
            SignalEventKind.MISSED_PRICE_CHASE,
        )
    )
    assert triggers > 0 and decided == triggers
    assert kinds[SignalEventKind.READY_ISSUED] > 0  # fixture-declared thresholds only


def test_signal_invariants_on_stress_fixture() -> None:
    stream = stress_stream()
    pipe = run(stream, FIXTURE)
    by_key = {q.source_event_key: q for q in stream.quotes}
    triggers = {e.trigger.trigger_id: e.trigger for e in pipe.detector.events if e.trigger}
    per_candidate = Counter(s.candidate_id for s in pipe.signals.signals.values())
    assert all(n == 1 for n in per_candidate.values())
    for sig in pipe.signals.signals.values():
        q = by_key[sig.first_quote_event_key]
        trig = triggers[sig.trigger_id]
        assert sig.first_ready_ms == q.received_time_ms >= trig.available_at_ms
        assert sig.e0 == (q.ask if sig.side.value == "BUY" else q.bid)
        assert sig.execution_fidelity is ExecutionFidelity.SIMULATED
    terminal = {}
    for e in pipe.signals.events:
        if e.signal_id in terminal:
            raise AssertionError("signal event after terminal state")
        if e.kind in (SignalEventKind.EXPIRED, SignalEventKind.INVALIDATED):
            terminal[e.signal_id] = e


def test_default_policy_has_no_ready_and_explains_why() -> None:
    pipe = run(stress_stream())
    assert not pipe.signals.signals
    events = pipe.signals.events
    assert events and all(e.kind is not SignalEventKind.READY_ISSUED for e in events)
    assert all(
        "QUOTE_DELAY_UNEVALUATED" in e.reason_codes or "DATA_GAP" in e.reason_codes for e in events
    )
