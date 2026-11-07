"""U2-A Overview structure and safety: Qt renders engine/journal facts only."""

from __future__ import annotations

import os
from dataclasses import replace

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from test_desktop_d03 import (  # noqa: E402
    at_ready,
    decisions,
    events,
    finish,
    make_state,
    open_d03,
    wait_until,
)

from grog.desktop.frames import OverviewFrame  # noqa: E402
from grog.replay.session import Playback  # noqa: E402
from ui_support import open_journal, record_unlinked, session  # noqa: E402


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication(["gold-u2-overview-test"])


def test_ready_overview_keeps_full_ids_and_review_is_navigation_only(app, tmp_path) -> None:
    replay, sid = at_ready()
    window = open_d03(app, replay, make_state(tmp_path))
    try:
        assert window.frame.ready_ids == (sid,)
        assert window.signal_ids.isVisibleTo(window)
        assert f"READY signal ID  {sid}" in window.signal_ids.text()
        assert window.review_signals.isVisibleTo(window)
        assert window.evidence_toggle.isVisibleTo(window)
        assert not window.diag.isVisibleTo(window)
        assert "Config v" in window.diag_text.text()
        window.evidence_toggle.click()
        app.processEvents()
        assert window.diag.isVisibleTo(window)
        window.evidence_toggle.click()
        app.processEvents()
        assert not window.diag.isVisibleTo(window)
        assert not window.positions_detail.isVisibleTo(window)
        window.positions_expand.click()
        app.processEvents()
        assert window.positions_detail.isVisibleTo(window)

        before = (replay.cursor, window.frame.transport.processed)
        window.review_signals.click()
        assert window.page_index == 1
        assert (replay.cursor, window.frame.transport.processed) == before
        assert events(tmp_path) == [] and decisions(tmp_path) == []
    finally:
        finish(app, window)


def test_reconciliation_attention_is_before_decision_and_not_broker_synced(app, tmp_path):
    replay, _sid = at_ready()
    request = make_state(tmp_path)
    store, journal = open_journal(tmp_path)
    try:
        record_unlinked(journal)
    finally:
        store.close()
    window = open_d03(app, replay, request)
    try:
        assert window.record_alert.isVisibleTo(window)
        assert "require reconciliation" in window.record_alert_text.text()
        assert "No broker orders are sent" in window.record_alert_text.text()
        page = window.scroll.widget()
        alert_y = window.record_alert.mapTo(page, QPoint(0, 0)).y()
        decision_y = window.decision.mapTo(page, QPoint(0, 0)).y()
        assert alert_y < decision_y
    finally:
        finish(app, window)


def test_only_fresh_active_engine_conditions_are_shown(app, tmp_path) -> None:
    replay = session()
    while not (replay.snapshot().forming and replay.snapshot().health.status.value == "FRESH"):
        assert replay.step()
    window = open_d03(app, replay, make_state(tmp_path))
    try:
        frame = window.frame
        assert isinstance(frame, OverviewFrame)
        assert frame.forming > 0 and frame.overview.watchlist
        assert window.pending_condition.isVisibleTo(window)
        assert "NOT TRADABLE" in window.pending_title.text() or frame.forming > 1
        if frame.forming == 1:
            assert window.pending_text.text() == frame.overview.watchlist[0]

        ended = replace(frame, transport=replace(frame.transport, playback=Playback.ENDED))
        window._apply_overview(ended)
        assert not window.pending_condition.isVisibleTo(window)
        degraded = replace(
            frame,
            diagnostics=replace(frame.diagnostics, health="DEGRADED"),
        )
        window._apply_overview(degraded)
        assert not window.pending_condition.isVisibleTo(window)
    finally:
        finish(app, window)


def test_overview_does_not_hide_unreadable_local_journal(app) -> None:
    from grog.desktop.loading import LoadRequest
    from grog.desktop.replay_worker import ReplayWorker
    from grog.desktop.window import GoldWindow

    window = GoldWindow(
        LoadRequest("syn"),
        worker=ReplayWorker(
            loader=lambda _request: session(),
            journal_reader=lambda _r: (None, None, "Journal not connected"),
        ),
    )
    window.show()
    try:
        wait_until(app, lambda: isinstance(window.frame, OverviewFrame), "first frame")
        assert window.record_alert.isVisibleTo(window)
        assert "UNVERIFIED" in window.record_alert_text.text()
        assert "not broker-synced" in window.record_alert_text.text()
    finally:
        window.close()
        wait_until(app, lambda: not window._threads_running(), "owner threads stopped")
        app.processEvents()

# U2-C: position counters must reflect local records, never inferred broker state.


