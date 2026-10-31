"""Shared helpers for Textual workstation tests (synthetic data, fixture-only thresholds)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from decimal import Decimal
from functools import cache
from pathlib import Path

from grog.domain.clock import FixedClock
from grog.domain.enums import Side, SignalEventKind
from grog.domain.models import DataHealthPolicy, NormalizedQuote
from grog.journal.positions import EntryRequest, ManualPosition, PositionJournal, new_action_id
from grog.journal.store import STATE_DB_FILENAME, Store
from grog.market_data.import_csv import parse_canonical_csv
from grog.replay import synthetic
from grog.replay.session import ReplaySession, SourceInfo
from grog.signals.engine import SignalPolicy

# Fixture-only declarations of OPEN thresholds (never broker values; docs/11 keeps them OPEN).
FIXTURE_POLICY = SignalPolicy(
    health=DataHealthPolicy(max_quote_age_ms=60_000, max_first_postclose_delay_ms=30_000),
    price_step=Decimal("0.01"),
)
INFO = SourceInfo(
    source_id="syn",
    origin="SYNTHETIC",
    raw_symbol="XAUUSD",
    batch_sha256s=("0" * 64,),
    batch_paths=("batches/syn.csv",),
    config_hash="f" * 64,
    config_version=1,
    state_schema_version=4,
)


@cache
def synthetic_quotes(days: int = 20) -> tuple[NormalizedQuote, ...]:
    data = synthetic.generate_csv(days=days)
    return parse_canonical_csv(data, source_id="syn", origin="SYNTHETIC").quotes


def session(policy: SignalPolicy = FIXTURE_POLICY, days: int = 20, **kw) -> ReplaySession:
    return ReplaySession(synthetic_quotes(days), INFO, policy, **kw)


def step_until(s: ReplaySession, kind: SignalEventKind, nth: int = 1) -> str:
    """Step (paused) until the n-th signal event of ``kind``; returns its signal id."""
    seen = 0
    events = s.pipeline.signals.events
    start = len(events)
    while s.step():
        for e in events[start:]:
            if e.kind is kind:
                seen += 1
                if seen == nth:
                    return e.signal_id or e.candidate_id
        start = len(events)
    raise AssertionError(f"{kind} #{nth} not reached")


def run(coro_factory: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(coro_factory())


JOURNAL_CLOCK = FixedClock(1_793_450_000_000)  # wall-clock "recorded at" for fixtures


def open_journal(tmp_path: Path, **kw) -> tuple[Store, PositionJournal]:
    store = Store.open(tmp_path / "state" / STATE_DB_FILENAME, JOURNAL_CLOCK, **kw)
    return store, PositionJournal(store)


def record_unlinked(journal: PositionJournal, fill_ms: int | None = None, **kw) -> ManualPosition:
    """A fixture OFF_PLAN external BUY on the synthetic source (declared test values)."""
    q = synthetic_quotes()[0]
    req = dict(
        action_id=new_action_id(),
        side=Side.BUY,
        price=q.ask,
        qty=Decimal("0.10"),
        fill_ms=q.received_time_ms if fill_ms is None else fill_ms,
        source_id="syn",
        stop=q.bid - Decimal("2.00"),
    )
    req.update(kw)
    return journal.record_entry(EntryRequest(**req))[0]
