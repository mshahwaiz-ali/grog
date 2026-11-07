"""D01 robustness: nonblocking close, whole-load fault handling, source/generation guards."""

from __future__ import annotations

import threading
import time

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QThread, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from grog.desktop.frames import OverviewFrame, Phase, StatusFrame  # noqa: E402
from grog.desktop.loading import LoadRequest, read_journal  # noqa: E402
from grog.desktop.replay_worker import ReplayWorker  # noqa: E402
from grog.desktop.window import GoldWindow  # noqa: E402
from ui_support import open_journal, session  # noqa: E402

TIMEOUT_S = 20.0


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


def finish(app, window: GoldWindow) -> None:
    """Close and let the owner thread finish while the GUI loop keeps running."""
    window.close()
    wait_until(app, window.thread.isFinished, "owner thread to finish")
    app.processEvents()


def no_journal(_request):
    return {}, [], "Read-only test journal (empty)"


def test_close_during_slow_load_keeps_gui_responsive_and_exits_cleanly(app) -> None:
    gate = threading.Event()
    beats_during_close: list[int] = []
    closing = [False]

    def loader(_request):
        assert gate.wait(TIMEOUT_S), "gate never released"
        return session()

    def beat():
        if closing[0]:
            beats_during_close.append(1)
            if len(beats_during_close) >= 5:
                gate.set()  # the load can only finish if the GUI loop is still running

    heartbeat = QTimer()
    heartbeat.timeout.connect(beat)
    heartbeat.start(5)
    fallback = threading.Timer(3.0, gate.set)  # avoid a deadlock if close blocks the GUI
    fallback.start()
    window = GoldWindow(
        LoadRequest("syn"), worker=ReplayWorker(loader=loader, journal_reader=no_journal)
    )
    window.show()
    try:
        wait_until(app, lambda: isinstance(window.frame, StatusFrame), "loading frame")
        closing[0] = True
        started = time.monotonic()
        window.close()
        returned_after = time.monotonic() - started
        wait_until(app, window.thread.isFinished, "owner thread to finish")
        app.processEvents()
        assert returned_after < 1.0, f"close() blocked the GUI for {returned_after:.2f}s"
        assert len(beats_during_close) >= 5
        assert not window.isVisible()
        assert not window.play.isEnabled() and not window.step.isEnabled()
    finally:
        heartbeat.stop()
        fallback.cancel()
        gate.set()
        if not window.thread.isFinished():
            window.thread.wait()


def test_journal_reader_failure_is_a_controlled_startup_fault(app, tmp_path) -> None:
    store, _journal = open_journal(tmp_path)
    store.close()
    db = tmp_path / "state" / "state.sqlite3"
    before = db.read_bytes()

    def failing_reader(request):
        read_journal(LoadRequest("syn", state_dir=str(tmp_path / "state")))
        raise RuntimeError("unexpected projection failure")

    failures: list[tuple[int, str]] = []
    window = GoldWindow(
        LoadRequest("syn"),
        worker=ReplayWorker(loader=lambda _r: session(), journal_reader=failing_reader),
        on_startup_failure=lambda code, message: failures.append((code, message)),
    )
    window.show()
    try:
        wait_until(
            app,
            lambda: isinstance(window.frame, StatusFrame) and window.frame.phase is Phase.FAULT,
            "startup fault",
        )
        assert failures and failures[0][0] == 3
        assert "unexpected projection failure" in failures[0][1]
        assert not window.play.isEnabled()
    finally:
        finish(app, window)
    assert db.read_bytes() == before


def test_reload_ignores_controls_from_the_previous_source(app) -> None:
    gate = threading.Event()
    sessions = []

    def loader(request):
        if request.source_id == "second":
            assert gate.wait(TIMEOUT_S)
        sessions.append(session())
        return sessions[-1]

    window = GoldWindow(
        LoadRequest("first"), worker=ReplayWorker(loader=loader, journal_reader=no_journal)
    )
    window.show()
    try:
        wait_until(app, lambda: isinstance(window.frame, OverviewFrame), "first source")
        generation = window.load_source(LoadRequest("second"))
        assert not window.step.isEnabled() and not window.play.isEnabled()
        window.step_once()  # an intent issued while the new source is still loading
        window.toggle_play()
        gate.set()
        wait_until(
            app,
            lambda: (
                isinstance(window.frame, OverviewFrame)
                and window.frame.tag.generation == generation
            ),
            "second source",
        )
        app.processEvents()
        frame = window.frame
        assert frame.tag.source_id == "second"
        assert frame.transport.processed == sessions[1].pre_roll_quotes  # no stray step
        assert frame.transport.playback.value == "PAUSED"
    finally:
        finish(app, window)


def test_frame_with_current_generation_but_wrong_source_is_rejected(app) -> None:
    window = GoldWindow(
        LoadRequest("syn"),
        worker=ReplayWorker(loader=lambda _r: session(), journal_reader=no_journal),
    )
    window.show()
    try:
        wait_until(app, lambda: isinstance(window.frame, OverviewFrame), "frame")
        good = window.frame
        import dataclasses

        forged = dataclasses.replace(
            good, tag=dataclasses.replace(good.tag, source_id="other", sequence=10**9)
        )
        dropped = window.dropped_stale
        window._on_frame(forged)
        app.processEvents()
        assert window.dropped_stale == dropped + 1
        assert window.frame.tag.source_id == "syn"
    finally:
        finish(app, window)


