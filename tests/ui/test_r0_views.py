"""R0 view content (docs/02 §7, §8): journal separates OPERATOR records from SIM ENGINE
events and inspects a full record; diagnostics group checks with explicit verdicts."""

from __future__ import annotations

from pathlib import Path

from grog.domain.enums import SignalEventKind
from grog.domain.models import DataHealthPolicy
from grog.signals.engine import SignalPolicy
from grog.ui import panels
from grog.ui.app import GrogApp
from grog.ui.screens import Overlay
from ui_support import open_journal, record_unlinked, run, session, step_until


def test_journal_recorded_by_detail_and_full_id_filter(tmp_path: Path) -> None:
    async def scenario() -> None:
        s = session()
        sid = step_until(s, SignalEventKind.READY_ISSUED)
        store, journal = open_journal(tmp_path)
        pos = record_unlinked(journal, fill_ms=s.snapshot().virtual_time_ms)
        app = GrogApp(s, journal, autoplay_timer=False)
        async with app.run_test(size=(120, 34)) as pilot:
            await pilot.press("4")
            table = app.query_one("#journal-table")
            rows = [table.get_row_at(i) for i in range(table.row_count)]
            assert {r[1] for r in rows} == {"OPERATOR", "SIM ENGINE"}
            assert all(r[2] != "SKIP" or r[1] == "OPERATOR" for r in rows)
            op = next(i for i, r in enumerate(rows) if r[1] == "OPERATOR")
            table.move_cursor(row=op)
            await pilot.press("enter")
            assert isinstance(app.screen, Overlay)
            detail = app.screen.plain
            assert "JOURNAL RECORD — OPERATOR" in detail and pos.position_id in detail
            assert "Not a broker record" in detail
            await pilot.press("escape")
            app.query_one("#journal-filter").value = sid  # full ID, cells show a short one
            await pilot.pause()
            shown = [table.get_row_at(i) for i in range(table.row_count)]
            assert shown and all(r[1] == "SIM ENGINE" for r in shown)
        store.close()

    run(scenario)


def test_diagnostics_groups_and_verdicts() -> None:
    s = session(SignalPolicy(health=DataHealthPolicy()))
    for _ in range(300):
        s.step()
    text = panels.plain(panels.diagnostics_lines(s.snapshot()))
    for group in ("SOURCE", "FEED HEALTH", "BARS & GAPS", "WARM-UP & REPLAY", "INTEGRITY"):
        assert f"\n{group}\n" in text
    assert "[NOT CONFIGURED]" in text and "[UNKNOWN]" in text
    assert "Summary: " in text and "freshness thresholds NOT CONFIGURED" in text
    fresh = session()
    for _ in range(300):
        fresh.step()
    ftext = panels.plain(panels.diagnostics_lines(fresh.snapshot()))
    assert "[OK]" in ftext and "Freshness thresholds: declared in config" in ftext
