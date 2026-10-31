"""Causal per-quote wiring: quotes -> bars -> analysis -> S1 detector -> signal eligibility.

Library-level driver for tests and the later replay command (M06). No wall clock, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from grog.domain.models import NormalizedQuote, S1Event, SignalEvent
from grog.market_data.bars import BarAggregator, BarEvent
from grog.market_data.health import FeedHealth, assess_feed
from grog.signals.engine import SignalEngine, SignalPolicy
from grog.strategies.s1_pullback import S1Detector


@dataclass(frozen=True, slots=True)
class StepResult:
    quote: NormalizedQuote
    bar_events: tuple[BarEvent, ...]
    s1_events: tuple[S1Event, ...]
    health: FeedHealth
    signal_events: tuple[SignalEvent, ...]


class S1ResearchPipeline:
    def __init__(self, source_id: str, policy: SignalPolicy | None = None) -> None:
        self.policy = policy or SignalPolicy()
        self.aggregator = BarAggregator(source_id, self.policy.health)
        self.detector = S1Detector(source_id)
        self.signals = SignalEngine(self.detector, self.policy)

    def on_quote(self, quote: NormalizedQuote) -> StepResult:
        bar_events = self.aggregator.on_quote(quote)
        s1 = self.detector.process(list(bar_events), quote)
        health = assess_feed(
            quote,
            self.aggregator.gaps,
            self.aggregator.history,
            quote.received_time_ms,
            self.policy.health,
        )
        sig = self.signals.on_step(quote, bar_events, s1, health)
        return StepResult(quote, tuple(bar_events), tuple(s1), health, tuple(sig))
