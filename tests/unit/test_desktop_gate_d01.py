"""D01 gate clauses GUI-15, GUI-19, GUI-20, GUI-21 (docs/08 §20) against the real engine.

All values come from the replay engine, the CSV import validator or the read-only journal
service on disposable state; nothing here hard-codes widget output.
"""

from __future__ import annotations

import argparse
import dataclasses
import io
from decimal import Decimal
from pathlib import Path

import pytest

from desktop_gate_support import captured_views, composite
from grog.cli import build_ui_session
from grog.cli import main as grog
from grog.desktop.frames import (
    FrameTag,
    assert_detached,
    build_overview_frame,
)
from grog.desktop.loading import LoadRequest, load_session
from grog.desktop.presentation import UNAVAILABLE, UNKNOWN, price_text, utc_ms_text
from grog.domain.enums import Side, SignalEventKind, Timeframe
from grog.domain.ids import sha256_hex
from grog.journal.positions import EntryRequest, PlanRef, TouchTracker, new_action_id
from grog.market_data.import_csv import CsvImportError, parse_canonical_csv
from grog.replay import synthetic
from grog.replay.session import Playback, ReplaySession
from ui_support import FIXTURE_POLICY, INFO, open_journal, session, step_until

TAG = FrameTag("syn", 1, 1)
HEADER = "provider_time_utc_ms,received_time_utc_ms,bid,ask\n"


def _frame(owner, overlay=None):
    return build_overview_frame(
        owner,
        tag=TAG,
        overlay={} if overlay is None else overlay,
        positions=[],
        tracker=TouchTracker(),
        journal_note="test journal",
    )


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if dataclasses.is_dataclass(value):
        return [s for f in dataclasses.fields(value) for s in _strings(getattr(value, f.name))]
    if isinstance(value, tuple):
        return [s for item in value for s in _strings(item)]
    return []


# ------------------------------------------------------------------ GUI-19 Decimal scalars


def _tiny(rows: str) -> ReplaySession:
    quotes = parse_canonical_csv(
        (HEADER + rows).encode(), source_id="syn", origin="SYNTHETIC"
    ).quotes
    return ReplaySession(quotes, INFO, FIXTURE_POLICY)


def test_gui19_small_and_long_scale_quotes_keep_every_digit() -> None:
    small = _frame(_tiny("1790812800000,1790812800001,0.00001,0.00002\n")).quote
    assert (small.bid, small.ask, small.spread) == (
        Decimal("0.00001"),
        Decimal("0.00002"),
        Decimal("0.00001"),
    )
    assert (small.bid_text, small.ask_text, small.spread_text) == ("0.00001", "0.00002", "0.00001")
    long = _frame(_tiny("1790812800000,1790812800001,4119.123456789012,4119.123456789013\n")).quote
    assert long.bid_text == "4,119.123456789012" and long.ask_text == "4,119.123456789013"
    assert long.spread == Decimal("0.000000000001") and long.spread_text == "0.000000000001"
    trailing = _frame(_tiny("1790812800000,1790812800001,4119.9600,4120.2700\n")).quote
    assert trailing.bid_text == "4,119.9600" and trailing.spread_text == "0.3100"


@pytest.mark.parametrize("bad", ["-0.00", "0.00", "NaN", "Infinity", "-Infinity", "sNaN", "1e3"])
def test_gui19_invalid_prices_never_reach_the_desktop(bad: str) -> None:
    # The existing import validator is the authority; the GUI is never given these values.
    with pytest.raises(CsvImportError) as exc:
        parse_canonical_csv(
            (HEADER + f"1790812800000,1790812800001,{bad},4120.27\n").encode(),
            source_id="syn",
            origin="SYNTHETIC",
        )
    assert exc.value.field == "bid"


