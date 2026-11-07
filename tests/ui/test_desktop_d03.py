"""D03 Positions / Journal / manual forms with the real replay and journal owner threads.

Every database is a disposable tmp copy; the replay is the synthetic fixture source.
GUI ids refer to docs/08 §20.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt, QThread  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton  # noqa: E402

from grog.desktop.frames import OverviewFrame  # noqa: E402
from grog.desktop.journal_model import JournalMode  # noqa: E402
from grog.desktop.journal_worker import JournalWorker  # noqa: E402
from grog.desktop.loading import LoadRequest  # noqa: E402
from grog.desktop.replay_worker import ReplayWorker  # noqa: E402
from grog.desktop.signals_model import Section  # noqa: E402
from grog.desktop.window import GoldWindow  # noqa: E402
from grog.domain.clock import SystemClock  # noqa: E402
from grog.domain.enums import SignalEventKind  # noqa: E402
from grog.journal.positions import PlanRef, PositionState, new_action_id  # noqa: E402
from grog.journal.store import STATE_DB_FILENAME, Store, available_migrations  # noqa: E402
from grog.replay.session import Playback  # noqa: E402
from grog.ui.format import iso_utc  # noqa: E402
from ui_support import open_journal, record_unlinked, session, step_until  # noqa: E402

TIMEOUT_S = 30.0


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication(["gold-desktop-test"])


def wait_until(app, predicate, what: str, timeout: float = TIMEOUT_S) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        app.processEvents()
        QThread.msleep(1)


def settle(app, n: int = 10) -> None:
    for _ in range(n):
        app.processEvents()
        QThread.msleep(1)


def pending(_request):
    return None, None, "Opening the local journal…"


def db_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / STATE_DB_FILENAME


def make_state(tmp_path: Path) -> LoadRequest:
    store, _j = open_journal(tmp_path)
    store.close()
    return LoadRequest("syn", state_dir=str(tmp_path / "state"))


def at_ready(nth: int = 1):
    s = session()
    return s, step_until(s, SignalEventKind.READY_ISSUED, nth)


def open_d03(app, s, request, journal_worker=None, mode=JournalMode.WRITABLE) -> GoldWindow:
    window = GoldWindow(
        request,
        worker=ReplayWorker(loader=lambda _r: s, journal_reader=pending),
        journal_worker=journal_worker or JournalWorker(),
    )
    window.resize(1440, 900)
    window.show()
    wait_until(app, lambda: isinstance(window.frame, OverviewFrame), "first frame")
    wait_until(app, lambda: window.manual.snapshot is not None, "journal snapshot")
    assert window.manual.snapshot.mode is mode, window.manual.snapshot.reason
    wait_until(
        app,
        lambda: window.frame.positions.journal_note.startswith("Local journal"),
        "records pushed to the replay owner",
    )
    return window


def finish(app, window: GoldWindow) -> None:
    if window.manual.dialog is not None:
        window.manual.dialog.state = window.manual.dialog.EDITING
        window.manual.dialog.done(0)
        settle(app)
    window.close()
    wait_until(app, lambda: not window._threads_running(), "owner threads to finish")
    app.processEvents()


def events(tmp_path: Path) -> list[tuple]:
    con = sqlite3.connect(f"file:{db_path(tmp_path)}?mode=ro", uri=True)
    try:
        return con.execute(
            "SELECT event_id, position_id, action_type FROM position_events ORDER BY rowid"
        ).fetchall()
    finally:
        con.close()


def decisions(tmp_path: Path) -> list[tuple]:
    con = sqlite3.connect(f"file:{db_path(tmp_path)}?mode=ro", uri=True)
    try:
        return con.execute("SELECT signal_id, decision FROM signal_decisions").fetchall()
    finally:
        con.close()


def signal_row(window, sid):
    facts = window.frame.signals
    return next(r for sec in Section for r in facts.rows(sec) if r.key == sid)


def open_form(app, window, kind, target=""):
    if kind in ("entry", "skip"):
        window._on_action_requested(kind, target)
    elif kind == "offplan":
        window._on_action_requested("offplan", "")
    else:
        window._on_action_requested(kind, target)
    wait_until(app, lambda: window.manual.dialog is not None, f"{kind} form")
    settle(app)
    return window.manual.dialog


def fill(dialog, **values) -> None:
    for key, text in values.items():
        w = dialog.inputs[key]
        if key == "ack":
            w.setChecked(text == "yes")
        elif key == "side":
            w.setCurrentText(text)
        else:
            w.setText(text)


def confirm_and_wait(app, window, dialog):
    n = len(window.manual.results)
    dialog.confirm_button.click()
    wait_until(app, lambda: dialog.state != dialog.SAVING, "save result")
    settle(app)
    return window.manual.results[n] if len(window.manual.results) > n else None


def close_dialog(app, window) -> None:
    dialog = window.manual.dialog
    dialog.cancel_button.click()
    wait_until(app, lambda: window.manual.dialog is None, "form closed")
    settle(app)


# --------------------------------------------------------------------------- GUI-30/06/47


def test_gui30_47_entry_from_signals_button_cancel_focus_keys_dirty_esc_and_one_save(app, tmp_path):
    s, sid = at_ready()
    request = make_state(tmp_path)
    window = open_d03(app, s, request)
    try:
        window.show_page(1)
        page = window.signals_page
        table = page.tables[Section.CURRENT]
        page.tabs.setCurrentIndex(1)
        table.selectRow(0)
        wait_until(app, lambda: page.selected_key == sid, "READY row selected")
        entry = next(b for b in page.action_buttons if b.property("action_kind") == "entry")
        assert entry.isEnabled() and entry.text() == "Record entry (on-plan)"
        cursor = window.frame.clock.cursor
        entry.click()
        wait_until(app, lambda: window.manual.dialog is not None, "entry form")
        dialog = window.manual.dialog
        settle(app)
        assert dialog.isVisible() and dialog.focusWidget() is dialog.cancel_button
        assert not window.play.isEnabled() and not window.step.isEnabled()
        assert "Paused while recording" in window.progress.text()
        assert not dialog.confirm_button.isEnabled()  # price/qty still missing
        # GUI-47: global keys typed into a field stay literal input
        price = dialog.inputs["price"]
        price.setFocus()
        typed = "e s q p m x n 1 2 3"
        QTest.keyClicks(price, typed)
        QTest.keyClick(price, Qt.Key.Key_Space)
        settle(app, 20)
        assert price.text() == typed + " "
        assert window.page_index == 1 and not window._closing and window.manual.dialog is dialog
        assert window.frame.clock.cursor == cursor and window.frame.transport.playback is (
            Playback.PAUSED
        )
        # dirty Esc needs a second Esc; nothing is written
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        settle(app)
        assert dialog.isVisible() and dialog.discard_bar.isVisible()
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        wait_until(app, lambda: window.manual.dialog is None, "discarded")
        assert events(tmp_path) == [] and decisions(tmp_path) == []
        assert window.frame.transport.playback is Playback.PAUSED  # stays paused

        dialog = open_form(app, window, "entry", sid)
        plan = dialog.spec.opened.plan
        fill(dialog, price=str(plan.e0), qty="0.10")
        settle(app)
        assert dialog.confirm_button.isEnabled()
        dialog.inputs["qty"].setFocus()
        QTest.keyClick(dialog.inputs["qty"], Qt.Key.Key_Return)  # Enter never submits
        settle(app)
        assert dialog.state == dialog.EDITING and events(tmp_path) == []
        action_id = dialog.action_id
        dialog.confirm_button.click()
        dialog.confirm_button.click()  # double-click: the second is ignored while saving
        wait_until(app, lambda: dialog.state == dialog.SAVED, "SAVED LOCALLY")
        assert "SAVED LOCALLY" in dialog.outcome.text() and action_id in dialog.outcome.text()
        assert [e[0] for e in events(tmp_path)] == [action_id]  # exactly one local event
        assert len(window.manual.results) == 1
        assert not dialog.confirm_button.isEnabled() and dialog.cancel_button.text() == "Close"
        close_dialog(app, window)
        wait_until(app, lambda: signal_row(window, sid).detail.actions[0].enabled is False,
                   "overlay pushed to replay")  # fmt: skip
        assert "already ENTERED" in window.signals_page.detail_text()
        assert window.frame.transport.playback is Playback.PAUSED
        assert window.play.isEnabled()  # resumable only by the operator
        pos = window.manual.snapshot.positions[0]
        assert pos.plan == PlanRef.from_record(
            next(v for v in s.snapshot().signals if v.record.signal_id == sid).record
        )
        window.show_page(2)
        assert window.positions_page.model.rowCount() == 1
    finally:
        finish(app, window)


# --------------------------------------------------------------------------- GUI-33/07


def test_gui33_changed_or_claimed_signal_is_not_saved_on_plan_and_off_plan_is_separate(
    app, tmp_path
):
    s, sid = at_ready()
    request = make_state(tmp_path)
    window = open_d03(app, s, request)
    try:
        dialog = open_form(app, window, "entry", sid)
        plan = dialog.spec.opened.plan
        fill(dialog, price=str(plan.e0), qty="0.10", fees="0")
        # the replay moves while the form is open (simulated external change)
        window._step_to_owner.emit(window._generation)
        wait_until(app, lambda: window.frame.clock.cursor == dialog.spec.opened.cursor + 1,
                   "cursor moved")  # fmt: skip
        res = confirm_and_wait(app, window, dialog)
        assert res is None and dialog.state == dialog.EDITING  # never reached the journal
        assert "SIGNAL_CHANGED" in dialog.outcome.text() and "cursor" in dialog.outcome.text()
        assert not dialog.confirm_button.isEnabled() and dialog.off_plan_button.isVisible()
        assert events(tmp_path) == []
        first_action = dialog.action_id
        dialog.off_plan_button.click()
        wait_until(app, lambda: window.manual.dialog not in (None, dialog), "OFF_PLAN form")
        off = window.manual.dialog
        assert off.action_id != first_action and off.spec.form_id == "record-unlinked"
        assert off.values()["side"] == plan.side.value and off.values()["signal"] == sid
        assert not off.confirm_button.isEnabled()  # explicit acknowledgement still required
        fill(off, ack="yes")
        res = confirm_and_wait(app, window, off)
        assert res.saved
        snap = window.manual.snapshot
        assert snap.positions[0].plan is None and snap.positions[0].plan_status.value == (
            "OFF_PLAN"
        )
        assert snap.overlay() == {}  # the READY signal itself was never claimed
        close_dialog(app, window)

        # claimed by a second local instance while the form is open
        dialog = open_form(app, window, "skip", sid)
        store2, j2 = open_journal(tmp_path)
        j2.record_entry(
            __import__("grog.journal.positions", fromlist=["EntryRequest"]).EntryRequest(
                action_id=new_action_id(), side=plan.side, price=plan.e0, qty=Decimal("1"),
                fill_ms=dialog.spec.opened.virtual_ms, source_id="syn",
                plan=dialog.spec.opened.plan, signal_ready=True,
            )
        )  # fmt: skip
        store2.close()
        res = confirm_and_wait(app, window, dialog)
        assert res is not None and not res.saved and res.code == "SIGNAL_ALREADY_ENTERED"
        assert "NOT SAVED" in dialog.outcome.text() and decisions(tmp_path) == []
    finally:
        finish(app, window)


def test_gui07_terminal_signal_never_opens_an_on_plan_form(app, tmp_path):
    s, sid = at_ready()
    while s.step():
        if all(v.status.state.value != "READY" for v in s.snapshot().signals
               if v.record.signal_id == sid):  # fmt: skip
            break
    window = open_d03(app, s, make_state(tmp_path))
    try:
        window._on_action_requested("entry", sid)
        wait_until(app, lambda: "Nothing opened" in window.notice.text(), "refusal notice")
        assert window.manual.dialog is None and not window.manual.busy
        assert events(tmp_path) == []
    finally:
        finish(app, window)


# --------------------------------------------------------------------------- GUI-06/36-38/43


def test_gui06_position_journeys_partial_modify_close_and_off_plan_persist(app, tmp_path):
    s, sid = at_ready()
    request = make_state(tmp_path)
    window = open_d03(app, s, request)
    try:
        t = iso_utc(window.frame.clock.virtual_ms)
        off = open_form(app, window, "offplan")
        fill(off, side="BUY", price="4000.10", qty="1", time=t, stop="3990", ack="yes")
        assert confirm_and_wait(app, window, off).saved
        close_dialog(app, window)
        pid = window.manual.snapshot.positions[0].position_id
        window.show_page(2)
        pp = window.positions_page
        pp.table.selectRow(0)
        wait_until(app, lambda: pp.selected_key == pid, "position selected")
        assert pp.buttons["partial"].isEnabled() and not pp.buttons["confirm"].isVisible()

        pp.buttons["partial"].click()
        wait_until(app, lambda: window.manual.dialog is not None, "partial form")
        d = window.manual.dialog
        fill(d, price="4001", qty="1", time=t)
        settle(app)
        assert not d.confirm_button.isEnabled()  # = remaining is a close, preview rejects
        fill(d, qty="0.4")
        assert confirm_and_wait(app, window, d).saved
        close_dialog(app, window)

        pp.buttons["modify"].click()
        wait_until(app, lambda: window.manual.dialog is not None, "modify form")
        d = window.manual.dialog
        fill(d, stop="3980", time=t)
        settle(app)
        assert "FURTHER AWAY" in d.preview.text()
        assert confirm_and_wait(app, window, d).saved
        close_dialog(app, window)

        window.activateWindow()  # offscreen QPA does not hand activation back after a modal
        wait_until(app, window.isActiveWindow, "window active again")
        pp.table.setFocus()
        QTest.keyClick(pp.table, Qt.Key.Key_X)  # scoped shortcut on the Positions page
        wait_until(app, lambda: window.manual.dialog is not None, "close form")
        d = window.manual.dialog
        assert d.values()["qty"] == "0.6"
        fill(d, price="4002", time=t, fees="0.5")
        assert confirm_and_wait(app, window, d).saved
        close_dialog(app, window)
        acts = [e[2] for e in events(tmp_path)]
        assert acts == ["ENTRY", "PARTIAL_CLOSE", "MODIFY", "CLOSE"]
        snap = window.manual.snapshot
        assert snap.positions[0].state is PositionState.CLOSED
        assert snap.positions[0].initial_risk == Decimal("10.10")  # frozen at entry
        pp.filter.setCurrentText("Closed")
        settle(app)
        assert pp.model.rowCount() == 1 and not pp.buttons["partial"].isEnabled()
        # Journal page: durable operator rows with recorded UTC, plus SIM ENGINE rows
        window.show_page(3)
        jp = window.journal_page
        settle(app)
        producers = {jp.model.item(r, 2).text() for r in range(jp.model.rowCount())}
        assert producers == {"OPERATOR", "SIM ENGINE"}
        jp.stream.setCurrentText("OPERATOR")
        settle(app)
        assert jp.model.rowCount() == 4
        assert [jp.model.item(r, 3).text() for r in range(4)] == [
            "CLOSE", "MODIFY", "PARTIAL_CLOSE", "ENTRY",
        ]  # newest first, stable for equal times  # fmt: skip
        jp.table.selectRow(0)
        settle(app)
        assert "RECORDED UTC" in jp.detail_text_label.text()
        assert "durable" in jp.detail_text_label.text()
    finally:
        finish(app, window)


def test_gui42_43_restart_restores_once_and_confirm_open_needs_explicit_ack(app, tmp_path):
    s, _sid = at_ready()
    request = make_state(tmp_path)
    store, j = open_journal(tmp_path)
    already = record_unlinked(j)
    j.restore_on_startup()  # already RECONCILIATION_REQUIRED before this start
    monitoring = record_unlinked(j)
    store.close()
    before = events(tmp_path)
    window = open_d03(app, s, request)
    try:
        snap = window.manual.snapshot
        assert snap.restored == (monitoring.position_id,)
        new = events(tmp_path)[len(before) :]
        assert [(e[1], e[2]) for e in new] == [(monitoring.position_id, "RESTORED_UNVERIFIED")]
        assert {p.state for p in snap.positions} == {PositionState.RECONCILIATION_REQUIRED}
        window.show_page(2)
        pp = window.positions_page
        assert "RECONCILIATION REQUIRED: 2 position(s)" in pp.worklist.text()
        assert already.position_id in pp.worklist.text()
        pp.filter.setCurrentText("Needs reconciliation")
        settle(app)
        assert pp.model.rowCount() == 2
        keys = [pp.model.item(r, 0).text() for r in range(2)]
        pp.table.selectRow(keys.index(monitoring.position_id))
        settle(app)
        assert pp.buttons["confirm"].isVisible() and pp.buttons["confirm"].isEnabled()
        pp.buttons["confirm"].click()
        wait_until(app, lambda: window.manual.dialog is not None, "confirm form")
        d = window.manual.dialog
        fill(d, time=iso_utc(window.frame.clock.virtual_ms))
        settle(app)
        assert not d.confirm_button.isEnabled()  # broker verification ack is mandatory
        fill(d, ack="yes")
        assert confirm_and_wait(app, window, d).saved
        close_dialog(app, window)
        states = {p.position_id: p.state for p in window.manual.snapshot.positions}
        assert states[monitoring.position_id] is PositionState.MONITORING
        assert states[already.position_id] is PositionState.RECONCILIATION_REQUIRED
    finally:
        finish(app, window)
    # a second start: the confirmed one is restored again, the other is not duplicated
    count = len(events(tmp_path))
    window = open_d03(app, session(), request)
    try:
        assert window.manual.snapshot.restored == (monitoring.position_id,)
        assert len(events(tmp_path)) == count + 1
    finally:
        finish(app, window)


# --------------------------------------------------------------------------- GUI-44


def test_gui44_read_only_database_is_unverified_and_refuses_every_record(app, tmp_path):
    s, sid = at_ready()
    request = make_state(tmp_path)
    store, j = open_journal(tmp_path)
    pos = record_unlinked(j)
    store.close()
    db = db_path(tmp_path)
    os.chmod(db, 0o444)
    os.chmod(db.parent, 0o555)
    try:
        digest = db.read_bytes()
        window = open_d03(app, s, request, mode=JournalMode.READ_ONLY)
        try:
            snap = window.manual.snapshot
            assert "UNVERIFIED" in snap.reason and "writable open failed" in snap.reason
            assert snap.restored == () and snap.positions[0].state is PositionState.MONITORING
            window.show_page(2)
            pp = window.positions_page
            assert "UNVERIFIED (read-only)" in pp.model.item(0, 9).text()
            assert not pp.off_plan_button.isEnabled()
            window.show_page(1)
            window.signals_page.tabs.setCurrentIndex(1)
            window.signals_page.tables[Section.CURRENT].selectRow(0)
            wait_until(app, lambda: window.signals_page.selected_key == sid, "row")
            assert all(not b.isEnabled() for b in window.signals_page.action_buttons)
            assert "READ ONLY" in window.signals_page.action_reason.text()
            window._on_action_requested("entry", sid)
            settle(app, 30)
            assert window.manual.dialog is None
        finally:
            finish(app, window)
        assert db.read_bytes() == digest  # no invented reconciliation, nothing written
        assert pos.position_id in digest.decode("latin-1")
    finally:
        os.chmod(db.parent, 0o755)
        os.chmod(db, 0o644)


def test_gui44_locked_database_falls_back_and_writes_nothing(app, tmp_path):
    s, _sid = at_ready()
    request = make_state(tmp_path)
    store, j = open_journal(tmp_path)
    record_unlinked(j)
    store.close()
    before = events(tmp_path)
    holder = sqlite3.connect(db_path(tmp_path), isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        worker = JournalWorker(
            writable_opener=lambda db: Store.open(db, SystemClock(), busy_timeout_ms=200)
        )
        window = open_d03(app, s, request, worker, mode=JournalMode.READ_ONLY)
        try:
            assert "locked" in window.manual.snapshot.reason
            assert window.manual.snapshot.restored == ()
        finally:
            finish(app, window)
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    assert events(tmp_path) == before


def test_gui44_migration_needed_on_read_only_database_is_not_partially_migrated(app, tmp_path):
    s, _sid = at_ready()
    request = LoadRequest("syn", state_dir=str(tmp_path / "state"))
    old = available_migrations()[:2]
    Store.open(db_path(tmp_path), SystemClock(), old).close()
    db = db_path(tmp_path)
    os.chmod(db, 0o444)
    os.chmod(db.parent, 0o555)
    try:
        digest = db.read_bytes()
        window = GoldWindow(
            request,
            worker=ReplayWorker(loader=lambda _r: s, journal_reader=pending),
            journal_worker=JournalWorker(),
        )
        window.show()
        try:
            wait_until(app, lambda: window.manual.snapshot is not None, "journal snapshot")
            snap = window.manual.snapshot
            assert snap.mode in (JournalMode.READ_ONLY, JournalMode.UNAVAILABLE)
            assert "writable open failed" in snap.reason
            if snap.mode is JournalMode.UNAVAILABLE:
                assert snap.overlay() is None  # never an invented empty overlay
            wait_until(app, lambda: isinstance(window.frame, OverviewFrame), "frame")
        finally:
            finish(app, window)
        assert db.read_bytes() == digest
        assert sorted(p.name for p in db.parent.iterdir()) == [STATE_DB_FILENAME]  # no backup
    finally:
        os.chmod(db.parent, 0o755)
        os.chmod(db, 0o644)


def test_missing_database_is_unavailable_and_never_created(app, tmp_path):
    s, _sid = at_ready()
    request = LoadRequest("syn", state_dir=str(tmp_path / "nothing"))
    window = GoldWindow(
        request,
        worker=ReplayWorker(loader=lambda _r: s, journal_reader=pending),
        journal_worker=JournalWorker(),
    )
    window.show()
    try:
        wait_until(app, lambda: window.manual.snapshot is not None, "journal snapshot")
        assert window.manual.snapshot.mode is JournalMode.UNAVAILABLE
        assert window.manual.snapshot.overlay() is None
        wait_until(app, lambda: isinstance(window.frame, OverviewFrame)
                   and "unavailable" in window.frame.positions.journal_note.lower(),
                   "note pushed")  # fmt: skip
        assert not (tmp_path / "nothing").exists()
    finally:
        finish(app, window)


# --------------------------------------------------------------------------- threads / shutdown


def test_sqlite_only_on_journal_owner_thread_and_close_refused_while_saving(app, tmp_path):
    s, sid = at_ready()
    request = make_state(tmp_path)
    worker = JournalWorker()
    window = open_d03(app, s, request, worker)
    try:
        assert worker.owner_thread_name not in (None, threading.current_thread().name)
        assert worker.owner_thread_name != window.worker.owner_thread_name
        dialog = open_form(app, window, "skip", sid)
        window.close()  # refused while a form is open
        settle(app)
        assert window.isVisible() and "Close the open manual form" in window.notice.text()
        dialog.confirm_button.click()
        assert dialog.state == dialog.SAVING
        QTest.keyClick(dialog, Qt.Key.Key_Escape)  # Esc cannot abandon a save in flight
        window.close()
        settle(app)
        assert dialog.isVisible() and window.isVisible()
        wait_until(app, lambda: dialog.state == dialog.SAVED, "saved")
        close_dialog(app, window)
        n_open = window.manual.oversight_count()
        window.close()
        wait_until(app, lambda: not window._threads_running(), "threads stopped")
        assert f"{n_open} local open position(s) still need your external oversight" in (
            window.description.text()
        )
        assert decisions(tmp_path) == [(sid, "USER_SKIPPED")]
    finally:
        if window._threads_running():
            finish(app, window)


def test_journal_owner_finishes_a_queued_command_before_shutdown(app, tmp_path):
    """Graceful shutdown truthfulness: a command queued before shutdown is executed and
    its real result reported before the owner stops (queued order on its own thread)."""
    from PySide6.QtCore import QObject, Signal

    from grog.desktop.frames import signal_check
    from grog.desktop.manual_forms import skip_spec

    s, sid = at_ready()
    request = make_state(tmp_path)
    worker = JournalWorker()
    thread = QThread()
    worker.moveToThread(thread)
    got: list = []
    worker.snapshot.connect(lambda snap: got.append(("snapshot", snap.mode)))
    worker.result.connect(lambda res: got.append(("result", res.code)))
    worker.stopped.connect(lambda: got.append(("stopped", None)))

    class Driver(QObject):
        open = Signal(object, int)
        submit = Signal(object)
        stop = Signal()

    driver = Driver()
    driver.open.connect(worker.open)
    driver.submit.connect(worker.submit)
    driver.stop.connect(worker.shutdown)
    thread.start()
    try:
        driver.open.emit(request, 1)
        wait_until(app, lambda: got, "opened")
        chk = signal_check(s, token=1, source_id="syn", generation=1, signal_id=sid)
        spec = skip_spec(chk)
        cmd = spec.build(9, new_action_id(), spec.parse({"reason": ""}).values, chk)
        driver.submit.emit(cmd)
        driver.stop.emit()  # immediately after: still executes the command first
        wait_until(app, lambda: ("stopped", None) in got, "stopped")
        kinds = [k for k, _ in got]
        assert kinds.index("result") < kinds.index("stopped")
        assert ("result", "SAVED") in got
        late = []
        worker.result.connect(lambda res: late.append(res.code))
        driver.submit.emit(cmd)  # after shutdown: refused, never written
        wait_until(app, lambda: late, "late refusal")
        assert late == ["SHUTTING_DOWN"] and decisions(tmp_path) == [(sid, "USER_SKIPPED")]
    finally:
        thread.quit()
        thread.wait()


def test_gui50_journal_has_no_edit_correction_or_delete_controls(app, tmp_path):
    s, _sid = at_ready()
    window = open_d03(app, s, make_state(tmp_path))
    try:
        texts = [b.text().lower() for b in window.journal_page.findChildren(QPushButton)]
        texts += [b.text().lower() for b in window.positions_page.findChildren(QPushButton)]
        for word in ("edit", "delete", "correct", "remove", "undo"):
            assert not any(word in t for t in texts), (word, texts)
        assert all(not e.isReadOnly() for e in window.journal_page.findChildren(QLineEdit))
        assert "Corrections and deletions are not supported" in "\n".join(
            lbl.text() for lbl in window.journal_page.findChildren(type(window.notice))
        )
    finally:
        finish(app, window)


# --------------------------------------------------------------------------- audit fixes


@pytest.mark.parametrize("kind", ["entry", "skip"])
def test_uncertain_outcome_retry_reaches_service_idempotency_not_a_foreign_claim(
    app, tmp_path, kind
):
    """Audit defect 2: after a fault AFTER commit (OUTCOME UNKNOWN), retrying the same form
    was refused as 'already claimed' with an OFF_PLAN offer (a duplicate path). Now the
    same action ID goes to the service: a changed payload is rejected, the identical one
    is confirmed as already saved; one row and one claim."""
    s, sid = at_ready()
    request = make_state(tmp_path)
    method = "record_entry" if kind == "entry" else "record_skip"
    armed = {"on": True}

    def configure(journal):
        real = getattr(journal, method)

        def commit_then_fail(*a, **kw):
            out = real(*a, **kw)
            if armed["on"]:
                armed["on"] = False
                raise sqlite3.OperationalError("disk I/O error after commit")
            return out

        setattr(journal, method, commit_then_fail)

    window = open_d03(app, s, request, journal_worker=JournalWorker(configure=configure))
    rows = (lambda: events(tmp_path)) if kind == "entry" else (lambda: decisions(tmp_path))
    try:
        dialog = open_form(app, window, kind, sid)
        action_id = dialog.action_id
        if kind == "entry":
            plan = dialog.spec.opened.plan
            fill(dialog, price=str(plan.e0), qty="0.10", fees="0")
            changed = {"qty": "0.20"}
            original = {"qty": "0.10"}
        else:
            fill(dialog, reason="not for me")
            changed = {"reason": "edited later"}
            original = {"reason": "not for me"}
        first = confirm_and_wait(app, window, dialog)
        assert first is not None and first.code == "OUTCOME_UNKNOWN" and not first.saved
        assert len(rows()) == 1  # it was in fact committed
        assert len(window.manual.snapshot.claims) == 1
        fill(dialog, **changed)  # same action ID, different payload: must be rejected
        res = confirm_and_wait(app, window, dialog)
        assert res is not None and not res.saved and res.code == "DUPLICATE_ACTION_ID"
        assert not dialog.off_plan_button.isVisible() and len(rows()) == 1
        fill(dialog, **original)  # exact retry of the uncertain record
        res = confirm_and_wait(app, window, dialog)
        assert res is not None and res.saved and not res.created, res.message
        assert res.action_id == action_id and "already saved earlier" in res.message
        assert not dialog.off_plan_button.isVisible()
        assert len(rows()) == 1 and len(window.manual.snapshot.claims) == 1
    finally:
        finish(app, window)


def test_confirm_open_before_fill_is_refused_on_save_even_if_the_button_is_bypassed(app, tmp_path):
    """Audit defect 1 at the controller: Save re-runs the structured rules on the fresh
    values, independent of the Confirm button state."""
    s, _sid = at_ready()
    request = make_state(tmp_path)
    store, j = open_journal(tmp_path)
    pos = record_unlinked(j)
    store.close()
    window = open_d03(app, s, request)  # this start marks it RECONCILIATION_REQUIRED
    try:
        assert window.manual.snapshot.restored == (pos.position_id,)
        before = events(tmp_path)
        window.show_page(2)
        window._on_action_requested("confirm", pos.position_id)
        wait_until(app, lambda: window.manual.dialog is not None, "confirm form")
        d = window.manual.dialog
        fill(d, time=iso_utc(pos.entry_ms - 1000), ack="yes")
        settle(app)
        assert not d.confirm_button.isEnabled()
        assert "REJECTED TIME_BEFORE_ENTRY" in d.preview.text()
        n = len(window.manual.results)
        window.manual._save(d)  # bypass the disabled button
        wait_until(app, lambda: "TIME_BEFORE_ENTRY" in d.outcome.text(), "refusal")
        assert "NOT SAVED" in d.outcome.text() and events(tmp_path) == before
        settle(app)
        assert len(window.manual.results) == n  # refused at Save, never sent to the owner
        fill(d, time=iso_utc(pos.entry_ms))
        assert confirm_and_wait(app, window, d).saved
        assert events(tmp_path)[-1][2] == "CONFIRMED_OPEN"
    finally:
        finish(app, window)
