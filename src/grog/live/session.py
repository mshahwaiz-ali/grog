"""ReferenceSession: the read-only MT5 reference feed driving the unchanged pure engine.

docs/09 §5.1. ``poll()`` is meant to be called from a timer: it consumes new transport lines,
feeds accepted quotes to :class:`S1ResearchPipeline` in order, and evaluates link and feed
state at the injected clock's *now* — so a silent feed is detected without another tick.
A READY issued while processing a BACKFILL quote (catch-up, restart backlog, late lines,
restart warm-up history) is historical and never actionable. Prices never touch the journal.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from grog.adapters.mt5_reference.feed import (
    CursorPosition,
    FeedEvent,
    ReferenceReader,
    cursor_path_for,
)
from grog.domain.clock import Clock
from grog.domain.enums import FeedStatus, SignalEventKind, SignalState
from grog.domain.models import NormalizedQuote
from grog.market_data.health import FeedHealth, assess_feed
from grog.signals.engine import SignalPolicy
from grog.signals.pipeline import S1ResearchPipeline


class LinkStatus(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NO_DATA = "NO_DATA"
    DISCONNECTED = "DISCONNECTED"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"
    CATCHING_UP = "CATCHING_UP"
    MARKET_CLOSED = "MARKET_CLOSED"
    LIVE = "LIVE"


REFERENCE_LABEL = "REFERENCE · INDICATIVE"
FIXTURE_LABEL = "FIXTURE · SIMULATED"


@dataclass(frozen=True, slots=True)
class ReferenceStatus:
    link: LinkStatus
    reasons: tuple[str, ...]
    now_ms: int
    label: str  # REFERENCE · INDICATIVE | FIXTURE · SIMULATED | NOT CONFIGURED
    feed: FeedHealth | None
    last_quote: NormalizedQuote | None
    heartbeat_age_ms: int | None
    actionable: tuple[str, ...]  # READY signal IDs issued live and actionable now
    historical: tuple[str, ...]  # READY issued from BACKFILL/history: never actionable
    counters: dict[str, int]

    @property
    def broker_verified(self) -> bool:
        return False  # a reference feed is never broker-verified (docs/07 §12)


def not_configured(now_ms: int) -> ReferenceStatus:
    return ReferenceStatus(
        LinkStatus.NOT_CONFIGURED,
        ("NO_REFERENCE_CONFIG",),
        now_ms,
        "NOT CONFIGURED",
        None,
        None,
        None,
        (),
        (),
        {},
    )


class ReferenceSession:
    def __init__(
        self,
        exporter_dir: Path,
        source_id: str,
        policy: SignalPolicy,
        clock: Clock,
        max_heartbeat_age_ms: int | None,
        state_dir: Path | None = None,
        commit: bool = True,
    ) -> None:
        self.source_id = source_id
        self.policy = policy
        self.clock = clock
        self.max_heartbeat_age_ms = max_heartbeat_age_ms
        self.commit_cursor = commit and state_dir is not None
        cursor = cursor_path_for(state_dir, source_id) if state_dir is not None else None
        age = policy.health.max_quote_age_ms
        self.reader = ReferenceReader(Path(exporter_dir), source_id, clock, age, cursor)
        self.pipeline = S1ResearchPipeline(source_id, policy)
        self.live_ready: set[str] = set()
        self.historical_ready: set[str] = set()
        self.events: list[FeedEvent] = []  # bounded diagnostics tail
        self._warm_up(cursor if cursor is not None and cursor.exists() else None)

    # ------------------------------------------------------------------ ingestion

    def _warm_up(self, cursor: Path | None) -> None:
        """After a restart, rebuild engine state from retained files up to the cursor (history)."""
        if cursor is None:
            return
        stop = self.reader.position
        history = ReferenceReader(
            self.reader.directory, self.source_id, self.clock, self.policy.health.max_quote_age_ms
        )
        for ev in history.poll(stop_at=CursorPosition(stop.file, stop.offset, stop.next_seq)):
            if ev.kind == "QUOTE" and ev.quote is not None:
                self._feed(ev.quote, live=False)

    def _feed(self, quote: NormalizedQuote, live: bool) -> None:
        step = self.pipeline.on_quote(quote)
        for e in step.signal_events:
            if e.kind is SignalEventKind.READY_ISSUED and e.signal_id is not None:
                (self.live_ready if live else self.historical_ready).add(e.signal_id)

    def poll(self) -> ReferenceStatus:
        for ev in self.reader.poll():
            if ev.kind == "QUOTE" and ev.quote is not None:
                self._feed(ev.quote, ev.live)
            self.events.append(ev)
        del self.events[:-200]
        if self.commit_cursor:
            self.reader.commit()
        return self.status()

    # ------------------------------------------------------------------ evaluation

    def status(self) -> ReferenceStatus:
        st = self.reader.state
        last = self.pipeline.aggregator.last_quote
        now = self.clock.now_ms()
        hb = st.heartbeat
        hb_age = None if hb is None else max(0, now - hb.received_ms)
        link, reasons = self._link(now, hb_age)
        feed = None
        if last is not None:
            agg = self.pipeline.aggregator
            feed = assess_feed(
                last, agg.gaps, agg.history, max(now, last.received_time_ms), self.policy.health
            )
        actionable: tuple[str, ...] = ()
        if link is LinkStatus.LIVE and feed is not None and feed.status is FeedStatus.FRESH:
            eng = self.pipeline.signals
            actionable = tuple(
                sid
                for sid in sorted(self.live_ready - self.historical_ready)
                if eng.status[sid].state is SignalState.READY
                and not eng.status[sid].blocked
                and eng.signals[sid].expiry_ms > now
            )
        label = (
            "NOT CONFIGURED"
            if st.producer is None
            else ("FIXTURE · SIMULATED" if st.fixture else REFERENCE_LABEL)
        )
        return ReferenceStatus(
            link,
            reasons,
            now,
            label,
            feed,
            last,
            hb_age,
            actionable,
            tuple(sorted(self.historical_ready)),
            dict(st.counters),
        )

    def _link(self, now: int, hb_age: int | None) -> tuple[LinkStatus, tuple[str, ...]]:
        st = self.reader.state
        hb = st.heartbeat
        if st.records == 0:
            return LinkStatus.NO_DATA, ("NO_RECORDS",)
        if hb is not None and not hb.connected:
            return LinkStatus.DISCONNECTED, ("TERMINAL_REPORTS_DISCONNECTED",)
        if self.max_heartbeat_age_ms is None:
            return LinkStatus.UNKNOWN, ("HEARTBEAT_THRESHOLD_UNSET",)
        if hb is None:
            return LinkStatus.OFFLINE, ("NO_HEARTBEAT",)
        if hb_age is not None and hb_age > self.max_heartbeat_age_ms:
            return LinkStatus.OFFLINE, ("HEARTBEAT_AGE_EXCEEDS_POLICY",)
        if st.in_catchup:
            return LinkStatus.CATCHING_UP, ("CATCH_UP_IN_PROGRESS",)
        if hb.session == "CLOSED" or self.policy.health.closure_at(now) is not None:
            return LinkStatus.MARKET_CLOSED, ("MARKET_CLOSED",)
        if hb.session == "UNKNOWN":
            return LinkStatus.UNKNOWN, ("SESSION_UNKNOWN",)
        return LinkStatus.LIVE, ()


__all__ = [
    "FIXTURE_LABEL",
    "REFERENCE_LABEL",
    "LinkStatus",
    "ReferenceSession",
    "ReferenceStatus",
    "not_configured",
]
