"""R0 premium terminal layout (docs/02 §2.1) at 120x34, 80x24 and 70x18.

Shell order, tabs, context key bar, panel titles, table fit, modal anatomy (identity ->
plan/position -> fields -> risk preview & warnings -> actions, Cancel focused) and that
typing never triggers hotkeys. Fixture thresholds are test-only (tests/ui_support.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import Button, ContentSwitcher, Input

from grog.domain.enums import SignalEventKind
from grog.ui.app import GrogApp
from grog.ui.forms import JournalForm, PositionDetail
from grog.ui.screens import Overlay
from ui_support import open_journal, record_unlinked, run, session, step_until

SIZES = [(120, 34), (80, 24), (70, 18)]
VIEWS = ("live", "signals", "positions", "journal", "diagnostics")
TAB = {"live": "LIVE", "signals": "SIG", "positions": "POS", "journal": "J", "diagnostics": "DIAG"}


def ready_app(tmp_path: Path, restart: bool = False) -> tuple[GrogApp, object]:
    s = session()
    step_until(s, SignalEventKind.READY_ISSUED)
    store, journal = open_journal(tmp_path)
    if restart:
        record_unlinked(journal)
        journal.restore_on_startup()
    return GrogApp(s, journal, autoplay_timer=False), store


def _tab_on(app: GrogApp) -> str:
    """Text of the filled (active) tab."""
    tabs = app.query_one("#tabs")
    for seg, style in tabs._key[0]:
        if style == "tab_on":
            return seg
    raise AssertionError("no active tab")


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_shell_order_tabs_and_key_bar(tmp_path: Path, size) -> None:
    async def scenario() -> None:
        app, store = ready_app(tmp_path)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            header, tabs, views, keys = (
                app.query_one(x).region for x in ("#header", "#tabs", "#views", "#keys")
            )
            assert header.bottom <= tabs.y < views.y and views.bottom <= keys.y
            assert keys.bottom == size[1]  # key bar always on the last row
            for n, view in enumerate(VIEWS, start=1):
                await pilot.press(str(n))
                assert app.query_one("#views", ContentSwitcher).current == view
                assert TAB[view] in _tab_on(app).replace("JRNL", "J").replace("JOURNAL", "J")
                bar = app.query_one("#keys").plain
                assert bar.endswith("[No orders]") and "1-5" in bar
                assert len(bar) <= size[0] - 2, bar  # one row, nothing clipped
            await pilot.press("2")
            assert "e reco" in app.query_one("#keys").plain
            await pilot.press("3")
            bar = app.query_one("#keys").plain
            assert all(f"{k} " in bar for k in ("p", "m", "x", "n")) and "x close" in bar
            tabs = app.query_one("#tabs").plain
            assert len(tabs) <= size[0] - 2, tabs
            header_text = app.query_one("#header").plain
            assert "REPLAY • SYNTHETIC" in header_text and "SIMULATED" in header_text
            assert "[FRESH]" in header_text
            for line in header_text.splitlines():  # each header row fits, nothing wraps
                assert len(line) <= size[0] - 2, line
        store.close()

    run(scenario)


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_panels_titled_and_positions_table_fits(tmp_path: Path, size) -> None:
    async def scenario() -> None:
        app, store = ready_app(tmp_path, restart=True)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert app.query_one("#context").border_title == "MARKET CONTEXT"
            assert app.query_one("#forming-box").border_title == "OPPORTUNITIES FORMING"
            assert "ACTIONABLE PROPOSALS" in app.query_one("#proposals").border_title
            assert "RECONCILIATION REQUIRED" in app.query_one("#tabs").plain
            await pilot.press("3")
            await pilot.pause()
            table = app.query_one("#positions-table")
            assert table.virtual_size.width <= table.size.width  # no hidden STATE column
            assert table.get_row_at(0)[-1] == "RECONCILIATION REQUIRED"
            assert "ACTIVE MANUAL POSITIONS" in app.query_one("#positions-box").border_title
        store.close()

    run(scenario)


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_entry_modal_anatomy_cancel_default_and_typing_safe(tmp_path: Path, size) -> None:
    async def scenario() -> None:
        app, store = ready_app(tmp_path)
        async with app.run_test(size=size) as pilot:
            await pilot.press("2", "e")
            form = app.screen
            assert isinstance(form, JournalForm)
            assert form.query_one("#form-box").border_title.startswith("RECORD ENTRY")
            order = [
                form.query_one(x).virtual_region.y
                for x in ("#form-identity", "#sec-plan", "#sec-fields", "#sec-preview")
            ]
            buttons = form.query_one(".form-buttons").virtual_region.y
            assert order == sorted(order) and order[-1] < buttons
            assert form.query_one("#sec-preview").border_title == "RISK PREVIEW & WARNINGS"
            assert isinstance(app.focused, Button) and app.focused.id == "cancel"
            assert form.query_one("#form-box").scroll_y == 0  # opens at identity, not bottom
            price = form.query_one("#f-note", Input)
            price.focus()
            await pilot.press(*"esxpmnq12345", "space", "full_stop", "question_mark")
            assert app.screen is form and price.value == "esxpmnq12345 .?"
            assert app.query_one("#views", ContentSwitcher).current == "signals"
            assert "nothing is sent to a broker" in form.query_one("#form-hint").plain
        store.close()

    run(scenario)


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_reconciliation_detail_back_is_default(tmp_path: Path, size) -> None:
    async def scenario() -> None:
        app, store = ready_app(tmp_path, restart=True)
        async with app.run_test(size=size) as pilot:
            await pilot.press("3", "enter")
            detail = app.screen
            assert isinstance(detail, PositionDetail)
            assert "RECONCILIATION REQUIRED" in detail.query_one("#detail-box").border_title
            assert detail.query_one("#sec-reconcile").border_title == "RECONCILIATION"
            assert app.focused.id == "back"
            assert detail.query_one("#confirm-open", Button)
            await pilot.press("escape")
            assert not isinstance(app.screen, PositionDetail)
        store.close()

    run(scenario)


def test_overlay_title_is_border_title() -> None:
    async def scenario() -> None:
        s = session()
        step_until(s, SignalEventKind.READY_ISSUED)
        app = GrogApp(s, autoplay_timer=False)
        async with app.run_test(size=(120, 34)) as pilot:
            await pilot.press("2", "enter")
            ov = app.screen
            assert isinstance(ov, Overlay)
            assert ov.query_one("#detail-box").border_title.startswith("SIGNAL ")
            assert ov.plain.startswith("SIGNAL ") and "[Esc] Back" in ov.plain

    run(scenario)