@pytest.mark.parametrize("size", [(820, 620), (1366, 768), (1920, 1080)])
def test_toolbar_keeps_controls_and_safety_text_unclipped(app, size) -> None:
    window = GoldWindow(
        LoadRequest("syn"),
        worker=ReplayWorker(loader=lambda _r: session(), journal_reader=no_journal),
    )
    window.show()
    try:
        wait_until(app, lambda: isinstance(window.frame, OverviewFrame), "frame")
        window.resize(*size)
        wait_until(app, lambda: window.width() == size[0], "resize")
        for _ in range(5):
            app.processEvents()
        bar = window.toolbar
        for widget in (
            window.play,
            window.step,
            window.slower,
            window.faster,
            window.refresh_button,
            window.toolbar_safety,
        ):
            assert widget.isVisibleTo(window)
            rect = widget.geometry()
            top_left = widget.mapTo(bar, rect.topLeft() - rect.topLeft())
            assert top_left.x() >= 0 and top_left.x() + widget.width() <= bar.width(), widget
            assert widget.width() >= widget.sizeHint().width(), widget  # text not truncated
        assert window.toolbar_safety.text() == "No broker orders"
        if size[0] < 1100:  # auxiliary progress moves to its own wrapped row
            assert window.progress.mapTo(bar, window.progress.rect().topLeft()).y() > (
                window.play.mapTo(bar, window.play.rect().topLeft()).y()
            )
    finally:
        finish(app, window)


def test_later_pages_are_explained_without_relying_on_disabled_tooltips(app) -> None:
    window = GoldWindow(
        LoadRequest("syn"),
        worker=ReplayWorker(loader=lambda _r: session(), journal_reader=no_journal),
    )
    window.show()
    try:
        wait_until(app, lambda: isinstance(window.frame, OverviewFrame), "frame")
        assert window.later_note.isVisibleTo(window)
        assert "available in later phases" in window.later_note.text()
        assert [b.isEnabled() for b in window.nav] == [True, True, False, False, False]
    finally:
        finish(app, window)


def test_refresh_republishes_without_moving_replay_and_says_so(app) -> None:
    sessions = []

    def loader(_r):
        sessions.append(session())
        return sessions[-1]

    window = GoldWindow(
        LoadRequest("syn"), worker=ReplayWorker(loader=loader, journal_reader=no_journal)
    )
    window.show()
    try:
        wait_until(app, lambda: isinstance(window.frame, OverviewFrame), "frame")
        before = window.frame
        window.refresh()
        wait_until(app, lambda: window.frame.tag.sequence > before.tag.sequence, "refresh")
        after = window.frame
        assert after.transport.processed == before.transport.processed == sessions[0].cursor
        assert after.overview == before.overview and after.quote == before.quote
        assert window.notice.isVisibleTo(window)
        assert "View refreshed" in window.notice.text()
        assert f"{after.transport.processed:,} quotes" in window.notice.text()
    finally:
        finish(app, window)


def test_ready_signal_full_id_is_visible_in_the_decision_card(app) -> None:
    from grog.domain.enums import SignalEventKind
    from ui_support import step_until

    ids = []

    def loader(_r):
        s = session()
        ids.append(step_until(s, SignalEventKind.READY_ISSUED))
        return s

    window = GoldWindow(
        LoadRequest("syn"), worker=ReplayWorker(loader=loader, journal_reader=no_journal)
    )
    window.show()
    try:
        wait_until(app, lambda: isinstance(window.frame, OverviewFrame), "frame")
        assert window.frame.ready_ids == (ids[0],)
        assert window.signal_ids.isVisibleTo(window)
        assert f"READY signal ID  {ids[0]}" in window.signal_ids.text()
        caption = window.m5.caption.text()
        assert "Last confirmed M5 bar closed" in caption and " UTC" in caption
        assert caption.split("available ")[1] == window.frame.diagnostics.bars[2][3]
    finally:
        finish(app, window)


def test_window_lists_every_ready_and_blocked_id_from_a_real_engine_frame(app, tmp_path) -> None:
    """GUI-21 on screen: two READY + one blocked real engine signals, none ranked or hidden."""
    from desktop_gate_support import captured_views, composite
    from grog.desktop.frames import FrameTag, build_overview_frame
    from grog.journal.positions import TouchTracker

    s, ready, blocked, live = captured_views()
    ids = list(ready)
    views = (ready[ids[0]], blocked[ids[1]], ready[ids[2]])
    window = GoldWindow(
        LoadRequest("syn"),
        worker=ReplayWorker(loader=lambda _r: session(), journal_reader=no_journal),
    )
    window.show()
    try:
        wait_until(app, lambda: isinstance(window.frame, OverviewFrame), "frame")
        current = window.frame.tag
        frame = build_overview_frame(
            composite(s, views, snap=live),
            tag=FrameTag("syn", current.generation, current.sequence + 10**6),
            overlay={},
            positions=[],
            tracker=TouchTracker(),
            journal_note="test journal",
        )
        window._on_frame(frame)
        wait_until(app, lambda: window.frame is frame, "composite frame applied")
        text = window.signal_ids.text()
        assert window.signal_ids.isVisibleTo(window)
        assert f"READY signal ID  {ids[0]}" in text and f"READY signal ID  {ids[2]}" in text
        assert f"Execution-blocked signal ID  {ids[1]}" in text
        assert text.index(ids[0]) < text.index(ids[2])  # engine order, no ranking
        assert window.headline.text() == "2 simulated proposals ready"
    finally:
        finish(app, window)
