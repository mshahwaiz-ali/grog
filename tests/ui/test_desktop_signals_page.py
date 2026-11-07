"""D02 Signals page (GUI-27/28, focus safety, layout) with the real replay owner thread."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt, QThread  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QFormLayout, QLabel  # noqa: E402

from grog.desktop.frames import OverviewFrame  # noqa: E402
from grog.desktop.loading import LoadRequest, read_journal  # noqa: E402
from grog.desktop.replay_worker import ReplayWorker  # noqa: E402
from grog.desktop.signals_model import CURRENT_COLUMNS, Section  # noqa: E402
from grog.desktop.signals_page import CORE_COLUMNS, longest_token_width  # noqa: E402
from grog.desktop.window import GoldWindow  # noqa: E402
from grog.domain.enums import SignalEventKind  # noqa: E402
from grog.journal.positions import PlanRef, new_action_id  # noqa: E402
from grog.replay.session import Playback  # noqa: E402
from ui_support import open_journal, session, step_until  # noqa: E402

TIMEOUT_S = 30.0


@pytest.fixture(scope="module")
def app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication(["gold-desktop-test"])


def wait_until(app, predicate, what: str, timeout: float = TIMEOUT_S) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        app.processEvents()
        QThread.msleep(1)


def settle(app, n: int = 5) -> None:
    for _ in range(n):
        app.processEvents()


def no_journal(_request):
    return {}, [], "Read-only test journal (empty)"


def at_ready(nth: int = 1):
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED, nth)
    return s, sid


def open_window(app, loader, journal_reader=no_journal, request=None) -> GoldWindow:
    window = GoldWindow(
        request or LoadRequest("syn"),
        worker=ReplayWorker(loader=loader, journal_reader=journal_reader),
    )
    window.show()
    wait_until(app, lambda: isinstance(window.frame, OverviewFrame), "first frame")
    return window


def finish(app, window: GoldWindow) -> None:
    window.close()
    wait_until(app, window.thread.isFinished, "owner thread to finish")
    app.processEvents()


def keys_in(page, section: Section) -> list[str]:
    from grog.desktop.signals_page import KEY_ROLE

    proxy = page.proxies[section]
    return [proxy.index(r, 0).data(KEY_ROLE) for r in range(proxy.rowCount())]


def test_signals_page_renders_frame_rows_unranked_without_auto_selection(app) -> None:
    s, sid = at_ready()
    window = open_window(app, lambda _r: s)
    try:
        QTest.keyClick(window, Qt.Key.Key_2)
        settle(app)
        assert window.page_index == 1
        page, facts = window.signals_page, window.frame.signals
        assert page.facts is facts
        for section in Section:
            assert keys_in(page, section) == [r.key for r in facts.rows(section)]
        assert keys_in(page, Section.CURRENT) == [sid]
        assert page.tabs.tabText(1) == f"{Section.CURRENT.value} (1)"
        assert page.selected_key is None and "Select a row" in page.detail_text()
        assert all(not b.isEnabled() for b in page.action_buttons)
        QTest.keyClick(window, Qt.Key.Key_1)
        settle(app)
        assert window.page_index == 0
    finally:
        finish(app, window)


def test_typing_in_search_never_triggers_global_shortcuts(app) -> None:
    s, sid = at_ready()
    window = open_window(app, lambda _r: s)
    try:
        window.show_page(1)
        page = window.signals_page
        page.search.setFocus()
        settle(app)
        before = window.frame
        typed = "1 2 . + - = r q e s p m x n 3"
        QTest.keyClicks(page.search, typed)
        QTest.keyClick(page.search, Qt.Key.Key_Space)
        settle(app, 20)
        assert page.search.text() == typed + " "
        assert window.isVisible() and not window._closing  # q did not quit
        assert window.page_index == 1  # 1/2 did not switch pages
        assert window._refresh_after is None and not window.notice.isVisible()  # r inert
        now = window.frame
        assert now.transport.playback is Playback.PAUSED  # space did not play
        assert now.transport.processed == before.transport.processed == s.cursor  # no step
        assert now.transport.pace_text == before.transport.pace_text  # +/- inert
        # Positive control: the same keys work once focus leaves the text field.
        page.tables[Section.CURRENT].setFocus()
        QTest.keyClick(page.tables[Section.CURRENT], Qt.Key.Key_1)
        settle(app)
        assert window.page_index == 0
    finally:
        finish(app, window)


def test_search_and_filters_never_touch_market_state(app) -> None:
    s, sid = at_ready()
    window = open_window(app, lambda _r: s)
    try:
        window.show_page(1)
        page = window.signals_page
        page.select_key(sid)
        sequence, processed = window.frame.tag.sequence, s.cursor
        page.search.setText(sid[-8:])
        settle(app)
        assert keys_in(page, Section.CURRENT) == [sid]
        page.search.setText("no-such-signal")
        settle(app)
        assert keys_in(page, Section.CURRENT) == []
        assert page.tabs.tabText(1) == f"{Section.CURRENT.value} (0 of 1)"
        assert "hidden by the current search/filter" in page.detail_text()
        assert sid in page.detail_text()  # detail kept, never replaced
        page.search.clear()
        side = window.frame.signals.current[0].side
        page.side_filter.setCurrentText("BUY" if side == "SELL" else "SELL")
        settle(app)
        assert keys_in(page, Section.CURRENT) == []
        page.side_filter.setCurrentText("All sides")
        settle(app)
        assert keys_in(page, Section.CURRENT) == [sid]
        assert window.frame.tag.sequence == sequence and s.cursor == processed
    finally:
        finish(app, window)


def test_selected_ready_moving_to_history_keeps_id_detail_and_says_so(app) -> None:
    s, sid = at_ready()
    window = open_window(app, lambda _r: s)
    try:
        window.show_page(1)
        page = window.signals_page
        table = page.tables[Section.CURRENT]
        table.setFocus()
        table.selectRow(0)
        settle(app)
        assert page.selected_key == sid
        frozen = page.detail_text().split("Current BID")[0]
        page.tables[Section.HISTORY].sortByColumn(3, Qt.SortOrder.DescendingOrder)
        window.faster_requested.emit()
        window.faster_requested.emit()
        window.toggle_play()
        wait_until(
            app,
            lambda: (
                (row := window.frame.signals.find(sid)) is not None
                and row.section is Section.HISTORY
            ),
            "selected READY to move to History",
        )
        window.toggle_play()
        wait_until(app, lambda: window.frame.transport.playback is Playback.PAUSED, "pause")
        settle(app, 10)
        assert page.selected_key == sid and page.selected_section is Section.HISTORY
        text = page.detail_text()
        assert f"Selected {sid} moved from READY / execution-blocked to History" in text
        assert f"SIGNAL {sid}" in text
        for line in frozen.splitlines():
            if line.startswith(("SIGNAL", "READY at", "4,", "3,")):
                assert line in text  # issued identity and frozen plan values unchanged
        history = page.tables[Section.HISTORY]
        current = history.currentIndex()
        from grog.desktop.signals_page import KEY_ROLE

        assert current.isValid() and current.siblingAtColumn(0).data(KEY_ROLE) == sid
    finally:
        finish(app, window)


def test_selected_candidate_that_becomes_a_signal_is_announced(app) -> None:
    probe, sid = at_ready()
    k = probe.cursor
    candidate = probe.pipeline.signals.signals[sid].candidate_id
    s = session()
    while s.cursor < k - 1:
        assert s.step()
    assert candidate in {c.candidate_id for c in s.snapshot().forming}
    window = open_window(app, lambda _r: s)
    try:
        window.show_page(1)
        page = window.signals_page
        assert page.select_key(candidate)
        window.step_once()
        wait_until(app, lambda: window.frame.transport.processed == k, "one step")
        settle(app, 10)
        assert page.selected_key == candidate
        assert f"it became signal {sid}" in page.detail_text()
        assert f"CANDIDATE {candidate}" in page.detail_text()
    finally:
        finish(app, window)


def test_refresh_rereads_second_connection_claim_without_moving_replay(app, tmp_path: Path) -> None:
    s, sid = at_ready()
    store, _journal = open_journal(tmp_path)
    store.close()
    request = LoadRequest("syn", state_dir=str(tmp_path / "state"))
    window = open_window(app, lambda _r: s, journal_reader=read_journal, request=request)
    try:
        window.show_page(1)
        page = window.signals_page
        page.select_key(sid)
        assert keys_in(page, Section.CURRENT) == [sid]
        processed, seq = s.cursor, window.frame.tag.sequence
        store, journal = open_journal(tmp_path)  # second connection claims the signal
        try:
            r = s.pipeline.signals.signals[sid]
            journal.record_skip(
                new_action_id(), PlanRef.from_record(r), effective_ms=r.first_ready_ms
            )
        finally:
            store.close()
        window.refresh()
        wait_until(app, lambda: window.frame.tag.sequence > seq, "refreshed frame")
        settle(app, 10)
        assert s.cursor == processed and window.frame.transport.processed == processed
        assert keys_in(page, Section.CURRENT) == []
        row = window.frame.signals.find(sid)
        assert row.state == "USER_SKIPPED · READY" and row.section is Section.HISTORY
        text = page.detail_text()
        assert "USER_SKIPPED" in text and "moved from READY / execution-blocked" in text
        assert "syn [SYNTHETIC]" in text and window.frame.ready == 0
    finally:
        finish(app, window)


@pytest.mark.parametrize(
    "size", [(820, 620), (1100, 700), (1366, 768), (1440, 900), (1600, 900), (1920, 1080)]
)
def test_signals_page_layout_keeps_filters_table_and_detail_reachable(app, size) -> None:
    from dataclasses import replace

    from grog.replay.session import ReplaySession
    from ui_support import FIXTURE_POLICY, INFO, synthetic_quotes

    # Long pre-roll history states (e.g. "MISSED_PRICE_CHASE · PRE-ROLL") plus a READY.
    # A real-width 64-hex config hash: unbreakable values must not widen a narrow page.
    info = replace(
        INFO, config_hash="a782f759561ab990ef49d15fb4a9162417e710bc8ae0d999eb2cecac883ad8d4"
    )
    s = ReplaySession(
        synthetic_quotes(),
        info,
        FIXTURE_POLICY,
        from_ms=synthetic_quotes()[74_880].provider_time_ms,
    )
    sid = step_until(s, SignalEventKind.READY_ISSUED)
    window = open_window(app, lambda _r: s)
    try:
        window.resize(*size)
        window.show_page(1)
        wait_until(app, lambda: window.width() == size[0], "resize")
        page = window.signals_page
        page.select_key(sid)
        settle(app, 10)
        width = window.signals_scroll.viewport().width()
        for widget in (page.search, page.side_filter, page.state_filter, page.tabs, page.detail):
            x = widget.mapTo(page, widget.rect().topLeft()).x()
            assert widget.isVisibleTo(window) and x >= 0
            assert x + widget.width() <= width + 1, widget
        assert page.minimumSizeHint().width() <= width, (page.minimumSizeHint().width(), width)
        assert page.width() <= width and window.signals_scroll.horizontalScrollBar().maximum() == 0
        assert window.frame.signals.history  # long state labels are present in the filter
        tabs_pos = page.tabs.mapTo(page, page.tabs.rect().topLeft())
        detail_pos = page.detail.mapTo(page, page.detail.rect().topLeft())
        # Side by side only when the core plan and a detail wide enough for the 64-hex hash
        # both fit (here: the 1920 window); otherwise full-width table over the detail.
        if size[0] >= 1920:
            assert page.side_by_side and detail_pos.x() > tabs_pos.x()
        else:
            assert not page.side_by_side and detail_pos.y() > tabs_pos.y()  # page scrolls
        # Every READY column still exists (none removed to fake a fit) ...
        current = page.tables[Section.CURRENT]
        assert current.model().columnCount() == len(CURRENT_COLUMNS)
        assert not any(current.isColumnHidden(i) for i in range(len(CURRENT_COLUMNS)))
        # ... the core plan is visible without sideways scrolling at practical widths, and
        # overflow is announced instead of silently clipped.
        shown = page.visible_columns(Section.CURRENT)
        assert shown[:5] == ["Signal ID", "Side", "Current state", "Entry", "SL"]
        if size[0] >= 1100:  # ID, side, state, entry, SL, TP1, TP2
            assert set(CORE_COLUMNS[:7]) <= set(shown), shown
        if size[0] >= 1366:  # ... and time left
            assert set(CORE_COLUMNS) <= set(shown), shown
        overflow = current.horizontalHeader().length() > current.viewport().width() + 1
        assert page.more_columns.isVisibleTo(window) == overflow
        # Wrapped exact values (entry band, config hash, ...) get their full height: no crop,
        # no overlap with the next field, nothing outside the card.
        info_hash = "a782f759561ab990ef49d15fb4a9162417e710bc8ae0d999eb2cecac883ad8d4 v1"
        assert info_hash in page.detail_text()
        for lab in page.detail.findChildren(QLabel):
            if lab.isVisibleTo(window) and lab.wordWrap():
                assert lab.height() >= lab.heightForWidth(lab.width()), lab.text()[:40]
                assert longest_token_width(lab) <= lab.width(), lab.text()[:40]  # no side crop
        values = [
            page.fields.itemAt(r, QFormLayout.ItemRole.FieldRole).widget().geometry()
            for r in range(page.fields.rowCount())
        ]
        labels = [
            page.fields.itemAt(r, QFormLayout.ItemRole.LabelRole).widget().geometry()
            for r in range(page.fields.rowCount())
        ]
        for r in range(1, len(values)):
            assert values[r].top() > values[r - 1].bottom()  # rows never overlap
            assert labels[r].top() > values[r - 1].bottom()
        assert values[-1].bottom() <= page.fields_box.height()
        card_bottom = page.detail.mapTo(page, page.detail.rect().bottomLeft()).y()
        assert card_bottom <= page.height()
        assert sid in page.detail_text()
    finally:
        finish(app, window)


def test_selection_stays_on_the_same_id_while_replay_advances(app) -> None:
    s, sid = at_ready()
    window = open_window(app, lambda _r: s)
    try:
        window.show_page(1)
        page = window.signals_page
        table = page.tables[Section.CURRENT]
        table.selectRow(0)
        settle(app)
        for n in range(1, 4):
            window.step_once()
            wait_until(app, lambda n=n: window.frame.transport.processed == s.cursor, "step")
            settle(app, 5)
        row = window.frame.signals.find(sid)
        from grog.desktop.signals_page import KEY_ROLE

        assert page.selected_key == sid and not page.notice.isVisible()
        assert table.currentIndex().siblingAtColumn(0).data(KEY_ROLE) == sid
        assert row.section is Section.CURRENT
        assert page.models[Section.CURRENT].item(0, 10).text() == row.cells[10]
    finally:
        finish(app, window)


def test_filter_notice_clears_when_the_selected_row_is_visible_again(app) -> None:
    s, sid = at_ready()
    window = open_window(app, lambda _r: s)
    try:
        window.show_page(1)
        page = window.signals_page
        assert page.select_key(sid)
        settle(app)
        before = page.detail_text()
        processed = window.frame.transport.processed
        page.search.setText("no-such-signal")
        settle(app)
        assert page.notice.isVisibleTo(window)
        assert f"Selected {sid} is hidden by the current search/filter." == page.notice.text()
        page.search.clear()
        settle(app)
        assert not page.notice.isVisibleTo(window) and page.notice.text() == ""
        page.side_filter.setCurrentText("SELL" if "BUY" in before else "BUY")
        settle(app)
        assert "hidden by the current search/filter" in page.notice.text()
        page.side_filter.setCurrentText("All sides")
        settle(app)
        assert page.notice.text() == ""
        assert page.selected_key == sid and page.detail_text() == before
        assert window.frame.transport.processed == processed == s.cursor
    finally:
        finish(app, window)


def test_moved_notice_survives_filter_hide_and_clear(app) -> None:
    s, sid = at_ready()
    window = open_window(app, lambda _r: s)
    try:
        window.show_page(1)
        page = window.signals_page
        page.tables[Section.CURRENT].selectRow(0)
        settle(app)
        window.faster_requested.emit()
        window.faster_requested.emit()
        window.toggle_play()
        wait_until(
            app,
            lambda: (
                (row := window.frame.signals.find(sid)) is not None
                and row.section is Section.HISTORY
            ),
            "selected READY to move to History",
        )
        window.toggle_play()
        wait_until(app, lambda: window.frame.transport.playback is Playback.PAUSED, "pause")
        settle(app, 10)
        moved = page.notice.text()
        assert moved.startswith(f"Selected {sid} moved from") and page.notice_kind == "moved"
        page.search.setText("no-such-signal")
        settle(app)
        assert (
            page.notice.text()
            == moved + f"\nSelected {sid} is hidden by the current search/filter."
        )
        page.search.clear()
        settle(app)
        assert page.notice.text() == moved and page.selected_key == sid
    finally:
        finish(app, window)


def test_unavailable_engine_marks_selected_detail_stale_until_next_frame(app) -> None:
    s, sid = at_ready()
    window = open_window(app, lambda _r: s)
    try:
        window.show_page(1)
        page = window.signals_page
        assert page.select_key(sid)
        settle(app)
        detail = page.detail_text()
        facts = window.frame.signals
        page.show_unavailable("Signals unavailable — source fault")
        assert page.notice_kind == "stale" and page.notice.isVisibleTo(window)
        assert f"Detail for {sid} is the last known state, not current." in page.notice.text()
        assert page.selected_key == sid and f"SIGNAL {sid}" in page.detail_text()
        page.apply(facts)  # a fresh engine frame with the row present clears the warning
        assert page.notice_kind is None and page.notice.text() == ""
        assert page.detail_text() == detail
    finally:
        finish(app, window)
