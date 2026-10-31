"""R0 end-to-end operator acceptance (docs/14 Phase D; docs/02 §9; docs/07 §5-§8).

One deterministic SYNTHETIC journey through the real CLI entry points and the Textual app:
import -> REPLAY UI -> context/forming -> SIMULATED READY -> details -> record fill ->
economics -> monitoring -> partial -> modify -> close -> unlinked OFF_PLAN -> skip ->
restart -> RECONCILIATION_REQUIRED -> confirm -> exact persistence, no broker order.
Error paths follow. The feed thresholds come from config/synthetic-demo.fixture-only.toml:
DEMO/TEST-ONLY values (docs/11 keeps them OPEN). Quantities are fixture values, not advice.
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from textual.widgets import Button, Input

from grog.cli import EXIT_OK, build_ui_session, main, open_ui_journal
from grog.domain.enums import Side, SignalEventKind
from grog.journal.positions import PositionState
from grog.journal.store import STATE_DB_FILENAME
from grog.replay import synthetic
from grog.ui.app import GrogApp
from grog.ui.forms import JournalForm, PositionDetail
from grog.ui.screens import Overlay
from ui_support import run, step_until

REPO = Path(__file__).resolve().parents[2]
DEMO_CONFIG = REPO / "config" / "synthetic-demo.fixture-only.toml"
WIDE, SMALL = (120, 34), (70, 18)
QTY = "0.10"  # fixture quantity (not a lot recommendation)


# ---------------------------------------------------------------- helpers


@pytest.fixture(scope="module")
def imported(tmp_path_factory) -> tuple[Path, dict[str, str]]:
    root = tmp_path_factory.mktemp("r0")
    csv = root / "syn.csv"
    csv.write_bytes(synthetic.generate_csv(days=20))
    env = {"HOME": str(root / "home")}
    state = root / "state"
    code = main(
        ["import-ticks", "--file", str(csv), "--source-id", "syn", "--origin", "SYNTHETIC",
         "--state-dir", str(state)],
        env=env,
    )  # fmt: skip
    assert code == EXIT_OK
    return state, env


def args(state: Path, config: Path | None = DEMO_CONFIG) -> argparse.Namespace:
    return argparse.Namespace(
        source_id="syn",
        from_ts=None,
        config=None if config is None else str(config),
        state_dir=str(state),
    )


def market_hashes(state: Path) -> dict[str, str]:
    return {
        str(p.relative_to(state)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (state / "market").rglob("*")
        if p.is_file()
    }


async def fill_and_confirm(pilot, form: JournalForm, **values: str) -> None:
    for key, value in values.items():
        form.query_one(f"#f-{key}", Input).value = value
    await pilot.pause()
    form.query_one("#confirm", Button).focus()
    await pilot.press("enter")
    await pilot.pause()


async def dismiss_notice(pilot, app: GrogApp, expect: str) -> None:
    assert isinstance(app.screen, Overlay) and expect in app.screen.plain, app.screen
    assert "No broker order" in app.screen.plain
    await pilot.press("escape")


def select(app: GrogApp, table_id: str, key: str) -> None:
    table = app.query_one(table_id)
    table.focus()
    table.move_cursor(row=table.get_row_index(key))


def tables(state: Path) -> dict[str, list[tuple]]:
    conn = sqlite3.connect(state / STATE_DB_FILENAME)
    try:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return {n: list(conn.execute(f"SELECT * FROM {n}")) for n in names}
    finally:
        conn.close()


# ---------------------------------------------------------------- the journey


def test_r0_full_operator_journey(imported) -> None:
    state, env = imported
    market_before = market_hashes(state)

    async def first_run() -> tuple[str, str, str]:
        session = build_ui_session(args(state), env)  # 2. open REPLAY (paused, read-only)
        store, journal = open_ui_journal(args(state), env)
        app = GrogApp(session, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            # 3. market context and developing opportunities
            while not session.snapshot().forming:
                assert session.step()
            app.action_refresh_panels()
            assert "MARKET CONTEXT" in app.query_one("#context").plain
            assert app.query_one("#forming").row_count >= 1
            # 4. a SIMULATED READY signal
            sid = step_until(session, SignalEventKind.READY_ISSUED)
            app.action_refresh_panels()
            rec = session.pipeline.signals.signals[sid]
            proposals = app.query_one("#proposals").plain
            assert "READY" in proposals and "SIMULATED" in proposals
            # 5. inspect entry, SL, targets, expiry
            await pilot.press("2")
            select(app, "#ready", sid)
            await pilot.press("enter")
            detail = app.screen.plain
            for v in (rec.e0, rec.sl0, rec.tp1, rec.tp2):
                assert format(v, "f") in detail
            assert "Expires" in detail and "Issued: READY" in detail and "[e]" in detail
            await pilot.press("escape")
            # 6. record the external manual fill (on plan, at the executable side)
            q = session.snapshot().quote
            fill = q.ask if rec.side is Side.BUY else q.bid
            await pilot.press("e")
            form = app.screen
            assert isinstance(form, JournalForm) and app.focused.id == "cancel"
            await fill_and_confirm(pilot, form, price=str(fill), qty=QTY)
            await dismiss_notice(pilot, app, "Saved locally")
            # 7. actual fill economics
            (pos,) = journal.open_positions()
            assert pos.plan_status.value == "ON_PLAN" and pos.entry_price == fill
            assert pos.initial_risk == abs(rec.sl0 - fill) and pos.initial_qty == Decimal(QTY)
            assert "ENTERED" in app.query_one("#ready").get_row(sid)[-1]
            assert "already" in app.query_one("#proposals").plain  # not a fresh opportunity
            # 8. monitor quote movement; touches are observations only
            for _ in range(60):
                session.step()
            app.action_refresh_panels()
            await pilot.press("3")
            row = app.query_one("#positions-table").get_row(pos.position_id)
            q = session.snapshot().quote
            mark = q.bid if rec.side is Side.BUY else q.ask
            assert row[5].rstrip("*") == format(mark, "f")
            assert journal.get(pos.position_id).state is not PositionState.CLOSED
            exit_side = mark
            # 9. partial close
            select(app, "#positions-table", pos.position_id)
            await pilot.press("p")
            await fill_and_confirm(pilot, app.screen, price=str(exit_side), qty="0.04")
            await dismiss_notice(pilot, app, "Saved locally")
            assert journal.get(pos.position_id).remaining_qty == Decimal("0.06")
            # 10. stop modification (tighter, toward the fill)
            tighter = (
                rec.sl0 - Decimal("0.50") if rec.side is Side.SELL else rec.sl0 + Decimal("0.50")
            )
            select(app, "#positions-table", pos.position_id)
            await pilot.press("m")
            await fill_and_confirm(pilot, app.screen, stop=str(tighter), note="trail")
            await dismiss_notice(pilot, app, "Saved locally")
            assert journal.get(pos.position_id).current_sl == tighter
            assert journal.get(pos.position_id).initial_risk == pos.initial_risk  # frozen
            # 11. manual close (quantity prefilled with the remainder)
            select(app, "#positions-table", pos.position_id)
            await pilot.press("x")
            assert app.screen.query_one("#f-qty", Input).value == "0.06"
            await fill_and_confirm(pilot, app.screen, price=str(exit_side))
            await dismiss_notice(pilot, app, "Saved locally")
            closed = journal.get(pos.position_id)
            assert closed.state is PositionState.CLOSED and closed.remaining_qty == 0
            # 12. unlinked OFF_PLAN position (stays open for the restart)
            await pilot.press("n")
            form = app.screen
            assert "Grog did not recommend or execute it" in form.plain
            q = session.snapshot().quote
            await fill_and_confirm(
                pilot, form, side="BUY", price=str(q.ask), qty="0.05", stop=str(q.bid - 3)
            )
            await dismiss_notice(pilot, app, "Saved locally")
            (unlinked,) = journal.open_positions()
            assert unlinked.plan_status.value == "OFF_PLAN" and unlinked.linked_signal_id is None
            # 13. skip the next READY signal
            sid2 = step_until(session, SignalEventKind.READY_ISSUED)
            app.action_refresh_panels()
            await pilot.press("2")
            select(app, "#ready", sid2)
            await pilot.press("s")
            await fill_and_confirm(pilot, app.screen, reason="spread too wide for me")
            await dismiss_notice(pilot, app, "Saved locally")
            assert "USER_SKIPPED" in app.query_one("#ready").get_row(sid2)[-1]
            await pilot.press("e")  # a skipped signal cannot be entered on plan
            assert isinstance(app.screen, Overlay) and "already USER_SKIPPED" in app.screen.plain
            await pilot.press("escape")
        store.close()
        return pos.position_id, unlinked.position_id, sid2

    closed_id, open_id, skipped = asyncio_run(first_run)

    # 14-15. restart with an open position -> RECONCILIATION_REQUIRED, operator confirms
    async def second_run() -> None:
        session = build_ui_session(args(state), env)
        store, journal = open_ui_journal(args(state), env)
        (p,) = journal.open_positions()
        assert p.position_id == open_id and p.state is PositionState.RECONCILIATION_REQUIRED
        app = GrogApp(session, journal, autoplay_timer=False)
        async with app.run_test(size=WIDE) as pilot:
            assert "RECONCILIATION REQUIRED" in app.query_one("#tabs").plain
            await pilot.press("3")
            select(app, "#positions-table", open_id)
            await pilot.press("enter")
            detail = app.screen
            assert isinstance(detail, PositionDetail) and app.focused.id == "back"
            detail.query_one("#confirm-open", Button).focus()
            await pilot.press("enter")
            await pilot.pause()
            await dismiss_notice(pilot, app, "MONITORING")
            row = app.query_one("#positions-table").get_row(open_id)
            assert row[-1] == "MONITORING"
        store.close()

    asyncio_run(second_run)

    # 16. exact persistence, append-only history, no broker/order artefacts, market intact
    db = tables(state)
    actions = [(r[1], r[3]) for r in sorted(db["position_events"], key=lambda r: (r[1], r[2]))]
    assert [a for pid, a in actions if pid == closed_id] == [
        "ENTRY",
        "PARTIAL_CLOSE",
        "MODIFY",
        "CLOSE",
    ]
    assert [a for pid, a in actions if pid == open_id] == [
        "ENTRY",
        "RESTORED_UNVERIFIED",
        "CONFIRMED_OPEN",
    ]
    first_actions = {(r[2], r[4]) for r in db["signal_operator_actions"]}
    assert first_actions == {("ENTERED", closed_id), ("USER_SKIPPED", None)}
    assert [r[1] for r in db["signal_operator_actions"] if r[2] == "USER_SKIPPED"] == [skipped]
    (decision,) = db["signal_decisions"]
    assert skipped in decision and "USER_SKIPPED" in decision
    assert "spread too wide for me" in decision
    assert not [n for n in db if any(w in n.lower() for w in ("order", "broker", "wallet"))]
    assert market_hashes(state) == market_before


def asyncio_run(factory):
    out = []

    async def wrapper() -> None:
        out.append(await factory())

    run(wrapper)
    return out[0]