def test_gui19_display_formatter_is_lossless_and_marks_invalid_unknown() -> None:
    assert price_text(Decimal("-0.00")) == "-0.00"  # sign and scale preserved, not "0"
    assert price_text(Decimal("0.00001")) == "0.00001"
    assert price_text(Decimal("4119.9600")) == "4,119.9600"
    assert price_text(Decimal("1234567.123456789012345")) == "1,234,567.123456789012345"
    for value in ("NaN", "sNaN", "Infinity", "-Infinity"):
        assert price_text(Decimal(value)) == UNKNOWN
    assert price_text(None) == UNAVAILABLE
    with pytest.raises(TypeError):  # frames refuse binary floats anywhere
        assert_detached(4119.96)


def test_gui19_ready_levels_are_exact_engine_decimals_and_r_fees_not_fabricated() -> None:
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED)
    rec = s.pipeline.signals.signals[sid]
    frame = _frame(s)
    text = frame.overview.description
    for value in (rec.e0, rec.sl0, rec.tp1, rec.tp2):
        assert isinstance(value, Decimal)
        assert format(value, ",f") in text
    # The Overview has no R-multiple or fee field (they belong to signal detail/journal);
    # no Overview text claims one. The D02 Signals detail states fees/net R as UNKNOWN.
    overview_only = dataclasses.replace(frame, signals=None)
    lowered = " ".join(_strings(overview_only)).lower()
    assert "fee" not in lowered and "r-multiple" not in lowered and " 1r" not in lowered
    (row,) = frame.signals.current
    fees = [v for _k, v in row.detail.fields if "fee" in v.lower()]
    assert fees == ["UNKNOWN — net R/fees not confirmed"]


# ------------------------------------------------------------------ GUI-20 bar provenance


def test_gui20_confirmed_and_provisional_bars_at_each_boundary_without_lookahead() -> None:
    s = session()
    snap = s.snapshot()
    last = {tf: snap.last_bars[tf] for tf in (Timeframe.H1, Timeframe.M15, Timeframe.M5)}
    rolled: set[Timeframe] = set()
    while rolled != set(last) and s.step():
        snap = s.snapshot()
        for tf in last:
            bar = snap.last_bars[tf]
            if tf in rolled or bar == last[tf]:
                continue
            rolled.add(tf)
            now = snap.virtual_time_ms
            # Confirmed only once the first quote at/after the close was received.
            assert bar.end_ms <= bar.available_at_ms <= now
            assert bar.available_at_ms == snap.quote.received_time_ms
            prov = snap.provisional[tf]
            assert prov is None or prov.start_ms >= bar.end_ms  # open bar is the next one
            frame = _frame(s)
            bars = {row[0]: row[1:] for row in frame.diagnostics.bars}
            assert bars[tf.value] == (
                snap.bar_counts[tf],
                utc_ms_text(bar.end_ms),
                utc_ms_text(bar.available_at_ms),
            )
            labels = [p for p in frame.diagnostics.provisional if p.startswith(tf.value + " ")]
            if prov is not None:
                assert labels == [
                    f"{tf.value} open since {utc_ms_text(prov.start_ms)} · PROVISIONAL, "
                    "not used for signals"
                ]
    assert rolled == set(last)


def test_gui20_ready_trigger_is_a_confirmed_m5_bar_not_the_provisional_one() -> None:
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED)
    snap, rec = s.snapshot(), s.pipeline.signals.signals[sid]
    bar = snap.last_bars[Timeframe.M5]
    assert rec.trigger_id == "S1T-" + sha256_hex(f"{rec.candidate_id}|{bar.bar_id}".encode())[:20]
    assert bar.available_at_ms <= rec.first_ready_ms == snap.virtual_time_ms
    prov = snap.provisional[Timeframe.M5]
    assert prov is not None and prov.start_ms >= bar.end_ms
    frame = _frame(s)
    assert frame.ready_ids == (sid,)
    assert any(
        "M5 open since" in p and "not used for signals" in p for p in frame.diagnostics.provisional
    )


# ------------------------------------------------------------------ GUI-21 decision lane


@pytest.fixture(scope="module")
def engine_views():
    return captured_views()


