"""D01 replay-owner threading and Overview shell tests (GUI-08, GUI-15..22, GUI-09 layout).

Offscreen Qt; synchronisation waits on observable conditions while the Qt event loop runs
(no fixed sleeps as synchronisation). All data is synthetic; journals live in tmp dirs.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QThread, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from grog.desktop.frames import OverviewFrame, Phase, StatusFrame, assert_detached  # noqa: E402
from grog.desktop.loading import LoadRequest, read_journal  # noqa: E402
from grog.desktop.overview_model import from_snapshot  # noqa: E402
from grog.desktop.replay_worker import ReplayWorker  # noqa: E402
from grog.desktop.window import GoldWindow  # noqa: E402
from grog.journal.positions import TouchTracker  # noqa: E402
from grog.replay.session import Playback  # noqa: E402
from ui_support import open_journal, record_unlinked, session  # noqa: E402

TIMEOUT_S = 60.0


@pytest.fixture(scope="module")
def app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication(["gold-desktop-test"])


def wait_until(app, predicate: Callable[[], bool], what: str) -> None:
    deadline = time.monotonic() + TIMEOUT_S
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        app.processEvents()
        QThread.msleep(1)


def close_and_join(app, window: GoldWindow) -> None:
    """Closing is asynchronous: the GUI loop keeps running until the owner thread stops."""
    window.close()
    wait_until(app, window.thread.isFinished, "owner thread to stop")
    app.processEvents()


class Harness:
    """Records worker-side evidence: which thread loaded and the sessions it built."""

    def __init__(self, gate: threading.Event | None = None, **kw) -> None:
        self.gate = gate
        self.kw = kw
        self.sessions = []
        self.load_threads = []

    def loader(self, request: LoadRequest):
        self.load_threads.append(threading.current_thread())
        if self.gate is not None and request.source_id == "gated":
            assert self.gate.wait(TIMEOUT_S), "loader gate never released"
        s = session(**self.kw)
        self.sessions.append(s)
        return s


def no_journal(_request):
    return {}, [], "Read-only test journal (empty)"


def make_window(app, harness: Harness, journal=no_journal, source="syn") -> GoldWindow:
    worker = ReplayWorker(loader=harness.loader, journal_reader=journal)
    window = GoldWindow(LoadRequest(source), worker=worker)
    window.show()
    return window


def engine_frame(window: GoldWindow) -> OverviewFrame:
    assert isinstance(window.frame, OverviewFrame), window.frame
    return window.frame


def wait_frame(app, window: GoldWindow, predicate=lambda f: True, what="engine frame"):
    wait_until(
        app,
        lambda: isinstance(window.frame, OverviewFrame) and predicate(window.frame),
        what,
    )
    return window.frame


def test_load_and_preroll_run_on_owner_thread_while_gui_stays_responsive(app) -> None:
    gate = threading.Event()
    beats: list[float] = []
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: (beats.append(1), len(beats) >= 5 and gate.set()))
    heartbeat.start(5)
    harness = Harness(gate=gate)
    worker = ReplayWorker(loader=harness.loader, journal_reader=no_journal)
    window = GoldWindow(LoadRequest("gated"), worker=worker)
    try:
        # The loader cannot finish until the GUI thread has run its own timer 5 times.
        wait_until(app, lambda: isinstance(window.frame, StatusFrame), "loading frame")
        assert window.frame.phase is Phase.LOADING
        assert not window.play.isEnabled() and not window.step.isEnabled()
        frame = wait_frame(app, window)
        assert len(beats) >= 5
        assert harness.load_threads[0] is not threading.main_thread()
        assert worker.owner_thread_name == harness.load_threads[0].name
        assert frame.transport.pre_roll == harness.sessions[0].pre_roll_quotes > 0
        assert frame.transport.playback is Playback.PAUSED  # starts paused at the cursor
    finally:
        heartbeat.stop()
        close_and_join(app, window)


def test_frames_are_detached_applied_on_gui_thread_and_match_engine(app, monkeypatch) -> None:
    painted_on: list[bool] = []
    original = GoldWindow._apply_overview

    def spy(self, frame):
        painted_on.append(QThread.currentThread() is app.thread())
        original(self, frame)

    monkeypatch.setattr(GoldWindow, "_apply_overview", spy)
    harness = Harness()
    window = make_window(app, harness)
    try:
        frame = wait_frame(app, window)
        assert_detached(frame)
        assert painted_on and all(painted_on)
        direct = session()  # same deterministic source, built independently
        snap = direct.snapshot()
        assert frame.overview == from_snapshot(
            snap, direct.pipeline.signals.events, {}, open_positions=0
        )
        assert frame.quote.bid == snap.quote.bid and frame.quote.ask == snap.quote.ask
        assert frame.quote.received_ms == snap.quote.received_time_ms
        assert window.bid.value.text() == format(snap.quote.bid, ",f")
        assert window.fidelity_pill.text() == "SIMULATED" and window.mode_pill.text() == "REPLAY"
        assert window.playback_pill.text() != window.health_pill.text()
        assert window.toolbar.isVisibleTo(window)
    finally:
        close_and_join(app, window)


def test_step_processes_exactly_one_quote(app) -> None:
    harness = Harness()
    window = make_window(app, harness)
    try:
        first = wait_frame(app, window)
        cursor = first.transport.processed
        window.step_once()
        frame = wait_frame(app, window, lambda f: f.tag.sequence > first.tag.sequence, "step")
        s = harness.sessions[0]
        assert frame.transport.processed == cursor + 1
        assert frame.quote.received_ms == s.quotes[cursor].received_time_ms
        assert frame.quote.bid == s.quotes[cursor].bid
    finally:
        close_and_join(app, window)


def test_pause_handshake_acknowledges_exact_cursor_and_stops_processing(app) -> None:
    harness = Harness()
    window = make_window(app, harness)
    try:
        first = wait_frame(app, window)
        window.toggle_play()  # 50 events/s
        wait_frame(
            app,
            window,
            lambda f: f.transport.processed > first.transport.processed,
            "playback progress",
        )
        acks = []
        token = window.request_pause(acks.append)
        assert not window.play.isEnabled() and not window.step.isEnabled()
        wait_until(app, lambda: bool(acks), "pause acknowledgement")
        ack = acks[0]
        assert ack.token == token and ack.playback is Playback.PAUSED
        assert ack.source_id == "syn" and ack.generation == 1
        frame = engine_frame(window)  # the paused frame is painted before the callback
        assert frame.transport.processed == ack.cursor
        assert frame.transport.playback is Playback.PAUSED
        assert window.play.isEnabled() and window.step.isEnabled()
        seq = frame.tag.sequence
        window.refresh_requested.emit()
        later = wait_frame(app, window, lambda f: f.tag.sequence > seq, "refresh")
        assert later.transport.processed == ack.cursor == harness.sessions[0].cursor
    finally:
        close_and_join(app, window)


def test_pace_steps_through_50_500_fast_and_back(app) -> None:
    harness = Harness()
    window = make_window(app, harness)
    try:
        wait_frame(app, window)
        seen = []
        for action in ("faster", "faster", "faster", "slower", "slower", "slower"):
            seq = engine_frame(window).tag.sequence
            getattr(window, f"{action}_requested").emit()
            seen.append(
                wait_frame(
                    app, window, lambda f, s=seq: f.tag.sequence > s, action
                ).transport.pace_text
            )
        assert seen == ["500 ev/s", "FAST", "FAST", "500 ev/s", "50 ev/s", "50 ev/s"]
    finally:
        close_and_join(app, window)


def test_fast_replay_under_slow_painting_never_drops_engine_events(
    app, tmp_path, monkeypatch
) -> None:
    store, journal = open_journal(tmp_path)
    try:
        position = record_unlinked(journal)
    finally:
        store.close()
    request_state = str(tmp_path / "state")

    def journal_reader(_request):
        return read_journal(LoadRequest("syn", state_dir=request_state))

    original = GoldWindow._apply_overview

    def slow_paint(self, frame):
        time.sleep(0.15)  # simulated expensive render; not used for synchronisation
        original(self, frame)

    monkeypatch.setattr(GoldWindow, "_apply_overview", slow_paint)
    harness = Harness()
    window = make_window(app, harness, journal=journal_reader)
    try:
        wait_frame(app, window)
        window.faster_requested.emit()
        window.faster_requested.emit()
        wait_frame(app, window, lambda f: f.transport.pace_text == "FAST", "FAST pace")
        window.toggle_play()
        end = wait_frame(app, window, lambda f: f.transport.playback is Playback.ENDED, "end")
    finally:
        close_and_join(app, window)
    assert window.thread.isFinished()
    replayed = harness.sessions[0]
    tracker = window.worker._tracker  # read after the owner thread has been joined

    direct = session()
    direct_tracker = TouchTracker()
    direct_tracker.track([position])
    direct.quote_observers.append(direct_tracker.on_quote)
    while direct.step():
        pass
    assert end.transport.processed == end.transport.total == len(direct.quotes)
    assert replayed.pipeline.signals.events == direct.pipeline.signals.events
    assert replayed.pipeline.detector.events == direct.pipeline.detector.events
    assert tuple(replayed.feed) == tuple(direct.feed)
    assert tracker.touches == direct_tracker.touches
    assert window.frames_applied <= window.frames_received
    assert end.positions.open_count == 1 and end.positions.journal_ok
    assert end.banner is not None and "REPLAY ENDED" in end.banner
    assert not window.play.isEnabled() and not window.step.isEnabled()
    assert not window.faster.isEnabled() and not window.slower.isEnabled()


def test_new_source_generation_discards_frames_from_the_old_one(app) -> None:
    gate = threading.Event()
    harness = Harness(gate=gate)
    worker = ReplayWorker(loader=harness.loader, journal_reader=no_journal)
    window = GoldWindow(LoadRequest("gated"), worker=worker)
    try:
        wait_until(app, lambda: isinstance(window.frame, StatusFrame), "loading")
        generation = window.load_source(LoadRequest("second"))  # queued behind the slow load
        gate.set()
        frame = wait_frame(app, window, lambda f: f.tag.generation == generation, "gen 2")
        assert frame.tag.source_id == "second" and generation == 2
        assert window.dropped_stale >= 1  # the finished first-generation frame was ignored
        assert len(harness.sessions) == 2
    finally:
        close_and_join(app, window)


def test_worker_fault_stops_safely_with_stale_state(app) -> None:
    harness = Harness()
    window = make_window(app, harness)
    try:
        wait_frame(app, window)

        def broken_step():
            raise RuntimeError("synthetic engine fault")

        harness.sessions[0].step = broken_step
        window.step_once()
        wait_until(
            app,
            lambda: isinstance(window.frame, StatusFrame) and window.frame.phase is Phase.FAULT,
            "fault frame",
        )
        assert "STALE" in window.frame.title and window.frame.last_virtual_utc
        assert "synthetic engine fault" in window.frame.detail
        assert window.banner.isVisibleTo(window)
        assert not window.play.isEnabled() and not window.step.isEnabled()
    finally:
        close_and_join(app, window)
    assert window.thread.isFinished()


def test_close_while_playing_joins_owner_thread(app) -> None:
    harness = Harness()
    window = make_window(app, harness)
    wait_frame(app, window)
    window.toggle_play()
    wait_frame(app, window, lambda f: f.transport.playback is Playback.PLAYING, "playing")
    close_and_join(app, window)
    assert window.thread.isFinished()
    received = window.frames_received
    app.processEvents()
    assert window.frames_received == received


@pytest.mark.parametrize(
    ("size", "mode"),
    [((820, 620), "narrow"), ((1366, 768), "medium"), ((1920, 1080), "wide")],
)
def test_layout_adapts_without_horizontal_clipping(app, size, mode) -> None:
    harness = Harness()
    window = make_window(app, harness)
    try:
        wait_frame(app, window)
        window.resize(*size)
        wait_until(app, lambda: window.layout_mode == mode, f"{mode} layout")
        app.processEvents()
        assert window.width() == size[0] and window.height() == size[1]
        page = window.scroll.widget()
        assert page.minimumSizeHint().width() <= window.scroll.viewport().width()
        assert window.toolbar.isVisibleTo(window)
    finally:
        close_and_join(app, window)
