"""Interactive replay session: causal pre-roll, paused start, step/play pacing (docs/02 §9A).

Pure and UI-agnostic (no Textual/Rich/sqlite3): the Textual workstation drives this object
and renders its immutable :class:`Snapshot`. Pacing only decides how many quotes are
processed per wall-clock slice; every quote is still processed exactly once, in stable
source order, on the virtual clock of the quotes themselves. Nothing here schedules on
wall time or changes event/availability timestamps.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from grog.domain.enums import (
    CandidateState,
    FeedStatus,
    IndicatorStatus,
    S1EventKind,
    SignalEventKind,
    SignalState,
    Timeframe,
)
from grog.domain.models import (
    AnalysisContext,
    FinalizedBar,
    GapRecord,
    NormalizedQuote,
    S1Candidate,
    SignalRecord,
)
from grog.market_data.health import FeedHealth, assess_feed
from grog.signals.engine import SignalPolicy, SignalStatus
from grog.signals.pipeline import S1ResearchPipeline

FEED_LIMIT = 50  # docs/02 §11: at most 50 visible event rows in the UI buffer
PACES: tuple[int | None, ...] = (50, 500, None)  # events/s; None = FAST (unthrottled)
FAST_SLICE_EVENTS = 5_000  # FAST work slice per UI tick; keeps keyboard responsive

# Meaningful state changes for the event strip (docs/02 §2: not every tick / update).
_STRIP_S1 = {
    S1EventKind.CANDIDATE_CREATED,
    S1EventKind.SUPERSEDED,
    S1EventKind.INVALIDATED,
    S1EventKind.EXPIRED,
    S1EventKind.TRIGGER_OBSERVED,
}


class Playback(StrEnum):
    PAUSED = "PAUSED"
    PLAYING = "PLAYING"
    ENDED = "ENDED"


@dataclass(frozen=True, slots=True)
class SourceInfo:
    source_id: str
    origin: str  # SYNTHETIC | HISTORICAL (batch origins)
    raw_symbol: str
    batch_sha256s: tuple[str, ...]
    batch_paths: tuple[str, ...]
    config_hash: str
    config_version: int
    state_schema_version: int


@dataclass(frozen=True, slots=True)
class FeedItem:
    time_ms: int  # decision/availability time (virtual UTC)
    ref: str  # candidate / signal id or FEED
    state: str
    text: str
    pre_roll: bool


@dataclass(frozen=True, slots=True)
class WarmUp:
    h1_bars: int
    h1_required: int
    m15_bars: int
    m15_required: int
    m5_atr: IndicatorStatus | None

    @property
    def sufficient(self) -> bool:
        return (
            self.h1_bars >= self.h1_required
            and self.m15_bars >= self.m15_required
            and self.m5_atr is IndicatorStatus.VALID
        )


@dataclass(frozen=True, slots=True)
class ProvisionalBar:
    timeframe: Timeframe
    start_ms: int
    open_bid: Decimal
    last_bid: Decimal


@dataclass(frozen=True, slots=True)
class SignalView:
    record: SignalRecord
    status: SignalStatus
    pre_roll: bool


@dataclass(frozen=True, slots=True)
class Snapshot:
    source: SourceInfo
    playback: Playback
    pace: int | None
    processed: int
    total: int
    pre_roll_quotes: int
    window_start_ms: int | None
    quote: NormalizedQuote | None
    health: FeedHealth | None
    context: AnalysisContext | None
    warmup: WarmUp
    forming: tuple[S1Candidate, ...]
    trigger_thresholds: dict[str, Decimal | None]  # candidate_id -> next-bar trigger level
    signals: tuple[SignalView, ...]
    feed: tuple[FeedItem, ...]
    last_bars: dict[Timeframe, FinalizedBar | None]
    provisional: dict[Timeframe, ProvisionalBar | None]
    bar_counts: dict[Timeframe, int]
    gaps: tuple[GapRecord, ...]
    triggers_observed: int

    @property
    def virtual_time_ms(self) -> int | None:
        return None if self.quote is None else self.quote.received_time_ms

    @property
    def ready(self) -> tuple[SignalView, ...]:
        return tuple(s for s in self.signals if s.status.state is SignalState.READY)


def _warmup(ctx: AnalysisContext, counts: dict[Timeframe, int], params) -> WarmUp:
    atr = next(
        (v for v in ctx.atr_values if v.timeframe is Timeframe.M5 and v.name.startswith("ATR")),
        None,
    )
    return WarmUp(
        h1_bars=counts[Timeframe.H1],
        h1_required=params.h1_warmup_bars,
        m15_bars=counts[Timeframe.M15],
        m15_required=params.m15_warmup_bars,
        m5_atr=None if atr is None else atr.status,
    )


class ReplaySession:
    """Owns one pipeline over one source's ordered quotes."""

    def __init__(
        self,
        quotes: Sequence[NormalizedQuote],
        source: SourceInfo,
        policy: SignalPolicy,
        from_ms: int | None = None,
    ) -> None:
        self.quotes = quotes
        self.source = source
        self.pipeline = S1ResearchPipeline(source.source_id, policy)
        self.from_ms = from_ms
        self.cursor = 0
        self.playback = Playback.PAUSED
        self.pace_index = 0
        self.health: FeedHealth | None = None
        self.feed: deque[FeedItem] = deque(maxlen=FEED_LIMIT)
        self._last_feed_status: FeedStatus | None = None
        self._credit = 0.0
        self.pre_roll_quotes = 0
        self.window_start_ms: int | None = None
        self._pre_rolling = True
        self._m5_seen = 0
        # Read-only listeners told about every processed quote (e.g. manual-position touch
        # monitoring, docs/07 §7.2). They cannot change engine state or event order.
        self.quote_observers: list[Callable[[NormalizedQuote], None]] = []
        self._pre_roll()
        self._pre_rolling = False

    # ----------------------------------------------------------------- processing

    def _process_one(self) -> None:
        q = self.quotes[self.cursor]
        step = self.pipeline.on_quote(q)
        self.cursor += 1
        self.health = step.health
        pre = self._pre_rolling
        if step.health.status is not self._last_feed_status:
            self._last_feed_status = step.health.status
            self.feed.append(
                FeedItem(
                    q.received_time_ms,
                    "FEED",
                    step.health.status.value,
                    ", ".join(step.health.reasons) or "feed health changed",
                    pre,
                )
            )
        for e in step.s1_events:
            if e.kind in _STRIP_S1:
                text = ", ".join(r.value for r in e.reason_codes) or e.kind.value
                state = e.new_state.value if e.new_state else e.kind.value
                if e.kind is S1EventKind.TRIGGER_OBSERVED:
                    state = "TRIGGER"
                self.feed.append(
                    FeedItem(e.decision_time_ms, e.candidate_id or "-", state, text, pre)
                )
        for e in step.signal_events:
            text = ", ".join(r.value for r in e.reason_codes) or e.kind.value
            self.feed.append(
                FeedItem(e.decision_time_ms, e.signal_id or e.candidate_id, e.kind.value, text, pre)
            )
        for observer in self.quote_observers:
            observer(q)
        if self.cursor >= len(self.quotes):
            self.playback = Playback.ENDED

    def _pre_roll(self) -> None:
        """Causal warm-up before the visible window (docs/02 §9A).

        With ``from_ms``: every quote before it is history. Without: process until the
        first moment the MTF warm-up is satisfied (checked only when a bar finalizes, the
        only time it can change); the next quote is the first post-warm-up quote.
        If the source never satisfies warm-up, it ends as INSUFFICIENT HISTORY.
        """
        engine = self.pipeline.detector.engine
        while self.cursor < len(self.quotes):
            q = self.quotes[self.cursor]
            if self.from_ms is not None:
                if q.provider_time_ms >= self.from_ms:
                    break
                self._process_one()
                continue
            self._process_one()
            if self._bars_changed() and self._counts_sufficient():
                if self.warmup_state(engine.context(q.received_time_ms)).sufficient:
                    break
        self.pre_roll_quotes = self.cursor
        if self.cursor < len(self.quotes):
            self.window_start_ms = self.quotes[self.cursor].provider_time_ms
            self.playback = Playback.PAUSED
        else:
            self.playback = Playback.ENDED

    def _bars_changed(self) -> bool:
        n = self.pipeline.aggregator.history.count(Timeframe.M5)
        changed = n != self._m5_seen
        self._m5_seen = n
        return changed

    def _counts_sufficient(self) -> bool:
        hist = self.pipeline.aggregator.history
        p = self.pipeline.detector.engine.params
        return hist.count(Timeframe.H1) >= p.h1_warmup_bars and (
            hist.count(Timeframe.M15) >= p.m15_warmup_bars
        )

    def warmup_state(self, ctx: AnalysisContext) -> WarmUp:
        hist = self.pipeline.aggregator.history
        counts = {tf: len(hist.available(tf, ctx.decision_time_ms)) for tf in Timeframe}
        return _warmup(ctx, counts, self.pipeline.detector.engine.params)

    # ----------------------------------------------------------------- controls

    @property
    def pace(self) -> int | None:
        return PACES[self.pace_index]

    def toggle_play(self) -> Playback:
        if self.playback is Playback.PAUSED:
            self.playback = Playback.PLAYING
            self._credit = 0.0
        elif self.playback is Playback.PLAYING:
            self.playback = Playback.PAUSED
        return self.playback

    def step(self) -> bool:
        """Process exactly one quote event; only while PAUSED."""
        if self.playback is not Playback.PAUSED or self.cursor >= len(self.quotes):
            return False
        self._process_one()
        return True

    def faster(self) -> int | None:
        self.pace_index = min(self.pace_index + 1, len(PACES) - 1)
        return self.pace

    def slower(self) -> int | None:
        self.pace_index = max(self.pace_index - 1, 0)
        return self.pace

    def advance(self, elapsed_s: float) -> int:
        """Process the quotes due after ``elapsed_s`` wall seconds of PLAYING. Returns count.

        Only the *number* of events per slice depends on pacing; their order, timestamps and
        results never do (UI-22, no UI refresh changes expiry).
        """
        if self.playback is not Playback.PLAYING:
            return 0
        if self.pace is None:
            budget = FAST_SLICE_EVENTS
        else:
            self._credit += self.pace * elapsed_s
            budget = int(self._credit)
            self._credit -= budget
        done = 0
        while done < budget and self.cursor < len(self.quotes):
            self._process_one()
            done += 1
        return done

    # ----------------------------------------------------------------- snapshot

    def snapshot(self) -> Snapshot:
        pipe = self.pipeline
        agg, det, eng = pipe.aggregator, pipe.detector, pipe.signals
        q = agg.last_quote
        ctx = det.engine.context(q.received_time_ms) if q is not None else None
        hist = agg.history
        now = q.received_time_ms if q is not None else 0
        counts = {tf: len(hist.available(tf, now)) for tf in Timeframe}
        params = det.engine.params
        if ctx is not None:
            warm = _warmup(ctx, counts, params)
        else:
            warm = WarmUp(0, params.h1_warmup_bars, 0, params.m15_warmup_bars, None)
        # UI-R1 (docs/14 §7): a triggered candidate whose signal was issued is shown once, in
        # its signal lane - not again as FORMING (the detector state itself is unchanged).
        signalled = {rec.candidate_id for rec in eng.signals.values()}
        forming = tuple(
            c
            for c in det.active.values()
            if c is not None
            and c.state is CandidateState.FORMING
            and not (c.trigger is not None and c.candidate_id in signalled)
        )
        thresholds = {c.candidate_id: self._next_trigger_level(c) for c in forming}
        signals = tuple(
            SignalView(rec, eng.status[sid], self._is_pre_roll(rec.first_ready_ms))
            for sid, rec in eng.signals.items()
        )
        provisional: dict[Timeframe, ProvisionalBar | None] = {}
        for tf in Timeframe:
            b = agg._building.get(tf)  # noqa: SLF001 - read-only view of the open bar
            provisional[tf] = (
                None if b is None else ProvisionalBar(tf, b.start_ms, b.open_bid, b.close_bid)
            )
        health = self.health
        if q is None:
            health = assess_feed(None, (), hist, 0, pipe.policy.health)
        return Snapshot(
            source=self.source,
            playback=self.playback,
            pace=self.pace,
            processed=self.cursor,
            total=len(self.quotes),
            pre_roll_quotes=self.pre_roll_quotes,
            window_start_ms=self.window_start_ms,
            quote=q,
            health=health,
            context=ctx,
            warmup=warm,
            forming=forming,
            trigger_thresholds=thresholds,
            signals=signals,
            feed=tuple(self.feed),
            last_bars={tf: hist.last_closed(tf, now) for tf in Timeframe},
            provisional=provisional,
            bar_counts=counts,
            gaps=tuple(agg.gaps),
            triggers_observed=sum(1 for e in det.events if e.kind is S1EventKind.TRIGGER_OBSERVED),
        )

    def _is_pre_roll(self, t_ms: int) -> bool:
        return self.window_start_ms is None or t_ms < self.window_start_ms

    def _next_trigger_level(self, cand: S1Candidate) -> Decimal | None:
        """The level the next closed M5 BID must beat (docs/05 §6 two-bar rule)."""
        bars = self.pipeline.detector.m5
        n = self.pipeline.detector.params.trigger_lookback_bars
        if len(bars) < n:
            return None
        prev = bars[-n:]
        if cand.side.value == "BUY":
            return max(b.high_bid for b in prev)
        return min(b.low_bid for b in prev)


__all__ = [
    "FEED_LIMIT",
    "PACES",
    "FeedItem",
    "Playback",
    "ReplaySession",
    "SignalEventKind",
    "Snapshot",
    "SourceInfo",
]