def _overlay(tmp_path: Path, entered, skipped):
    store, journal = open_journal(tmp_path)
    try:
        r = entered.record
        journal.record_entry(
            EntryRequest(
                action_id=new_action_id(),
                side=r.side,
                price=r.original_ask if r.side is Side.BUY else r.original_bid,
                qty=Decimal("0.10"),
                fill_ms=r.first_ready_ms,
                source_id="syn",
                plan=PlanRef.from_record(r),
                signal_ready=True,
                stop=r.sl0,
            )
        )
        k = skipped.record
        journal.record_skip(new_action_id(), PlanRef.from_record(k), effective_ms=k.first_ready_ms)
        return journal.signal_actions("syn")
    finally:
        store.close()


def test_gui21_multiple_ready_blocked_entered_skipped_are_all_counted_unranked(
    tmp_path: Path, engine_views
) -> None:
    s, ready, blocked, live = engine_views
    ids = list(ready)
    a, b, entered, skipped, gone = (ready[i] for i in ids[:5])
    blocked_view = blocked[ids[5]]
    overlay = _overlay(tmp_path, entered, skipped)
    assert overlay[entered.record.signal_id][0] == "ENTERED"
    assert overlay[skipped.record.signal_id][0] == "USER_SKIPPED"
    views = (a, blocked_view, entered, b, skipped)
    frame = _frame(composite(s, views, snap=live), overlay)
    assert frame.labels.fidelity == "SIMULATED" and frame.transport.playback is Playback.PAUSED
    assert frame.ready_ids == (a.record.signal_id, b.record.signal_id)  # engine order
    assert frame.blocked_ids == (blocked_view.record.signal_id,)
    assert (frame.ready, frame.blocked) == (2, 1)
    assert frame.overview.headline == "2 simulated proposals ready"
    assert "No ranking or automatic selection" in frame.overview.description
    # D03 adds the SIM ENGINE event log (engine_rows) to the frame. This composite owner
    # drops `gone` from the snapshot while the real pipeline log still holds its genuine
    # issuance event, so the log is checked separately: every row must come from that
    # real log, and nothing outside the log may mention `gone`.
    shown = " ".join(_strings(dataclasses.replace(frame, engine_rows=())))
    for used in (entered, skipped, gone):  # acted-on or absent signals are never offered
        assert used.record.signal_id not in frame.ready_ids
    assert gone.record.signal_id not in shown  # no extra signal is invented
    logged = {e.event_id for e in s.pipeline.signals.events}
    assert frame.engine_rows and {r.key for r in frame.engine_rows} <= logged
    # Reversed engine order is mirrored, never re-sorted or ranked.
    flipped = _frame(composite(s, tuple(reversed(views)), snap=live), overlay)
    assert flipped.ready_ids == tuple(reversed(frame.ready_ids))


def test_gui21_replay_end_keeps_counts_and_ids_and_never_resumes(engine_views) -> None:
    s, ready, blocked, _live = engine_views
    end = s.snapshot()
    assert end.playback is Playback.ENDED and end.processed == end.total
    real = _frame(s)
    assert real.overview.headline == "Replay complete"
    assert f"REPLAY ENDED at {utc_ms_text(end.virtual_time_ms)}" in real.banner
    assert not real.transport.can_toggle and not real.transport.can_step
    assert real.ready_ids == () and real.ready == 0  # every real signal has expired
    ids = list(ready)
    views = (ready[ids[0]], blocked[ids[1]], ready[ids[2]])
    frame = _frame(composite(s, views, snap=end))
    assert frame.overview.headline == "Replay complete"
    assert frame.ready_ids == (ids[0], ids[2]) and frame.blocked_ids == (ids[1],)
    assert frame.labels.fidelity == "SIMULATED" and "live" not in frame.overview.source.lower()


# ------------------------------------------------------------------ GUI-15 desktop loader


