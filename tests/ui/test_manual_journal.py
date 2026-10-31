"""M08 manual-journal UI (docs/02 §3, §6, §7, §9; docs/08 UI-15..18, UI-20, UI-21).

Forms are driven headless through Textual Pilot over a deterministic SYNTHETIC replay and a
tmp_path journal. Fixture fills use declared test values; nothing reaches any broker.
"""

from __future__ import annotations

import argparse
import sqlite3
from decimal import Decimal
from pathlib import Path

from textual.widgets import Button, Input

from grog.cli import EXIT_OK, main, open_ui_journal
from grog.domain.enums import SignalEventKind, SignalState
from grog.journal.positions import PlanStatus, PositionState
from grog.journal.store import STATE_DB_FILENAME
from grog.replay import synthetic
from grog.strategies.s1_pullback import record_to_dict
from grog.ui.app import GrogApp
from grog.ui.forms import JournalForm, PositionDetail
from grog.ui.screens import Overlay
from ui_support import open_journal, record_unlinked, run, session, step_until

WIDE, NORMAL = (120, 34), (80, 24)


async def fill(pilot, form: JournalForm, **values: str) -> None:
    for key, value in values.items():
        form.query_one(f"#f-{key}", Input).value = value
    await pilot.pause()


def ready_session():
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED)
    return s, sid


# ---------------------------------------------------------------- UI-15 record entry


def test_ui15_record_entry_modal_mandatory_fields_cancel_default_preview(tmp_path: Path) -> None:
    async def scenario() -> None:
        s, sid = ready_session()
        rec = s.pipeline.signals.signals[sid]
        original = record_to_dict(rec)
        store, journal = open_journal(tmp_path)
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.press("2", "e")
            form = app.screen
            assert isinstance(form, JournalForm) and form.id == "record-entry"
            assert isinstance(app.focused, Button) and app.focused.id == "cancel"
            body = form.plain
            assert sid in body and "SIMULATED (REPLAY)" in body and "(read-only)" in body
            assert "Grog sends no order" in body
            assert form.values()["time"].endswith("Z")  # default: form-opening virtual time
            # Mandatory actual fill price and size.
            form.confirm()
            await pilot.pause()
            assert "NOT SAVED" in form.error_plain and "fill price is required" in form.error_plain
            await fill(pilot, form, price=str(rec.e0))
            form.confirm()
            await pilot.pause()
            assert "quantity is required" in form.error_plain
            await fill(pilot, form, qty="-1")
            assert "Preview unavailable" in form.preview_plain
            await fill(pilot, form, qty="0.20")
            prev = form.preview_plain
            assert "Original E0" in prev and "Plan status: ON_PLAN" in prev
            assert "target +2.0000R gross" in prev and "P&L UNKNOWN" in prev
            assert "Fees: UNKNOWN" in prev
            assert journal.positions() == []  # nothing saved before confirmation
            # Typing hotkeys into a field never triggers parent actions (docs/02 §3).
            note = form.query_one("#f-note", Input)
            note.focus()
            await pilot.press("e", "s", "x", "n", "q", "1", "space")
            assert app.screen is form and note.value == "esxnq1 "
            await pilot.click("#confirm")
            await pilot.pause()
            assert isinstance(app.screen, Overlay) and "Saved locally" in app.screen.plain
            assert "No broker order" in app.screen.plain
        (pos,) = journal.positions()
        assert pos.plan_status is PlanStatus.ON_PLAN and pos.linked_signal_id == sid
        assert pos.entry_price == rec.e0 and pos.remaining_qty == Decimal("0.20")
        assert pos.fees_text == "UNKNOWN"
        assert s.pipeline.signals.signals[sid] is rec and record_to_dict(rec) == original
        store.close()

    run(scenario)


