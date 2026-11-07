"""D01 detached presentation frames (GUI-03/04/18/19/21); no Qt needed."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from grog.desktop.frames import (
    REPLAY_LABELS,
    FrameTag,
    assert_detached,
    build_overview_frame,
)
from grog.desktop.overview_model import from_snapshot
from grog.domain.enums import SignalEventKind
from grog.journal.positions import TouchTracker
from grog.market_data.import_csv import parse_canonical_csv
from grog.replay.session import ReplaySession
from ui_support import FIXTURE_POLICY, INFO, session, step_until

TAG = FrameTag("syn", 1, 1)


def _frame(s, overlay=None, positions=(), note="test journal"):
    return build_overview_frame(
        s,
        tag=TAG,
        overlay={} if overlay is None else overlay,
        positions=list(positions),
        tracker=TouchTracker(),
        journal_note=note,
    )


def test_frame_is_deeply_detached_and_immutable() -> None:
    s = session()
    frame = _frame(s)
    assert_detached(frame)
    with pytest.raises(dataclasses.FrozenInstanceError):
        frame.quote.bid = Decimal("1")  # type: ignore[misc]
    before = frame
    assert s.step()
    assert frame == before  # later engine work cannot alter an already-published frame


def test_detached_check_rejects_live_mutable_values() -> None:
    with pytest.raises(TypeError):
        assert_detached({"a": 1})
    with pytest.raises(TypeError):
        assert_detached((1, [2]))


def test_frame_overview_matches_engine_snapshot_and_textual_presenter() -> None:
    s = session()
    signal_id = step_until(s, SignalEventKind.READY_ISSUED)
    frame = _frame(s)
    snap = s.snapshot()
    assert frame.ready_ids == (signal_id,) and frame.blocked_ids == ()
    assert frame.overview == from_snapshot(snap, s.pipeline.signals.events, {}, open_positions=0)
    assert frame.quote.bid == snap.quote.bid and frame.quote.ask == snap.quote.ask
    assert frame.quote.received_ms == snap.quote.received_time_ms
    assert frame.quote.provider_ms == snap.quote.provider_time_ms
    assert frame.transport.processed == s.cursor
    assert frame.ready == 1 and "proposal ready in simulation" in frame.overview.headline
    assert frame.labels is REPLAY_LABELS and frame.labels.fidelity == "SIMULATED"


def test_unreadable_journal_never_presents_ready_as_unclaimed() -> None:
    s = session()
    step_until(s, SignalEventKind.READY_ISSUED)
    frame = build_overview_frame(
        s,
        tag=TAG,
        overlay=None,
        positions=None,
        tracker=TouchTracker(),
        journal_note="Journal unavailable (test)",
    )
    assert frame.overview.headline.startswith("Operator records unavailable")
    assert frame.overview.tone == "warning"
    assert not frame.positions.journal_ok and frame.positions.open_count is None
    assert (len(frame.ready_ids), len(frame.blocked_ids)) == (frame.ready, frame.blocked)


def _tiny(rows: str) -> ReplaySession:
    data = ("provider_time_utc_ms,received_time_utc_ms,bid,ask\n" + rows).encode()
    quotes = parse_canonical_csv(data, source_id="syn", origin="SYNTHETIC").quotes
    return ReplaySession(quotes, INFO, FIXTURE_POLICY)


def test_exact_decimal_scale_and_utc_milliseconds_are_preserved() -> None:
    s = _tiny("1790812800000,1790812800234,4119.9600,4120.27000\n")
    frame = _frame(s)
    assert frame.quote.bid == Decimal("4119.9600") and str(frame.quote.bid) == "4119.9600"
    assert frame.quote.bid_text == "4,119.9600"
    assert frame.quote.ask_text == "4,120.27000"
    assert frame.quote.spread == Decimal("4120.27000") - Decimal("4119.9600")
    assert frame.quote.received_ms == 1790812800234
    assert frame.quote.received_utc == "2026-10-01 00:00:00.234 UTC"  # exact ms


def test_same_millisecond_quotes_are_both_processed_in_source_order() -> None:
    s = _tiny(
        "1790812800000,1790812800234,4119.96,4120.27\n1790812800000,1790812800234,4119.97,4120.28\n"
    )
    frame = _frame(s)
    assert frame.transport.processed == frame.transport.total == 2
    assert frame.quote.bid == Decimal("4119.97")


def test_missing_quote_is_unknown_not_zero() -> None:
    frame = _frame(ReplaySession((), INFO, FIXTURE_POLICY))
    assert frame.quote.bid is None and frame.quote.ask is None and frame.quote.spread is None
    assert frame.quote.bid_text == frame.quote.ask_text == frame.quote.spread_text == "\u2014"
    assert frame.quote.received_utc == "\u2014"
    assert frame.overview.headline == "No market data"
    assert frame.diagnostics.health != "FRESH"
    assert frame.banner is not None and "DATA NOT LOADED" in frame.banner


def test_h1_m15_m5_causes_come_from_engine_context() -> None:
    s = session()
    while not s.snapshot().forming:
        assert s.step()
    snap = s.snapshot()
    causes = _frame(s).causes
    ctx = snap.context
    assert f"Bias {ctx.h1_bias.value}" in causes.h1
    assert all(code in causes.h1 for code in ctx.h1_bias_reasons)
    assert f"Buy side {ctx.m15_buy.context.value.lower()}" in causes.m15
    assert f"Sell side {ctx.m15_sell.context.value.lower()}" in causes.m15
    assert f"{len(snap.forming)} candidate(s) waiting" in causes.m5
    assert f"triggers observed this session {snap.triggers_observed}" in causes.m5


def test_causes_are_unknown_without_confirmed_context() -> None:
    causes = _frame(ReplaySession((), INFO, FIXTURE_POLICY)).causes
    assert causes.h1 == causes.m15 == causes.m5
    assert causes.h1.startswith("Not evaluated")
