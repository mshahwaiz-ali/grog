"""The single replay owner: one QObject living on a dedicated QThread.

It loads the source (including the causal pre-roll), owns the ``ReplaySession`` and its
``TouchTracker``, processes every quote in order and publishes detached immutable frames.
Qt widgets are never touched here; the GUI talks to it only through queued signals.
Painting is coalesced (at most ``MAX_FRAMES_PER_S`` playback frames per second); engine
processing is not: ``ReplaySession.advance`` processes every due quote exactly once.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from grog.desktop.frames import (
    REPLAY_LABELS,
    FrameTag,
    PauseAck,
    Phase,
    StatusFrame,
    build_overview_frame,
)
from grog.desktop.loading import LoadRequest, describe_failure, load_session, read_journal
from grog.desktop.presentation import utc_ms_text
from grog.journal.positions import TouchTracker
from grog.replay.session import Playback

if TYPE_CHECKING:
    from grog.replay.session import ReplaySession

MAX_FRAMES_PER_S = 4
FRAME_INTERVAL_S = 1 / MAX_FRAMES_PER_S
TICK_MS = 20
MAX_TICK_ELAPSED_S = 0.5  # same cap as the previous GUI-thread timer

Loader = Callable[[LoadRequest], "ReplaySession"]
JournalReader = Callable[[LoadRequest], tuple]


class ReplayWorker(QObject):
    """Owns one source generation at a time. All slots run on the worker thread."""

    frame = Signal(object)  # OverviewFrame | StatusFrame
    pause_acknowledged = Signal(object)  # PauseAck
    stopped = Signal()

    def __init__(
        self,
        loader: Loader = load_session,
        journal_reader: JournalReader = read_journal,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__()
        self._loader = loader
        self._journal_reader = journal_reader
        self._clock = clock
        self._session: ReplaySession | None = None
        self._tracker: TouchTracker | None = None
        self._overlay = None
        self._positions = None
        self._journal_note = ""
        self._request: LoadRequest | None = None
        self._source_id = ""
        self._generation = 0
        self._sequence = 0
        self._timer: QTimer | None = None
        self._last_tick = 0.0
        self._last_frame = 0.0
        self._faulted = False
        self.owner_thread_name: str | None = None  # test evidence only

    # ------------------------------------------------------------------ helpers

    def _tag(self) -> FrameTag:
        self._sequence += 1
        return FrameTag(self._source_id, self._generation, self._sequence)

    def _ensure_timer(self) -> QTimer:
        if self._timer is None:  # created lazily so it belongs to the worker thread
            self._timer = QTimer(self)
            self._timer.setInterval(TICK_MS)
            self._timer.timeout.connect(self._tick)
        return self._timer

    def _publish(self) -> None:
        session, tracker = self._session, self._tracker
        if session is None or tracker is None or self._faulted:
            return
        try:
            frame = build_overview_frame(
                session,
                tag=self._tag(),
                overlay=self._overlay,
                positions=self._positions,
                tracker=tracker,
                journal_note=self._journal_note,
            )
        except Exception as exc:  # noqa: BLE001 - surface any presenter fault, stop safely
            self._fault(exc)
            return
        self._last_frame = self._clock()
        self.frame.emit(frame)

    def _fault(self, exc: BaseException, *, startup: bool = False) -> None:
        self._faulted = True
        if self._timer is not None:
            self._timer.stop()
        code, message = describe_failure(exc, self._source_id)
        last = None
        if self._session is not None and self._session.cursor > 0:
            last = utc_ms_text(self._session.quotes[self._session.cursor - 1].received_time_ms)
        self.frame.emit(
            StatusFrame(
                tag=self._tag(),
                labels=REPLAY_LABELS,
                phase=Phase.FAULT,
                title="Source could not be loaded" if startup else "Replay stopped — STALE",
                detail=message,
                exit_code=code if startup else None,
                last_virtual_utc=last,
            )
        )

    # ------------------------------------------------------------------ slots

    @Slot(object, int)
    def load(self, request: LoadRequest, generation: int) -> None:
        """Start a new source generation; frames of earlier generations become obsolete."""
        import threading

        self.owner_thread_name = threading.current_thread().name
        if self._timer is not None:
            self._timer.stop()
        self._session = None
        self._tracker = None
        self._faulted = False
        self._source_id = request.source_id
        self._generation = generation
        self._sequence = 0
        self.frame.emit(
            StatusFrame(
                tag=self._tag(),
                labels=REPLAY_LABELS,
                phase=Phase.LOADING,
                title="Loading source — preparing confirmed history",
                detail=(
                    f"Verifying stored batches of {request.source_id!r} and replaying the "
                    "causal pre-roll. Quote counts appear when loading completes."
                ),
            )
        )
        try:  # the whole initialisation: source, journal read and tracker wiring
            session = self._loader(request)
            overlay, positions, note = self._journal_reader(request)
            self._request = request
            tracker = TouchTracker()
            if positions is not None:
                tracker.track(positions)
            # Same order as the Textual app: the tracker observes quotes after pre-roll.
            session.quote_observers.append(tracker.on_quote)
        except Exception as exc:  # noqa: BLE001 - every failure is reported, none hidden
            self._fault(exc, startup=True)
            return
        self._session, self._tracker = session, tracker
        self._overlay, self._positions, self._journal_note = overlay, positions, note
        self._publish()

    @Slot(int)
    def toggle_play(self, generation: int) -> None:
        if generation != self._generation:
            return  # an intent issued for an earlier source generation
        s = self._session
        if s is None or self._faulted or s.playback is Playback.ENDED:
            return
        if s.toggle_play() is Playback.PLAYING:
            self._last_tick = self._clock()
            self._ensure_timer().start()
        elif self._timer is not None:
            self._timer.stop()
        self._publish()

    @Slot(int, int)
    def request_pause(self, token: int, generation: int) -> None:
        """Pause (if playing) and acknowledge with the exact cursor/source/generation."""
        s = self._session
        if s is None or generation != self._generation:
            return
        if s.playback is Playback.PLAYING:
            s.toggle_play()
        if self._timer is not None:
            self._timer.stop()
        self._publish()
        self.pause_acknowledged.emit(
            PauseAck(token, self._source_id, self._generation, s.cursor, s.playback)
        )

    @Slot(int)
    def step(self, generation: int) -> None:
        if generation != self._generation:
            return  # an intent issued for an earlier source generation
        s = self._session
        if s is None or self._faulted:
            return
        try:
            stepped = s.step()  # exactly one normalized quote, only while PAUSED
        except Exception as exc:  # noqa: BLE001
            self._fault(exc)
            return
        if stepped:
            self._publish()

    @Slot(int)
    def faster(self, generation: int) -> None:
        if generation != self._generation:
            return  # an intent issued for an earlier source generation
        if self._session is not None and not self._faulted:
            self._session.faster()
            self._publish()

    @Slot(int)
    def slower(self, generation: int) -> None:
        if generation != self._generation:
            return  # an intent issued for an earlier source generation
        if self._session is not None and not self._faulted:
            self._session.slower()
            self._publish()

    @Slot()
    def refresh(self) -> None:
        """Re-read the operator overlay read-only (as the terminal's refresh does) and
        republish the current snapshot; the replay itself never moves."""
        if self._session is None or self._faulted:
            return
        try:
            overlay, positions, note = self._journal_reader(self._request)
        except Exception as exc:  # noqa: BLE001 - fail closed, never an invented empty overlay
            overlay, positions = None, None
            note = f"Journal unavailable (refresh failed: {exc})"
        self._overlay, self._positions, self._journal_note = overlay, positions, note
        if self._tracker is not None and positions is not None:
            self._tracker.track(positions)
        self._publish()

    @Slot()
    def shutdown(self) -> None:
        self._faulted = True  # accept no further work; references are released with the worker
        if self._timer is not None:
            self._timer.stop()
        self.stopped.emit()

    def _tick(self) -> None:
        s = self._session
        if s is None or self._faulted or s.playback is not Playback.PLAYING:
            if self._timer is not None:
                self._timer.stop()
            return
        now = self._clock()
        elapsed = min(max(now - self._last_tick, 0.0), MAX_TICK_ELAPSED_S)
        self._last_tick = now
        try:
            s.advance(elapsed)
        except Exception as exc:  # noqa: BLE001
            self._fault(exc)
            return
        if s.playback is Playback.ENDED:
            self._timer.stop()
            self._publish()  # a state transition is always shown
        elif now - self._last_frame >= FRAME_INTERVAL_S:
            self._publish()