def test_late_entry_preview_shows_off_plan_and_changed_r(tmp_path: Path) -> None:
    async def scenario() -> None:
        s, sid = ready_session()
        rec = s.pipeline.signals.signals[sid]
        store, journal = open_journal(tmp_path)
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.press("2", "e")
            form = app.screen
            worse = rec.e0 + rec.original_risk_price / 2 * (1 if rec.side.value == "BUY" else -1)
            await fill(pilot, form, price=str(worse), qty="0.1")
            prev = form.preview_plain
            assert "OFF_PLAN / REVALIDATE (OUTSIDE_ENTRY_BAND)" in prev
            assert "actual risk" in prev
            form.confirm()
            await pilot.pause()
        (pos,) = journal.positions()
        assert pos.plan_status is PlanStatus.OFF_PLAN
        assert pos.initial_risk == rec.original_risk_price * Decimal("1.5")
        assert pos.plan.e0 == rec.e0 and pos.plan.tp2 == rec.tp2  # original plan unchanged
        store.close()

    run(scenario)


def test_duplicate_keypress_and_db_lock_never_double_record(tmp_path: Path) -> None:
    async def scenario() -> None:
        s, sid = ready_session()
        rec = s.pipeline.signals.signals[sid]
        store, journal = open_journal(tmp_path, busy_timeout_ms=50)
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.press("2", "e")
            form = app.screen
            await fill(pilot, form, price=str(rec.e0), qty="0.1")
            other = sqlite3.connect(store.path, isolation_level=None)
            other.execute("BEGIN IMMEDIATE")  # another writer holds the DB lock
            form.confirm()
            await pilot.pause()
            assert app.screen is form and "NOT SAVED" in form.error_plain
            assert "Position record NOT saved" in form.error_plain
            other.execute("ROLLBACK")
            other.close()
            assert journal.positions() == []  # rolled back, no false success
            form.confirm()  # retry with the same action ID
            form.confirm()  # duplicate keypress
            await pilot.pause()
            assert form.saved and form.submissions == 2
        assert len(journal.positions()) == 1 and len(journal.events()) == 1
        store.close()

    run(scenario)


def test_escape_with_unsubmitted_input_needs_confirmation(tmp_path: Path) -> None:
    async def scenario() -> None:
        s, _ = ready_session()
        store, journal = open_journal(tmp_path)
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.press("2", "e")
            form = app.screen
            await pilot.press("escape")  # pristine form closes immediately
            assert not isinstance(app.screen, JournalForm)
            await pilot.press("e")
            form = app.screen
            await fill(pilot, form, price="4000")
            form.query_one("#cancel", Button).focus()
            await pilot.press("escape")
            assert app.screen is form and "press Esc again" in form.error_plain
            await pilot.press("escape")
            assert not isinstance(app.screen, JournalForm)
        assert journal.positions() == []
        store.close()

    run(scenario)


# ---------------------------------------------------------------- skip


def test_skip_records_user_skipped_and_blocks_entry(tmp_path: Path) -> None:
    async def scenario() -> None:
        s, sid = ready_session()
        store, journal = open_journal(tmp_path)
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.press("2", "s")
            form = app.screen
            assert form.id == "record-skip" and "USER_SKIPPED" in form.plain
            assert "original expiry" in form.plain and "[Mark skipped]" in form.plain
            await fill(pilot, form, reason="spread too wide for me")
            await pilot.click("#confirm")
            await pilot.pause()
            await pilot.press("escape")
            assert "USER_SKIPPED" in app.query_one("#ready").get_row(sid)[-1]
            await pilot.press("e")
            assert "already USER_SKIPPED" in app.screen.plain
        (d,) = journal.decisions()
        assert d.decision == "USER_SKIPPED" and d.reason == "spread too wide for me"
        assert s.snapshot().signals[0].status.state in (SignalState.READY, SignalState.EXPIRED)
        store.close()

    run(scenario)


# ---------------------------------------------------------------- UI-16 / UI-17 partial, close


def test_ui16_partial_exceeding_remaining_rejected_db_unchanged(tmp_path: Path) -> None:
    async def scenario() -> None:
        store, journal = open_journal(tmp_path)
        pos = record_unlinked(journal)
        s = session()
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.press("3", "p")
            form = app.screen
            assert form.id == "record-partial" and pos.position_id in form.plain
            await fill(pilot, form, price="4000", qty="0.11")
            assert "REJECTED: quantity exceeds remaining 0.1" in form.preview_plain
            before = (journal.positions(), journal.events())
            form.confirm()
            await pilot.pause()
            assert "NOT SAVED" in form.error_plain and "exceeds remaining" in form.error_plain
            assert (journal.positions(), journal.events()) == before
            await fill(pilot, form, qty="0.04")
            prev = form.preview_plain
            assert "Remaining after record: 0.06" in prev and "P&L UNKNOWN" in prev
            form.confirm()
            await pilot.pause()
        assert journal.get(pos.position_id).remaining_qty == Decimal("0.06")
        store.close()

    run(scenario)


