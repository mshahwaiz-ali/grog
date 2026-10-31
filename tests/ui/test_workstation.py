"""Textual workstation (M07): docs/02 views/keys/states, docs/08 UI-01..14/19/20/22.

All screens render real engine snapshots from a deterministic SYNTHETIC replay; nothing is a
hard-coded demo signal. Tests run headless via ``App.run_test()`` / ``Pilot``.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from textual.widgets import ContentSwitcher, Input

from grog.analysis.contexts import context_to_dict
from grog.domain.enums import M15Context, SignalEventKind, SignalState, Timeframe
from grog.replay.session import Playback, ReplaySession
from grog.signals.engine import SignalPolicy
from grog.signals.pipeline import S1ResearchPipeline
from grog.strategies.s1_pullback import record_to_dict
from grog.ui import panels
from grog.ui.app import GrogApp
from grog.ui.screens import Overlay, QuitWarning
from ui_support import (
    FIXTURE_POLICY,
    INFO,
    open_journal,
    record_unlinked,
    run,
    session,
    step_until,
    synthetic_quotes,
)

WIDE, NORMAL, SMALL = (120, 34), (80, 24), (70, 18)


def text(app: GrogApp, selector: str) -> str:
    return app.query_one(selector).plain


def at_first_ready() -> tuple[ReplaySession, str]:
    s = session()
    return s, step_until(s, SignalEventKind.READY_ISSUED)


# ---------------------------------------------------------------- UI-22 pre-roll / controls


def test_ui22_starts_paused_after_causal_preroll_without_lookahead() -> None:
    s = session()
    quotes = synthetic_quotes()
    k = s.cursor
    assert s.playback is Playback.PAUSED and k == s.pre_roll_quotes > 0
    assert s.window_start_ms == quotes[k].provider_time_ms  # first post-warm-up quote
    snap = s.snapshot()
    assert snap.warmup.sufficient and snap.quote == quotes[k - 1]
    # No lookahead: identical to a fresh pipeline fed exactly the pre-roll quotes.
    fresh = S1ResearchPipeline("syn", FIXTURE_POLICY)
    for q in quotes[:k]:
        fresh.on_quote(q)
    t = quotes[k - 1].received_time_ms
    assert context_to_dict(fresh.detector.engine.context(t)) == context_to_dict(snap.context)
    # Minimal: one quote earlier the MTF warm-up was not yet satisfied.
    before = S1ResearchPipeline("syn", FIXTURE_POLICY)
    for q in quotes[: k - 1]:
        before.on_quote(q)
    ctx = before.detector.engine.context(quotes[k - 2].received_time_ms)
    assert not s.warmup_state(ctx).sufficient


def test_ui22_from_window_preroll_is_history_and_labeled() -> None:
    quotes = synthetic_quotes()
    start = quotes[80_000].provider_time_ms
    s = session(from_ms=start)
    assert s.cursor == 80_000 and s.playback is Playback.PAUSED
    snap = s.snapshot()
    assert all(v.pre_roll for v in snap.signals)  # pre-roll READY are history, not alerts
    assert all(item.pre_roll for item in snap.feed)
    assert "PRE-ROLL 80000 quotes (history)" in panels.plain(panels.header(snap))
    assert not any(not v.pre_roll for v in snap.ready)


def test_ui22_space_step_and_pacing_keys() -> None:
    async def scenario() -> None:
        app = GrogApp(session())
        async with app.run_test(size=WIDE) as pilot:
            s = app.session
            k = s.cursor
            await pilot.pause(0.3)
            assert s.cursor == k and "REPLAY PAUSED" in text(app, "#header")  # stays paused
            await pilot.press("full_stop")
            assert s.cursor == k + 1  # exactly one quote event
            await pilot.press("plus")
            assert s.pace == 500
            await pilot.press("plus")
            assert s.pace is None and "Pace FAST" in text(app, "#header")
            await pilot.press("minus", "minus")
            assert s.pace == 50 and "Pace 50 ev/s" in text(app, "#header")
            await pilot.press("space")
            assert s.playback is Playback.PLAYING
            await pilot.pause(0.5)
            await pilot.press("space")
            moved = s.cursor - (k + 1)
            assert s.playback is Playback.PAUSED and 5 <= moved <= 60  # ~50 ev/s
            at = s.cursor
            await pilot.press("full_stop")
            assert s.cursor == at + 1

    run(scenario)


def test_ui22_pacing_never_changes_events_or_expiry() -> None:
    n = 20_000
    one = session()
    for _ in range(n):
        one.step()
    fast = session()
    fast.toggle_play()
    fast.faster()
    fast.faster()
    while fast.cursor < one.cursor:
        fast.advance(0.05)  # FAST slices of 5000 events
    slow = session()
    slow.toggle_play()
    while slow.cursor < one.cursor:
        slow.advance(0.37)  # odd wall slices at 50 ev/s
    for other in (fast, slow):
        while one.cursor < other.cursor:
            one.step()  # align: compare at the same processed-quote count
        assert other.cursor == one.cursor
        a, b = one.pipeline.signals, other.pipeline.signals
        assert record_to_dict(a.events) == record_to_dict(b.events)
        assert {k: v.expiry_ms for k, v in a.signals.items()} == {
            k: v.expiry_ms for k, v in b.signals.items()
        }
        assert one.snapshot().feed == other.snapshot().feed


def test_ui_refresh_rate_never_changes_engine_results() -> None:
    async def scenario(redraw_every: int) -> list:
        s = session()
        app = GrogApp(s, autoplay_timer=False)
        async with app.run_test(size=NORMAL) as pilot:
            for i in range(6_000):
                s.step()
                if i % redraw_every == 0:
                    app.action_refresh_panels()
            await pilot.pause()
        return record_to_dict(s.pipeline.signals.events) + record_to_dict(
            list(s.pipeline.signals.signals.values())
        )

    import asyncio

    assert asyncio.run(scenario(7)) == asyncio.run(scenario(3_000))


def test_ui19_paused_and_ended_show_virtual_time_not_wall_clock() -> None:
    async def scenario() -> None:
        s = session()
        app = GrogApp(s, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            last = s.snapshot().virtual_time_ms
            assert panels.utc(last) in text(app, "#header") and "(virtual)" in text(app, "#header")
            s.toggle_play()
            s.faster()
            s.faster()
            while s.playback is Playback.PLAYING:
                s.advance(0.05)
            app.action_refresh_panels()
            await pilot.pause()
            quotes = synthetic_quotes()
            assert s.playback is Playback.ENDED and s.cursor == len(quotes)
            assert "REPLAY ENDED" in text(app, "#header")
            assert "REPLAY ENDED" in text(app, "#banner")
            assert panels.utc(quotes[-1].received_time_ms) in text(app, "#header")
            before = record_to_dict(s.pipeline.signals.events)
            await pilot.press("full_stop", "space", "full_stop")
            assert s.playback is Playback.ENDED  # no new quote or fresh signal
            assert record_to_dict(s.pipeline.signals.events) == before
            await pilot.press("4")  # review remains possible
            assert app.query_one("#views", ContentSwitcher).current == "journal"

    run(scenario)


# ---------------------------------------------------------------- UI-01..05 layout/navigation


def test_ui01_wide_screen_shows_all_lanes_and_five_views() -> None:
    async def scenario() -> None:
        s, _sid = at_first_ready()
        app = GrogApp(s, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            assert app.screen.has_class("-wide")
            header = text(app, "#header")
            for label in (
                "GROG / GOLD WORKSTATION",
                "XAUUSD",
                "REPLAY • SYNTHETIC",
                "SIMULATED",
                "Source: syn",
                "BID",
                "ASK",
                "Spread",
            ):
                assert label in header
            assert "MARKET CONTEXT" in text(app, "#context")
            assert "ACTIONABLE PROPOSALS (SIMULATED)" in text(app, "#proposals")
            assert "READY" in text(app, "#proposals")
            assert "No manually confirmed positions." in text(app, "#positions-mini")
            assert "EVENT FEED" in text(app, "#feed") and "READY_ISSUED" in text(app, "#feed")
            assert "[No orders]" in text(app, "#keys")
            context = app.query_one("#context").region
            forming = app.query_one("#forming-box").region
            assert context.y == forming.y and context.right <= forming.x  # side by side
            for key, view in zip(
                "12345", ("live", "signals", "positions", "journal", "diagnostics"), strict=True
            ):
                await pilot.press(key)
                assert app.query_one("#views", ContentSwitcher).current == view
            assert "SOURCE DIAGNOSTICS" in text(app, "#diag")
            assert "canonical=XAUUSD" in text(app, "#diag")

    run(scenario)


def test_ui02_normal_screen_stacks_and_detail_has_exact_sl_tp() -> None:
    async def scenario() -> None:
        s, sid = at_first_ready()
        rec = s.pipeline.signals.signals[sid]
        app = GrogApp(s, autoplay_timer=False)
        async with app.run_test(size=NORMAL) as pilot:
            assert app.screen.has_class("-normal") and app.compact
            context = app.query_one("#context").region
            forming = app.query_one("#forming-box").region
            assert forming.y >= context.bottom  # stacked, no overlap
            await pilot.press("2")
            table = app.query_one("#ready")
            assert len(table.columns) == len(panels.READY_COLUMNS_COMPACT)  # secondary hidden
            await pilot.press("enter")
            assert isinstance(app.screen, Overlay)
            detail = app.screen.plain
            for value in (rec.sl0, rec.tp1, rec.tp2, rec.e0):
                assert format(value, "f") in detail
            assert "SL ASK" in detail and "TP2 ASK" in detail and "First entry BID" in detail
            await pilot.press("escape")
            assert not isinstance(app.screen, Overlay)

    run(scenario)


def test_ui03_small_terminal_shows_guidance_and_keeps_critical_state() -> None:
    async def scenario() -> None:
        app = GrogApp(session(), autoplay_timer=False)
        async with app.run_test(size=SMALL) as pilot:
            await pilot.pause()
            assert app.screen.has_class("-narrow") and app.screen.has_class("-short")
            notice = app.query_one("#notice")
            assert notice.display and "enlarge" in notice.plain and "70x18" in notice.plain
            header = text(app, "#header")
            assert "REPLAY • SYNTHETIC" in header and "SIMULATED" in header
            assert "REPLAY PAUSED" in header
            await pilot.resize_terminal(*WIDE)
            await pilot.pause()
            assert not app.query_one("#notice").display

    run(scenario)


def test_ui04_navigation_keeps_selection_while_market_data_updates() -> None:
    async def scenario() -> None:
        s = session()
        step_until(s, SignalEventKind.READY_ISSUED, 2)
        app = GrogApp(s, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.press("4")
            table = app.query_one("#journal-table")
            assert app.focused is table and table.row_count >= 3
            await pilot.press("down", "down")
            chosen, rows = table.selected_key, table.row_count
            step_until(s, SignalEventKind.EXPIRED)  # new rows arrive above the selection
            app.action_refresh_panels()
            await pilot.pause()
            assert table.row_count > rows and table.selected_key == chosen
            await pilot.press("1", "4")
            assert app.query_one("#journal-table").selected_key == chosen
            await pilot.press("tab")
            assert app.focused is not None

    run(scenario)


def test_ui05_help_detail_escape_have_no_side_effects(tmp_path: Path) -> None:
    async def scenario() -> None:
        s = session()
        app = GrogApp(s, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            before = (s.cursor, record_to_dict(s.pipeline.signals.events))
            await pilot.press("question_mark")
            assert isinstance(app.screen, Overlay) and "GROG KEYS" in app.screen.plain
            await pilot.press("escape")
            assert app.query_one("#forming").row_count >= 1
            app.query_one("#forming").focus()
            await pilot.press("enter")
            assert isinstance(app.screen, Overlay) and "NOT TRADABLE YET" in app.screen.plain
            await pilot.press("escape")
            assert not isinstance(app.screen, Overlay)
            assert (s.cursor, record_to_dict(s.pipeline.signals.events)) == before

    run(scenario)
    assert [p.name for p in tmp_path.iterdir()] in ([], ["home"])  # nothing written


def test_ui06_typing_into_focused_input_never_triggers_hotkeys() -> None:
    async def scenario() -> None:
        s = session()
        app = GrogApp(s, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.press("4")
            box = app.query_one("#journal-filter", Input)
            box.focus()
            await pilot.press(
                "e",
                "s",
                "p",
                "m",
                "x",
                "n",
                "q",
                "1",
                "space",
                "full_stop",
                "plus",
                "question_mark",
            )
            assert box.value == "espmxnq1 .+?"
            assert not isinstance(app.screen, Overlay)
            assert app.query_one("#views", ContentSwitcher).current == "journal"
            assert s.playback is Playback.PAUSED and s.pace == 50
            assert app.is_running

    run(scenario)


def test_ui07_record_entry_on_forming_is_not_tradable() -> None:
    async def scenario() -> None:
        s = session()
        app = GrogApp(s, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            app.query_one("#forming").focus()
            await pilot.press("e")
            assert isinstance(app.screen, Overlay)
            assert "NOT TRADABLE YET" in app.screen.plain
            assert "no on-plan local entry" in app.screen.plain

    run(scenario)


def test_record_keys_without_writable_journal_record_nothing_and_never_order() -> None:
    async def scenario() -> None:
        s, _sid = at_first_ready()
        app = GrogApp(s, autoplay_timer=False)  # no journal: e.g. read-only embedding
        async with app.run_test(size=WIDE) as pilot:
            await pilot.press("2")
            before = record_to_dict(s.pipeline.signals.events)
            for key in ("e", "s", "x", "n"):
                await pilot.press(key)
                body = app.screen.plain
                assert "Local journal unavailable" in body and "nothing recorded" in body
                assert "No broker order is ever created." in body
                await pilot.press("escape")
            assert record_to_dict(s.pipeline.signals.events) == before

    run(scenario)


# ---------------------------------------------------------------- UI-08..14 signal states


def test_ui08_forming_shows_exact_pending_condition() -> None:
    s = session()
    snap = s.snapshot()
    assert snap.forming
    cand = snap.forming[0]
    rows = dict(panels.forming_rows(snap))
    _id, side, strategy, status, needs = rows[cand.candidate_id]
    level = snap.trigger_thresholds[cand.candidate_id]
    bars = s.pipeline.detector.m5[-2:]
    expect = max(b.high_bid for b in bars) if side == "BUY" else min(b.low_bid for b in bars)
    assert level == expect
    if status == "FORMING":
        assert needs == f"M5 close{'>' if side == 'BUY' else '<'}{level} " + (
            "bull" if side == "BUY" else "bear"
        )
    else:
        assert status == "WAIT" and needs.startswith("H1 ")
    # M15 CORRECTIVE is context only (S1-02): the pending condition is unchanged.
    ctx = snap.context
    corrective = dataclasses.replace(
        ctx,
        m15_buy=dataclasses.replace(ctx.m15_buy, context=M15Context.CORRECTIVE),
        m15_sell=dataclasses.replace(ctx.m15_sell, context=M15Context.CORRECTIVE),
    )
    assert dict(panels.forming_rows(dataclasses.replace(snap, context=corrective))) == rows
    assert "BUY CORRECTIVE" in panels.plain(
        panels.context_panel(dataclasses.replace(snap, context=corrective))
    )


def test_ui09_simulated_ready_sell_and_buy_sides() -> None:
    s = session()
    for nth in (1, 2):
        sid = step_until(s, SignalEventKind.READY_ISSUED, 1)
        rec = s.pipeline.signals.signals[sid]
        snap = s.snapshot()
        row = dict(panels.ready_rows(snap))[sid]
        ent, ex = ("ASK", "BID") if rec.side.value == "BUY" else ("BID", "ASK")
        assert row[3] == f"{ent} {rec.e0}" and row[5] == f"{ex} {rec.sl0}"
        assert row[6] == f"{ex} {rec.tp2}" and row[7] == "UNKNOWN"
        assert row[9] == "READY SIMULATED" and row[8] != panels.DASH
        assert rec.e0 == (s.snapshot().quote.ask if ent == "ASK" else s.snapshot().quote.bid)
        if nth == 1:
            assert rec.side.value == "SELL"
        else:
            assert rec.side.value == "BUY"


def test_ui11_unset_thresholds_or_short_history_never_invent_values() -> None:
    unset = session(policy=SignalPolicy())  # docs default: OPEN thresholds unset
    snap = unset.snapshot()
    assert "UNKNOWN" in panels.plain([panels.banner(snap)])
    assert "STALE_THRESHOLD_UNSET" in panels.plain([panels.banner(snap)])
    assert "FEED UNKNOWN" in panels.no_trade_reason(snap, unset.pipeline.signals.events)
    short = ReplaySession(synthetic_quotes(1)[:30], INFO, FIXTURE_POLICY)  # minutes only
    snap = short.snapshot()
    assert short.playback is Playback.ENDED and not snap.warmup.sufficient
    text_ = panels.plain(panels.context_panel(snap))
    assert "DATA UNKNOWN" in text_ and "INSUFFICIENT HISTORY" in text_
    assert "INSUFFICIENT HISTORY" in panels.plain([panels.banner(snap)])
    assert "NO TRADE" in panels.plain(panels.proposals_panel(snap, ()))
    assert not re.search(r"\d+(\.\d+)?\s*%", panels.plain(panels.diagnostics_lines(snap)))


def test_ui12_provisional_h1_is_labeled_and_never_used() -> None:
    s = session()
    for _ in range(600):
        s.step()
    snap = s.snapshot()
    assert snap.provisional[Timeframe.H1] is not None
    lines = panels.plain(panels.context_panel(snap))
    assert "[provisional, not used]" in lines
    h1_line = next(line for line in lines.splitlines() if line.startswith("H1  "))
    assert snap.context.h1_bias.value in h1_line and "[closed]" in h1_line
    last_h1 = snap.last_bars[Timeframe.H1]
    assert snap.context.last_confirmed_h1_id == last_h1.bar_id  # confirmed bar only


def test_ui13_blocked_and_restored_keeps_id_prices_and_ttl() -> None:
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED)
    original = dict(panels.ready_rows(s.snapshot()))[sid]
    rec = s.pipeline.signals.signals[sid]
    assert step_until(s, SignalEventKind.EXECUTION_BLOCKED) == sid
    blocked = dict(panels.ready_rows(s.snapshot()))[sid]
    assert blocked[9] == "EXECUTION BLOCKED SIMULATED"
    assert blocked[:8] == original[:8]
    assert step_until(s, SignalEventKind.EXECUTION_UNBLOCKED) == sid
    restored = dict(panels.ready_rows(s.snapshot()))[sid]
    assert restored[9] == "READY SIMULATED" and restored[:8] == original[:8]
    assert s.pipeline.signals.signals[sid] is rec  # the original record is never replaced


def test_ui14_expired_signal_is_terminal_and_never_resurrected() -> None:
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED)
    assert step_until(s, SignalEventKind.EXPIRED) == sid
    snap = s.snapshot()
    row = dict(panels.ready_rows(snap))[sid]
    assert row[9] == "EXPIRED SIMULATED" and row[8] == panels.DASH
    assert sid not in panels.plain(panels.proposals_panel(snap, s.pipeline.signals.events))
    for _ in range(3_000):
        s.step()
    assert s.pipeline.signals.status[sid].state is SignalState.EXPIRED
    assert sid not in {v.record.signal_id for v in s.snapshot().ready}


# ---------------------------------------------------------------- UI-20 quit / no broker


def test_ui20_quit_with_recorded_open_position_explains_broker_untouched(tmp_path: Path) -> None:
    async def scenario() -> None:
        store, journal = open_journal(tmp_path)
        record_unlinked(journal)
        app = GrogApp(session(), journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.press("q")
            assert isinstance(app.screen, QuitWarning)
            assert (
                "Positions remain open at broker; Grog will not close them. Reconcile on restart."
            ) in app.screen.plain
            await pilot.press("escape")
            assert app.is_running and not isinstance(app.screen, QuitWarning)
            await pilot.press("q", "q")
            await pilot.pause()
        assert app.return_code == 0
        assert len(journal.open_positions()) == 1  # persisted, never closed by quitting
        store.close()

    run(scenario)


def test_quit_without_positions_exits_directly() -> None:
    async def scenario() -> None:
        app = GrogApp(session(days=1), autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.press("q")
            await pilot.pause()
            assert not app.is_running

    run(scenario)


def test_ui_package_has_no_order_or_network_path() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "grog" / "ui"
    source = "\n".join(p.read_text() for p in root.glob("*.py"))
    for forbidden in (
        "OrderSend",
        "order_send",
        "import socket",
        "urllib",
        "http.client",
        "requests",
        "sqlite3",
        "subprocess",
    ):
        assert forbidden not in source
    assert "%" not in "".join(line for line in source.splitlines() if "confidence" in line.lower())
    keys = {b.key for b in GrogApp.BINDINGS}
    assert not {"b", "buy", "sell", "o"} & keys


def test_empty_state_data_not_loaded() -> None:
    async def scenario() -> None:
        app = GrogApp(ReplaySession((), INFO, FIXTURE_POLICY), autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.pause()
            assert "DATA NOT LOADED — import/replay data" in text(app, "#header")
            assert "DATA NOT LOADED" in text(app, "#banner")
            assert "No developing opportunities" in text(app, "#lanes")
            assert "NO TRADE — conditions not met" in text(app, "#proposals")
            await pilot.press("4")
            assert "No journal events yet" in text(app, "#journal-note")

    run(scenario)