def test_u2_positions_summary_and_unverified_mode_are_truthful(app, tmp_path) -> None:
    from grog.desktop.journal_model import JournalMode, JournalSnapshot
    from grog.desktop.records_pages import PositionsPage
    from grog.journal.positions import PositionState

    store, journal = open_journal(tmp_path)
    try:
        open_position = record_unlinked(journal)
    finally:
        store.close()

    recon = replace(
        open_position,
        position_id="recon-fixture",
        state=PositionState.RECONCILIATION_REQUIRED,
    )
    closed = replace(
        open_position,
        position_id="closed-fixture",
        state=PositionState.CLOSED,
    )
    snapshot = JournalSnapshot(
        generation=1,
        sequence=1,
        source_id="syn",
        mode=JournalMode.WRITABLE,
        reason="U2 isolated fixture",
        positions=(open_position, recon, closed),
        events=(),
        decisions=(),
        claims=(),
    )
    page = PositionsPage()
    page.show()
    app.processEvents()
    try:
        assert page.open_metric.value.text() == "—"
        assert page.reconcile_metric.value.text() == "—"
        page.apply_snapshot(snapshot)
        assert page.open_metric.value.text() == "2"
        assert page.reconcile_metric.value.text() == "1"
        assert page.closed_metric.value.text() == "1"
        assert "recon-fixture" in page.worklist.text()
        assert "at your broker" in page.worklist.text()
        assert not page.off_plan_button.isEnabled()

        page.filter.setCurrentText("All")
        page.table.selectRow(1)
        app.processEvents()
        assert page.selected_key == "recon-fixture"
        assert "RECONCILIATION REQUIRED" in page.detail_summary.text()
        assert "not broker-synced" in page.detail_summary.text()
        assert "No automatic broker order" in page.detail_text()

        page.set_layout_mode("narrow")
        from PySide6.QtWidgets import QBoxLayout

        assert page.summary_row.direction() == QBoxLayout.Direction.TopToBottom
        page.apply_snapshot(
            replace(snapshot, mode=JournalMode.UNAVAILABLE, reason="read failed", positions=())
        )
        assert page.open_metric.value.text() == "—"
        assert page.reconcile_metric.value.text() == "—"
        assert page.closed_metric.value.text() == "—"
        assert "status UNKNOWN" in page.worklist.text()
        assert "read failed" in page.mode_text.text()
    finally:
        page.close()


def test_u2_journal_human_clocks_provenance_and_invalid_ranges(app, tmp_path) -> None:
    from grog.desktop.presentation import utc_ms_text, view_time_text

    replay, _sid = at_ready()
    window = open_d03(app, replay, make_state(tmp_path))
    try:
        window.show_page(3)
        page = window.journal_page
        assert page.shown  # a READY replay includes reconstructed engine events
        first = page.shown[0]
        assert page.model.headerData(0, Qt.Orientation.Horizontal) == "WHEN (PKT)"
        assert page.model.item(0, 0).text() == view_time_text(first.time_ms, "PKT")
        assert page.model.item(0, 0).toolTip() == (
            f"Original event UTC: {utc_ms_text(first.time_ms)}"
        )
        assert "reconstructed SIM ENGINE observation" in page.chronology.text()
        page.table.selectRow(0)
        app.processEvents()
        assert "SIM ENGINE" in page.detail_source.text()
        assert "RECORDED UTC" in page.detail_text_label.text()
        assert "Engine event ID:" in page.detail_text_label.text()

        keys = [entry.key for entry in page.shown]
        page.set_time_zone("UTC")
        assert page.model.headerData(0, Qt.Orientation.Horizontal) == "WHEN (UTC)"
        assert page.model.item(0, 0).text() == view_time_text(first.time_ms, "UTC")
        assert [entry.key for entry in page.shown] == keys  # display-only zone change
        assert page.selected_key == first.key

        page.from_utc.setText("not a UTC timestamp")
        assert page.model.rowCount() == 0
        assert page.range_error.text()
        assert "Correct the UTC time range" in page.chronology.text()
        page.from_utc.clear()
        assert [entry.key for entry in page.shown] == keys
        from PySide6.QtWidgets import QBoxLayout

        page.set_layout_mode("narrow")
        assert page.filter_row.direction() == QBoxLayout.Direction.TopToBottom
        assert page.range_row.direction() == QBoxLayout.Direction.TopToBottom
        page.set_layout_mode("medium")
        assert page.filter_row.direction() == QBoxLayout.Direction.LeftToRight
    finally:
        finish(app, window)


def test_u2_diagnostics_health_first_with_full_disclosed_evidence(app, tmp_path):
    replay, _sid = at_ready()
    window = open_d03(app, replay, make_state(tmp_path))
    try:
        window.show_page(4)
        page = window.diagnostics_page
        assert page.facts is not None
        assert "reference adapter is not connected" in page.health_note.text()
        assert not page.evidence_host.isVisibleTo(window)
        page.evidence_toggle.click()
        app.processEvents()
        assert page.evidence_host.isVisibleTo(window)
        assert "Config sha256:" in page.text()
        assert "REFERENCE ADAPTER" in page.text()
        page.evidence_toggle.click()
        app.processEvents()
        assert not page.evidence_host.isVisibleTo(window)
        page.mark_stale("simulated source fault", "2026-10-14 00:00:00 UTC")
        assert "stale" in page.health_note.text().lower()
        assert "simulated source fault" in page.text()
        page.apply(None)
        assert page.summary.text() == "Waiting for source diagnostics…"
        assert "no problems found" not in page.text()
    finally:
        finish(app, window)