@pytest.fixture(scope="module")
def imported(tmp_path_factory):
    root = tmp_path_factory.mktemp("gui15")
    csv = root / "syn.csv"
    csv.write_bytes(synthetic.generate_csv(days=20))
    short = root / "short.csv"
    short.write_bytes(synthetic.generate_csv(days=1))
    env = {"HOME": str(root / "home")}
    state = root / "state"
    for path, source in ((csv, "syn"), (short, "short")):
        argv = ["import-ticks", "--file", str(path), "--source-id", source]
        argv += ["--origin", "SYNTHETIC", "--state-dir", str(state)]
        assert grog(argv, env=env, stdout=io.StringIO(), stderr=io.StringIO()) == 0
    return state, env


@pytest.mark.parametrize(
    ("source", "from_ts"),
    [("syn", None), ("syn", "2026-10-10T00:00:00Z"), ("short", None)],
    ids=["warm-up-threshold", "from-window", "insufficient"],
)
def test_gui15_desktop_loader_is_the_r0_build_ui_session(imported, source, from_ts) -> None:
    state, env = imported
    request = LoadRequest(source, state_dir=str(state), from_ts=from_ts)
    desktop = load_session(request, env)
    r0 = build_ui_session(
        argparse.Namespace(source_id=source, config=None, state_dir=str(state), from_ts=from_ts),
        env,
    )
    a, b = desktop.snapshot(), r0.snapshot()
    assert desktop.playback is r0.playback and desktop.cursor == r0.cursor
    assert desktop.pre_roll_quotes == r0.pre_roll_quotes and a.window_start_ms == b.window_start_ms
    assert a.warmup == b.warmup and a.bar_counts == b.bar_counts and a.quote == b.quote
    frame = _frame(desktop)
    assert frame.transport.pre_roll == r0.pre_roll_quotes
    assert frame.diagnostics.warmup_sufficient == b.warmup.sufficient
    if source == "short":
        # R0: pre-roll consumes the whole short source without reaching sufficiency.
        assert not b.warmup.sufficient and desktop.playback is Playback.ENDED
        assert not frame.transport.can_toggle and frame.ready_ids == ()
        assert frame.overview.headline in (
            "No trade — insufficient history",
            "No trade — source status needs review",
        )
    elif from_ts is None:  # stopped exactly at the first sufficient quote
        assert (
            desktop.playback is Playback.PAUSED
            and b.warmup.sufficient
            and desktop.cursor == desktop.pre_roll_quotes
        )
    else:
        assert desktop.playback is Playback.PAUSED and all(v.pre_roll for v in a.signals)
        assert desktop.pre_roll_quotes > 0 and a.window_start_ms >= 1_791_590_400_000
    for bar in a.last_bars.values():  # no future bar in the paused start state
        assert bar is None or bar.available_at_ms <= a.virtual_time_ms


def test_gui20_overview_shows_exact_confirmed_bar_available_at_with_milliseconds() -> None:
    s = session()
    step_until(s, SignalEventKind.READY_ISSUED)
    snap = s.snapshot()
    frame = _frame(s)
    rows = {row[0]: row for row in frame.diagnostics.bars}
    for tf in (Timeframe.H1, Timeframe.M15, Timeframe.M5):
        bar = snap.last_bars[tf]
        assert rows[tf.value][3] == utc_ms_text(bar.available_at_ms)
    m5 = snap.last_bars[Timeframe.M5]
    assert m5.available_at_ms % 1000 != 0  # this fixture's bar became usable mid-second
    assert utc_ms_text(m5.available_at_ms).endswith(f".{m5.available_at_ms % 1000:03d} UTC")
    assert frame.quote.received_utc == utc_ms_text(snap.quote.received_time_ms)
    assert frame.quote.provider_utc == utc_ms_text(snap.quote.provider_time_ms)
    assert frame.overview.virtual_utc == utc_ms_text(snap.virtual_time_ms) + "  ·  virtual"
    assert all(
        " UTC  |  " in line and "." in line.split(" UTC")[0] for line in frame.overview.recent
    )
    rows = {row[0]: row for row in frame.diagnostics.bars}
    assert rows["M5"][2] == utc_ms_text(m5.end_ms)
