"""R0 operator acceptance — error paths (docs/14 Phase D; docs/02 §9-§10; docs/07 §8).

Invalid prices/quantities, duplicate actions, late/off-plan entry, unverified data, failed
database writes, replay end, insufficient history and a 70x18 terminal. Fixture thresholds
are test-only declarations (tests/ui_support.py); nothing reaches any broker.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from textual.widgets import Button, Input

from grog.domain.enums import Side, SignalEventKind
from grog.domain.models import DataHealthPolicy
from grog.replay.session import Playback
from grog.signals.engine import SignalPolicy
from grog.strategies.s1_pullback import record_to_dict
from grog.ui import manual
from grog.ui.app import GrogApp
from grog.ui.forms import JournalForm
from grog.ui.screens import Overlay
from ui_support import open_journal, record_unlinked, run, session, step_until

WIDE, SMALL = (120, 34), (70, 18)


def ready(tmp_path: Path):
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED)
    store, journal = open_journal(tmp_path)
    return s, sid, store, journal


async def open_entry(pilot, app: GrogApp, sid: str) -> JournalForm:
    await pilot.press("2")
    table = app.query_one("#ready")
    table.move_cursor(row=table.get_row_index(sid))
    await pilot.press("e")
    assert isinstance(app.screen, JournalForm)
    return app.screen


async def submit(pilot, form: JournalForm, **values: str) -> None:
    for k, v in values.items():
        form.query_one(f"#f-{k}", Input).value = v
    await pilot.pause()
    form.query_one("#confirm", Button).focus()
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.parametrize(
    ("price", "qty", "message"),
    [
        ("", "0.10", "required"),
        ("abc", "0.10", ""),
        ("-1", "0.10", ""),
        ("NaN", "0.10", ""),
        ("4000", "0", ""),
        ("4000", "-0.1", ""),
        ("4000", "", "required"),
    ],
)
def test_invalid_price_or_quantity_is_not_saved(tmp_path: Path, price, qty, message) -> None:
    async def scenario() -> None:
        s, sid, store, journal = ready(tmp_path)
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            form = await open_entry(pilot, app, sid)
            await submit(pilot, form, price=price, qty=qty)
            assert app.screen is form and form.error_plain.startswith("NOT SAVED")
            assert message in form.error_plain
            assert journal.positions() == [] and journal.signal_actions("syn") == {}
        store.close()

    run(scenario)


def test_duplicate_confirm_and_second_action_on_same_signal(tmp_path: Path) -> None:
    async def scenario() -> None:
        s, sid, store, journal = ready(tmp_path)
        q = s.snapshot().quote
        rec = s.pipeline.signals.signals[sid]
        fill = q.ask if rec.side is Side.BUY else q.bid
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            form = await open_entry(pilot, app, sid)
            for k, v in {"price": str(fill), "qty": "0.10"}.items():
                form.query_one(f"#f-{k}", Input).value = v
            form.confirm()
            form.confirm()  # duplicate keypress / resubmission
            assert len(journal.positions()) == 1 and form.submissions == 1
            await pilot.press("escape")
            await pilot.press("e")
            assert isinstance(app.screen, Overlay) and "already ENTERED" in app.screen.plain
            await pilot.press("escape")
            await pilot.press("s")
            assert isinstance(app.screen, Overlay) and "already ENTERED" in app.screen.plain
        assert len(journal.positions()) == 1 and journal.decisions() == []
        store.close()

    run(scenario)


def test_late_out_of_band_entry_is_off_plan_and_plan_unchanged(tmp_path: Path) -> None:
    async def scenario() -> None:
        s, sid, store, journal = ready(tmp_path)
        rec = s.pipeline.signals.signals[sid]
        original = record_to_dict(rec)
        far = rec.entry_high + 5 if rec.side is Side.BUY else rec.entry_low - 5
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            form = await open_entry(pilot, app, sid)
            for k, v in {"price": str(far), "qty": "0.10"}.items():
                form.query_one(f"#f-{k}", Input).value = v
            await pilot.pause()
            assert "OFF_PLAN" in form.preview_plain and "OUTSIDE_ENTRY_BAND" in form.preview_plain
            await submit(pilot, form)
        (pos,) = journal.positions()
        assert pos.plan_status.value == "OFF_PLAN" and "OUTSIDE_ENTRY_BAND" in pos.off_plan_reasons
        assert record_to_dict(s.pipeline.signals.signals[sid]) == original
        store.close()

    run(scenario)


def test_unconfigured_thresholds_issue_no_ready_and_marks_are_unverified(tmp_path: Path) -> None:
    async def scenario() -> None:
        s = session(SignalPolicy(health=DataHealthPolicy()))
        for _ in range(3000):
            s.step()
        assert s.snapshot().signals == ()  # UNKNOWN feed health: never READY
        store, journal = open_journal(tmp_path)
        pos = record_unlinked(journal, fill_ms=s.snapshot().virtual_time_ms)
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.pause()
            assert "STALE_THRESHOLD_UNSET" in app.query_one("#banner").plain
            assert "[UNKNOWN]" in app.query_one("#header").plain
            await pilot.press("3")
            row = app.query_one("#positions-table").get_row(pos.position_id)
            assert (
                row[5].endswith("*") and "MARK UNVERIFIED" in app.query_one("#positions-body").plain
            )
        store.close()

    run(scenario)


def test_failed_database_write_shows_not_saved_then_retry_saves_once(tmp_path: Path) -> None:
    async def scenario() -> None:
        s, sid, store, journal = ready(tmp_path)
        q = s.snapshot().quote
        rec = s.pipeline.signals.signals[sid]
        fill = q.ask if rec.side is Side.BUY else q.bid
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            form = await open_entry(pilot, app, sid)
            journal._inject_failure = "after_event"  # test-only failure point
            await submit(pilot, form, price=str(fill), qty="0.10")
            assert app.screen is form and "NOT SAVED" in form.error_plain
            assert journal.positions() == [] and journal.events() == []
            journal._inject_failure = None
            await pilot.pause(0.3)  # Textual's button "active" debounce after a press
            await submit(pilot, form)  # same form, same action ID
            assert isinstance(app.screen, Overlay) and "Saved locally" in app.screen.plain
        assert len(journal.positions()) == 1 and len(journal.events()) == 1
        store.close()

    run(scenario)


def test_replay_end_keeps_snapshot_and_labels_marks(tmp_path: Path) -> None:
    async def scenario() -> None:
        s = session(days=3)
        store, journal = open_journal(tmp_path)
        pos = record_unlinked(journal)
        while s.step():
            pass
        assert s.playback is Playback.ENDED
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.pause()
            assert "REPLAY ENDED" in app.query_one("#header").plain
            m = manual.mark_for(pos, s.snapshot())
            assert m.freshness in ("REPLAY_ENDED", "STALE", "DEGRADED", "MARKET_CLOSED")
            assert not m.fresh
            before = s.snapshot().virtual_time_ms
            await pilot.press("full_stop", "space")
            assert s.snapshot().virtual_time_ms == before  # no new quote after the end
        store.close()

    run(scenario)


def test_insufficient_history_blocks_ready_with_banner() -> None:
    async def scenario() -> None:
        s = session(days=1)
        while s.step():
            pass
        snap = s.snapshot()
        assert not snap.warmup.sufficient and snap.signals == ()
        app = GrogApp(s, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            await pilot.pause()
            assert "INSUFFICIENT HISTORY" in app.query_one("#banner").plain
            await pilot.press("5")
            assert "[ERROR]" in app.query_one("#diag").plain

    run(scenario)


def test_entry_recorded_on_a_70x18_terminal(tmp_path: Path) -> None:
    async def scenario() -> None:
        s, sid, store, journal = ready(tmp_path)
        q = s.snapshot().quote
        rec = s.pipeline.signals.signals[sid]
        fill = q.ask if rec.side is Side.BUY else q.bid
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=SMALL) as pilot:
            assert app.query_one("#notice").display
            form = await open_entry(pilot, app, sid)
            await submit(pilot, form, price=str(fill), qty="0.10")
            assert isinstance(app.screen, Overlay) and "Saved locally" in app.screen.plain
        (pos,) = journal.positions()
        assert pos.entry_price == fill and pos.initial_qty == Decimal("0.10")
        store.close()

    run(scenario)
