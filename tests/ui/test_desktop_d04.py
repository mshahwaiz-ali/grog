"""D04 desktop: Diagnostics page (GUI-52/53), keyboard help and focus guards (GUI-58),
honest STALE diagnostics after a mid-run source fault (GUI-55). Disposable state only."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from test_desktop_d03 import (  # noqa: E402
    app,  # noqa: F401 - fixture
    at_ready,
    finish,
    make_state,
    open_d03,
    pending,
    settle,
    wait_until,
)

from grog.desktop.frames import OverviewFrame, Phase, StatusFrame  # noqa: E402
from grog.desktop.journal_model import JournalMode  # noqa: E402
from grog.desktop.journal_worker import JournalWorker  # noqa: E402
from grog.desktop.replay_worker import ReplayWorker  # noqa: E402
from grog.desktop.window import SHORTCUT_HELP, GoldWindow  # noqa: E402


def test_gui52_53_fifth_page_by_key_shows_owner_diagnostics_and_journal(app, tmp_path):  # noqa: F811
    s, _sid = at_ready()
    window = open_d03(app, s, make_state(tmp_path))
    try:
        assert all(b.isEnabled() for b in window.nav)
        window.activateWindow()
        window.setFocus()
        QTest.keyClick(window, Qt.Key.Key_5)
        settle(app)
        assert window.page_index == 4
        page = window.diagnostics_page
        wait_until(app, lambda: page.facts is not None and page.cards, "diagnostics cards")
        text = page.text()
        facts = window.frame.diag
        scoped = facts.summary.removeprefix("Summary: ")
        assert f"Replay source checks only (terminal summary): {scoped}" in text
        assert facts.mode_line in text
        assert page.summary.text().startswith("Overall: no problems found in any group")
        assert "all checks OK" not in page.summary.text()  # R0 scope never the overall
        for g in facts.groups:  # the worker-built evidence is shown verbatim
            assert g.title in text
            for r in g.rows:
                assert r.text in text
        assert "REFERENCE ADAPTER (READ-ONLY) [NOT CONFIGURED]" in text
        assert "LOCAL JOURNAL / ERRORS [OK]" in text and "WRITABLE" in text
        assert f"Replay cursor (quotes processed): {window.frame.clock.cursor:,}" in text
        assert "LIVE" not in facts.mode_line
    finally:
        finish(app, window)


def test_gui58_help_lists_every_binding_and_keys_do_nothing_while_typing(app, tmp_path):  # noqa: F811
    s, _sid = at_ready()
    window = open_d03(app, s, make_state(tmp_path))
    try:
        installed = {sc.key().toString() for sc in window.shortcuts}
        documented = " ".join(k for k, _w in SHORTCUT_HELP).replace("…", "1 2 3 4 5")
        for key in installed:
            assert key in documented.split() or key in documented, key
        window.show_page(3)
        search = window.journal_page.search
        search.setFocus()
        QTest.keyClicks(search, "?5q e")
        settle(app)
        assert search.text() == "?5q e"
        assert window.page_index == 3 and window.help_dialog is None and window.isVisible()
        window.journal_page.table.setFocus()
        assert {"?", "F1"} <= installed  # both bindings really installed on the window
        QTest.keyClick(window, Qt.Key.Key_F1)  # real key event, no fallback
        settle(app)
        dialog = window.help_dialog
        assert dialog.isVisible() and dialog.focusWidget() is dialog.close_button
        for keys, what in SHORTCUT_HELP:
            assert keys in dialog.text() and what in dialog.text()
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        settle(app)
        assert not dialog.isVisible() and window.isVisible()
        # "?" needs Shift on most layouts, which offscreen QPA does not map; activate the
        # installed "?" QShortcut itself (same slot) to prove it opens the same dialog.
        (question,) = [sc for sc in window.shortcuts if sc.key().toString() == "?"]
        question.activated.emit()
        settle(app)
        assert window.help_dialog is dialog and dialog.isVisible()
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        settle(app)
    finally:
        finish(app, window)


class _FailingSession:
    """A real session whose next step raises (deterministic mid-run source fault)."""

    def __init__(self, real) -> None:
        self._real = real
        self.armed = False

    def step(self, *a, **kw):
        if self.armed:
            raise OSError("simulated read error in the replay source (test harness)")
        return self._real.step(*a, **kw)

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_gui55_fault_after_frames_keeps_last_diagnostics_labelled_stale(app, tmp_path):  # noqa: F811
    s, _sid = at_ready()
    failing = _FailingSession(s)
    window = GoldWindow(
        make_state(tmp_path),
        worker=ReplayWorker(loader=lambda _r: failing, journal_reader=pending),
        journal_worker=JournalWorker(),
    )
    window.resize(1440, 900)
    window.show()
    try:
        wait_until(app, lambda: isinstance(window.frame, OverviewFrame), "first frame")
        wait_until(app, lambda: window.manual.snapshot is not None, "journal")
        assert window.manual.snapshot.mode is JournalMode.WRITABLE
        window.show_page(4)
        last = window.frame.diag
        failing.armed = True
        window.step_once()
        wait_until(
            app,
            lambda: isinstance(window.frame, StatusFrame) and window.frame.phase is Phase.FAULT,
            "mid-run fault",
        )
        settle(app)
        page = window.diagnostics_page
        text = page.text()
        assert text.startswith("STALE — the source stopped") and "not current" in text
        assert "simulated read error" in text
        assert page.facts == last  # last good evidence, unchanged
        assert last.summary.removeprefix("Summary: ") in page.source_summary.text()
        assert page.summary.text().startswith("Overall (STALE — last good values, not current)")
        assert not window.play.isEnabled() and not window.step.isEnabled()
    finally:
        finish(app, window)


def test_gui54_fast_replay_with_journal_owner_and_mid_load_source_switch(app, tmp_path):  # noqa: F811
    """Long FAST replay to the end with the D03 journal owner running: every engine event
    reaches the frame (same IDs/order as a direct replay), diagnostics show the final
    cursor; then a source switch mid-load applies no frame or journal snapshot of the old
    generation, and SQLite stays on the journal owner thread."""
    import threading

    from grog.desktop.loading import LoadRequest
    from grog.domain.enums import Side  # noqa: F401 - keeps fixture imports explicit
    from ui_support import open_journal, record_unlinked, session

    request = make_state(tmp_path)
    store, j = open_journal(tmp_path)
    record_unlinked(j)
    store.close()
    gate = threading.Event()
    gate.set()
    made: list = []

    def loader(_r):
        gate.wait(30)
        made.append(session())
        return made[-1]

    journal = JournalWorker()
    window = GoldWindow(
        request,
        worker=ReplayWorker(loader=loader, journal_reader=pending),
        journal_worker=journal,
    )
    window.resize(1366, 768)
    window.show()
    try:
        wait_until(app, lambda: isinstance(window.frame, OverviewFrame), "first frame")
        wait_until(app, lambda: window.manual.snapshot is not None, "journal")
        window.faster_requested.emit()
        window.faster_requested.emit()
        wait_until(app, lambda: window.frame.transport.pace_text == "FAST", "FAST")
        window.toggle_play()
        wait_until(
            app,
            lambda: (
                isinstance(window.frame, OverviewFrame)
                and window.frame.transport.playback.name == "ENDED"
            ),
            "replay end",
            timeout=90,
        )
        settle(app)
        end = window.frame
        direct = session()
        while direct.step():
            pass
        assert end.transport.processed == end.transport.total == len(direct.quotes)
        assert [r.key for r in end.engine_rows] == [
            e.event_id for e in direct.pipeline.signals.events
        ]
        assert f"Replay cursor (quotes processed): {direct.cursor:,}" in end.diag.text()
        assert window.frames_applied <= window.frames_received
        owner = journal.owner_thread_name
        assert owner not in (None, threading.current_thread().name)

        applied: list[int] = []
        original = window._apply_overview

        def spy(frame):
            applied.append(frame.tag.generation)
            original(frame)

        window._apply_overview = spy
        gate.clear()  # the new source is still loading on the owner thread
        new_gen = window.load_source(LoadRequest("syn", state_dir=request.state_dir))
        settle(app, 50)
        assert window.manual.snapshot is None and window.diagnostics_page.journal is None
        assert applied == []  # nothing of the old generation is painted while loading
        gate.set()
        wait_until(
            app,
            lambda: (
                isinstance(window.frame, OverviewFrame)
                and window.frame.tag.generation == new_gen
                and window.manual.snapshot is not None
            ),
            "new source frame and journal",
        )
        assert set(applied) == {new_gen}
        assert window.manual.snapshot.generation == new_gen
        assert window.frame.transport.processed < end.transport.total  # a fresh replay
        assert journal.owner_thread_name == owner  # same journal owner thread, no GUI SQL
    finally:
        gate.set()
        finish(app, window)


def test_gui55_forced_exit_while_saving_commits_or_fails_truthfully(app, tmp_path):  # noqa: F811
    """Program exit (window.shutdown, the aboutToQuit path) during a Save:
    - signal form still waiting for its save-time re-check: never submitted, reported
      NOT SAVED SHUTTING_DOWN, nothing written;
    - OFF_PLAN command already submitted: runs on the journal owner before it stops and
      its real SAVED result is recorded once. Both owner threads exit."""
    from test_desktop_d03 import decisions, events, fill, open_form

    s, sid = at_ready()
    window = open_d03(app, s, make_state(tmp_path))
    dialog = open_form(app, window, "skip", sid)
    n = len(window.manual.results)
    dialog.confirm_button.click()
    assert dialog.state == dialog.SAVING
    window.shutdown()
    settle(app, 50)
    assert not window._threads_running()
    got = window.manual.results[n:]
    assert decisions(tmp_path) == [] and len(got) == 1, got
    assert not got[0].saved and got[0].code == "SHUTTING_DOWN"

    from grog.ui.format import iso_utc

    s2, _sid = at_ready()
    window = open_d03(app, s2, make_state(tmp_path / "second"))
    try:
        off = open_form(app, window, "offplan")
        t = iso_utc(window.frame.clock.virtual_ms)
        fill(off, side="BUY", price="4000.10", qty="1", time=t, stop="3990", ack="yes")
        settle(app)
        assert off.confirm_button.isEnabled()
        n = len(window.manual.results)
        off.confirm_button.click()  # position form: submitted to the journal owner at once
        window.shutdown()
        settle(app, 50)
        assert not window._threads_running()
    finally:
        if window._threads_running():
            finish(app, window)
    got = window.manual.results[n:]
    assert len(got) == 1 and got[0].saved and got[0].created, got
    assert [e[2] for e in events(tmp_path / "second")] == ["ENTRY"]  # exactly once


SIZES = [((820, 620), "narrow"), ((1366, 768), "medium"), ((1920, 1080), "wide")]


@pytest.mark.parametrize(("size", "mode"), SIZES)
def test_gui56_all_five_pages_fit_each_size(app, tmp_path, size, mode):  # noqa: F811
    """Measured page layout: no page needs horizontal scrolling, the safety toolbar stays
    visible, Diagnostics uses 2 columns only when wide and keeps full 64-hex hashes as
    selectable text, at 820x620, 1366x768 and 1920x1080."""
    import re

    s, _sid = at_ready()
    window = open_d03(app, s, make_state(tmp_path))
    try:
        window.resize(*size)
        wait_until(app, lambda: window.layout_mode == mode, f"{mode} layout")
        for index in range(5):
            window.show_page(index)
            settle(app)
            page = window.scroll.widget()
            assert page.minimumSizeHint().width() <= window.scroll.viewport().width(), index
            assert window.toolbar.isVisibleTo(window)
        diag = window.diagnostics_page
        assert diag.columns == (2 if mode == "wide" else 1)
        assert re.search(r"\b[0-9a-f]{64}\b", diag.text())  # full hash, never elided
    finally:
        finish(app, window)


def _inside(widget, outer) -> bool:
    from PySide6.QtCore import QPoint, QRect

    top_left = widget.mapTo(outer, QPoint(0, 0))
    return outer.rect().contains(QRect(top_left, widget.size()))


def _scroll_geometry(field, area) -> str:
    """Describe failed containment without relaxing the GUI-56 visibility gate."""
    from PySide6.QtCore import QPoint, QRect

    viewport = area.viewport()
    field_rect = QRect(field.mapTo(viewport, QPoint(0, 0)), field.size())
    hbar, vbar = area.horizontalScrollBar(), area.verticalScrollBar()
    content = area.widget()
    return (
        f"field={field_rect.getRect()} viewport={viewport.rect().getRect()} "
        f"content={content.width()}x{content.height()} "
        f"hscroll={hbar.value()}/{hbar.maximum()} "
        f"vscroll={vbar.value()}/{vbar.maximum()}"
    )


EXPECTED_FORMS = [  # (kind, has an explicit acknowledgement box); off-plan = ENTRY + ack
    ("entry", "ENTRY", False),
    ("skip", "SKIP", False),
    ("offplan", "ENTRY", True),
    ("partial", "PARTIAL", False),
    ("modify", "MODIFY", False),
    ("close", "CLOSE", False),
    ("confirm", "CONFIRM_OPEN", True),
]


@pytest.mark.parametrize(("size", "mode"), SIZES)
def test_gui56_every_manual_form_and_help_real_geometry(app, tmp_path, size, mode):  # noqa: F811
    """All seven manual form types and the help dialog, each constrained to the window's
    box (820x620 / 1366x768 / 1920x1080; run also with QT_SCALE_FACTOR=1.25 and 1.5):
    the dialog can shrink into the box, Cancel and Confirm are fully inside it, visible
    and never narrower than their text, the scrolling field area keeps a usable height
    and really scrolls to the last field, the preview stays visible, Cancel is focused;
    help shows every line inside its box without scrolling and Close focused."""
    from PySide6.QtWidgets import QLabel, QScrollArea
    from test_desktop_d03 import open_form

    from ui_support import open_journal, record_unlinked

    s, sid = at_ready()
    request = make_state(tmp_path)
    store, j = open_journal(tmp_path)
    record_unlinked(j)  # MONITORING -> RECONCILIATION_REQUIRED on open (confirm-open form)
    store.close()
    window = open_d03(app, s, request)
    try:
        window.resize(*size)
        wait_until(app, lambda: window.layout_mode == mode, f"{mode} layout")
        (pos,) = window.manual.snapshot.positions
        for kind, cmd_kind, ack in EXPECTED_FORMS:
            target = {"entry": sid, "skip": sid, "offplan": ""}.get(kind, pos.position_id)
            dialog = open_form(app, window, kind, target)
            assert (dialog.spec.kind.value, "ack" in dialog.inputs) == (cmd_kind, ack), kind
            dialog.resize(min(dialog.width(), size[0]), min(dialog.height(), size[1]))
            settle(app)
            assert dialog.width() <= size[0] and dialog.height() <= size[1], (kind, dialog.size())
            for button in (dialog.cancel_button, dialog.confirm_button):
                assert button.isVisible() and _inside(button, dialog), (kind, button.text())
                assert button.width() >= button.sizeHint().width(), (kind, button.text())
            assert dialog.focusWidget() is dialog.cancel_button, kind  # Cancel is default
            area = dialog.findChild(QScrollArea)
            viewport = area.viewport()
            assert viewport.height() >= 120, (kind, viewport.height())  # usable, not a slit
            fields = list(dialog.inputs.values())
            for field in (fields[-1], fields[0]):  # really reachable by scrolling
                area.ensureWidgetVisible(field)
                settle(app)
                assert field.isVisible() and _inside(field, viewport), (
                    kind,
                    field.objectName(),
                    _scroll_geometry(field, area),
                )
            region = dialog.preview_scroll  # fixed-height preview region, always visible
            assert region.isVisible() and _inside(region, dialog), kind
            assert region.height() >= 4 * dialog.preview.fontMetrics().lineSpacing(), kind
            dialog.done(0)
            wait_until(app, lambda: window.manual.dialog is None, f"{kind} closed")
        helper = window.show_help()
        settle(app)
        helper.resize(min(helper.width(), size[0]), min(helper.height(), size[1]))
        settle(app)
        assert helper.width() <= size[0] and helper.height() <= size[1]
        assert helper.findChild(QScrollArea) is None  # nothing hidden behind scrolling
        for text in helper.findChildren(QLabel):
            if text.text():
                assert text.isVisible() and _inside(text, helper), text.text()
        assert _inside(helper.close_button, helper)
        assert helper.focusWidget() is helper.close_button
        helper.close()
    finally:
        finish(app, window)


def test_gui55_read_only_and_unavailable_journal_turn_the_overall_verdict(app, tmp_path):  # noqa: F811
    """Read-only journal: the Diagnostics header says NEEDS ATTENTION naming the journal,
    while the scoped replay-source line may still say all checks OK."""
    s, _sid = at_ready()

    def refuse(_db):
        raise PermissionError("--read-only requested")

    window = open_d03(
        app, s, make_state(tmp_path), JournalWorker(writable_opener=refuse), JournalMode.READ_ONLY
    )
    try:
        window.show_page(4)
        page = window.diagnostics_page
        wait_until(app, lambda: page.cards, "cards")
        header = page.summary.text()
        assert "NEEDS ATTENTION — LOCAL JOURNAL / ERRORS DEGRADED" in header, header
        assert "no problems" not in header and "all checks OK" not in header
        assert page.source_summary.text().startswith("Replay source checks only")
    finally:
        finish(app, window)


def test_form_preview_has_fixed_height_so_ticking_ack_never_moves_the_fields(app, tmp_path):  # noqa: F811
    """Regression (native D04 at 150%): ticking the off-plan acknowledgement grew the
    preview card by ~51 px, shrank the scrolling field area and pushed the checkbox just
    clicked out of view. The preview region now has a fixed height."""
    from PySide6.QtWidgets import QScrollArea
    from test_desktop_d03 import fill, open_form

    from grog.ui.format import iso_utc

    s, _sid = at_ready()
    window = open_d03(app, s, make_state(tmp_path))
    try:
        window.resize(820, 620)
        settle(app)
        dialog = open_form(app, window, "offplan")
        dialog.resize(760, 620)
        t = iso_utc(window.frame.clock.virtual_ms)
        fill(dialog, side="BUY", price="4000.10", qty="1", time=t, stop="3990")
        area = dialog.findChild(QScrollArea)
        ack = dialog.inputs["ack"]
        area.ensureWidgetVisible(ack)
        settle(app)

        def geometry():
            top = ack.mapTo(area.viewport(), ack.rect().topLeft()).y()
            bar = area.verticalScrollBar()
            return area.viewport().height(), bar.value(), top, dialog.preview_scroll.height()

        before, text_before = geometry(), dialog.preview.text()
        ack.click()
        settle(app)
        assert dialog.preview.text() != text_before  # the preview really changed
        assert geometry() == before, (before, geometry())
        assert _inside(ack, area.viewport())
        ack.click()
        settle(app)
        assert geometry() == before
        dialog.done(0)
    finally:
        finish(app, window)