def test_ui17_close_updates_only_journal(tmp_path: Path) -> None:
    async def scenario() -> None:
        store, journal = open_journal(tmp_path)
        pos = record_unlinked(journal)
        s = session()
        signals_before = record_to_dict(s.pipeline.signals.events)
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.press("3", "x")
            form = app.screen
            assert form.id == "record-close" and form.values()["qty"] == "0.1"  # prefilled
            await fill(pilot, form, price=str(pos.entry_price + 1), fees="0.70")
            await pilot.click("#confirm")
            await pilot.pause()
            assert (
                "CLOSED" in app.screen.plain and "Broker position not touched" in app.screen.plain
            )
            await pilot.press("escape")
            assert app.query_one("#positions-table").row_count == 0
            await pilot.press("4")
            journal_text = str(app.query_one("#journal-table").get_row_at(0))
            assert "CLOSE" in journal_text and "OPERATOR" in journal_text
        closed = journal.get(pos.position_id)
        assert closed.state is PositionState.CLOSED and closed.remaining_qty == 0
        assert closed.fees_text == "0.7 + UNKNOWN"  # entry fee was never stated
        assert record_to_dict(s.pipeline.signals.events) == signals_before
        store.close()

    run(scenario)


def test_modify_warns_when_stop_moves_further_away(tmp_path: Path) -> None:
    async def scenario() -> None:
        store, journal = open_journal(tmp_path)
        pos = record_unlinked(journal)
        app = GrogApp(session(), journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.press("3", "m")
            form = app.screen
            await fill(pilot, form, stop=str(pos.current_sl - 1))
            assert "FURTHER AWAY" in form.preview_plain
            assert "never rewritten" in form.preview_plain
            form.confirm()
            await pilot.pause()
        p = journal.get(pos.position_id)
        assert p.current_sl == pos.current_sl - 1 and p.initial_risk == pos.initial_risk
        store.close()

    run(scenario)


def test_position_keys_need_selected_position(tmp_path: Path) -> None:
    async def scenario() -> None:
        store, journal = open_journal(tmp_path)
        app = GrogApp(session(), journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            for key in ("p", "m", "x"):
                await pilot.press(key)
                assert "Select a recorded open position" in app.screen.plain
                await pilot.press("escape")
        store.close()

    run(scenario)


# ---------------------------------------------------------------- UI-18 restart / reconcile


def test_ui18_restart_shows_reconciliation_required_and_confirm(tmp_path: Path) -> None:
    async def scenario() -> None:
        store, journal = open_journal(tmp_path)
        pos = record_unlinked(journal)
        store.close()
        args = argparse.Namespace(state_dir=str(tmp_path / "state"))
        store, journal = open_ui_journal(args, {})  # what `grog ui` does at start
        app = GrogApp(session(), journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            assert "RECONCILIATION REQUIRED" in app.query_one("#positions-mini").plain
            await pilot.press("3")
            row = app.query_one("#positions-table").get_row(pos.position_id)
            assert row[-1] == "RECONCILIATION REQUIRED"
            strip = app.query_one("#positions-body").plain
            assert "MANUAL BROKER VERIFICATION NEEDED" in strip
            await pilot.press("enter")
            detail = app.screen
            assert isinstance(detail, PositionDetail) and "Verify at your broker" in detail.plain
            await pilot.click("#confirm-open")
            await pilot.pause()
            assert "MONITORING" in app.screen.plain
            await pilot.press("escape")
            row = app.query_one("#positions-table").get_row(pos.position_id)
            assert row[-1] == "MONITORING"
        store.close()

    run(scenario)


def test_cli_journal_open_never_touches_market_data(tmp_path: Path) -> None:
    csv = tmp_path / "syn.csv"
    csv.write_bytes(synthetic.generate_csv(days=2))
    state = tmp_path / "state"
    env = {"HOME": str(tmp_path / "home")}
    assert (
        main(
            ["import-ticks", "--file", str(csv), "--source-id", "syn", "--origin", "SYNTHETIC",
             "--state-dir", str(state)],
            env=env,
        )
        == EXIT_OK
    )  # fmt: skip
    market = {p: p.read_bytes() for p in (state / "market").rglob("*") if p.is_file()}

    def catalog() -> list:
        conn = sqlite3.connect(state / STATE_DB_FILENAME)
        try:
            return [
                list(conn.execute(f"SELECT * FROM {t} ORDER BY 1"))
                for t in ("quote_sources", "import_batches", "research_runs")
            ]
        finally:
            conn.close()

    before = catalog()
    store, journal = open_ui_journal(argparse.Namespace(state_dir=str(state)), env)
    assert journal.positions() == []
    store.close()
    assert catalog() == before
    assert {p: p.read_bytes() for p in (state / "market").rglob("*") if p.is_file()} == market


# ---------------------------------------------------------------- UI-21 unlinked entry


def test_ui21_unlinked_off_plan_entry_no_resurrection(tmp_path: Path) -> None:
    async def scenario() -> None:
        s = session()
        sid = step_until(s, SignalEventKind.EXPIRED)
        expired = s.pipeline.signals.signals[sid]
        store, journal = open_journal(tmp_path)
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.press("n")
            assert "Journal or Positions only" in app.screen.plain
            await pilot.press("escape", "4", "n")
            form = app.screen
            assert form.id == "record-unlinked"
            assert (
                "This records your external trade; Grog did not recommend or execute it."
                in form.plain
            )
            q = s.snapshot().quote
            await fill(pilot, form, side="sell", price=str(q.bid), qty="0.05", signal=sid)
            assert "Plan status: OFF_PLAN" in form.preview_plain
            assert "NO_READY_SIGNAL_LINK" in form.preview_plain
            await pilot.click("#confirm")
            await pilot.pause()
            assert "OFF_PLAN external trade" in app.screen.plain
        (pos,) = journal.positions()
        assert pos.plan_status is PlanStatus.OFF_PLAN and pos.signal_link == "INFORMATIONAL"
        assert pos.linked_signal_id == sid and pos.initial_risk is None
        assert s.pipeline.signals.status[sid].state is SignalState.EXPIRED  # not resurrected
        assert s.pipeline.signals.signals[sid] is expired
        assert journal.signal_status("syn", sid) is None
        store.close()

    run(scenario)


# ---------------------------------------------------------------- monitoring


def test_stop_touch_is_observation_not_fill(tmp_path: Path) -> None:
    async def scenario() -> None:
        s = session()
        q = s.snapshot().quote
        store, journal = open_journal(tmp_path)
        # Fixture stop just under the current BID so replay quotes soon touch it.
        pos = record_unlinked(
            journal,
            fill_ms=q.received_time_ms,
            price=q.ask,
            stop=q.bid - Decimal("0.05"),
        )
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.press("3")
            for _ in range(20_000):
                if app.tracker.touched(pos):
                    break
                s.step()
            assert "STOP" in app.tracker.touched(pos)
            app.action_refresh_panels()
            await pilot.pause()
            assert "STOP TOUCHED (NOT VERIFIED FILL)" in app.query_one("#positions-body").plain
            row = app.query_one("#positions-table").get_row(pos.position_id)
            assert row[5] != "—" and row[8] == "UNKNOWN"  # closeable mark shown, P&L UNKNOWN
        after = journal.get(pos.position_id)
        assert after.state is PositionState.MONITORING and after.remaining_qty == pos.remaining_qty
        assert len(journal.events(pos.position_id)) == 1  # a touch never writes an event
        store.close()

    run(scenario)


def test_compact_positions_layout_keeps_state(tmp_path: Path) -> None:
    async def scenario() -> None:
        store, journal = open_journal(tmp_path)
        pos = record_unlinked(journal)
        app = GrogApp(session(), journal, autoplay_timer=False)
        async with app.run_test(size=NORMAL) as pilot:
            await pilot.press("3")
            row = app.query_one("#positions-table").get_row(pos.position_id)
            assert len(row) == 6 and row[-1] == "MONITORING"
        store.close()

    run(scenario)
