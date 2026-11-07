"""GUI-05 / GUI-17 / GUI-62 (D05): the Textual R0 app and the Qt desktop replay the SAME
stored source to the end with identical results.

Both frontends load one disposable imported state through their real entry paths (Textual:
``build_ui_session`` + ``GrogApp`` with its own play timer at FAST; desktop: ``GoldWindow``
with the default ``ReplayWorker`` / ``load_session`` on its owner thread). Compared after
REPLAY ENDED: every normalized quote, every S1 detector event and every signal event in
order (``repr`` keeps exact Decimal scale and UTC milliseconds), final signal statuses,
causal (non-decreasing virtual time) ordering, and the manual-position touch observations.
Only pacing/paint counts may differ. Synthetic data, explicit fixture config, no network.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import time
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QThread  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from grog.cli import build_ui_session  # noqa: E402
from grog.cli import main as grog  # noqa: E402
from grog.desktop.frames import OverviewFrame  # noqa: E402
from grog.desktop.loading import LoadRequest  # noqa: E402
from grog.desktop.window import GoldWindow  # noqa: E402
from grog.replay import synthetic  # noqa: E402
from grog.replay.session import Playback  # noqa: E402
from grog.ui.app import GrogApp  # noqa: E402
from ui_support import open_journal, record_unlinked  # noqa: E402

CONFIG = str(Path(__file__).resolve().parents[2] / "config" / "synthetic-demo.fixture-only.toml")
TIMEOUT_S = 120.0


@pytest.fixture(scope="module")
def app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication(["gold-desktop-test"])


@pytest.fixture
def state(tmp_path: Path, isolated_env: dict[str, str]) -> Path:
    csv = tmp_path / "syn.csv"
    csv.write_bytes(synthetic.generate_csv(days=20))
    state_dir = tmp_path / "state"
    argv = ["import-ticks", "--file", str(csv), "--source-id", "syn", "--origin", "SYNTHETIC"]
    argv += ["--state-dir", str(state_dir)]
    assert grog(argv, env=isolated_env, stdout=io.StringIO(), stderr=io.StringIO()) == 0
    store, journal = open_journal(tmp_path)  # one manual position, so touches are compared
    try:
        record_unlinked(journal)
    finally:
        store.close()
    return state_dir


def _textual(state: Path, env: dict[str, str]):
    from grog.domain.clock import SystemClock
    from grog.journal.positions import PositionJournal
    from grog.journal.store import STATE_DB_FILENAME, Store

    args = argparse.Namespace(source_id="syn", config=CONFIG, state_dir=str(state), from_ts=None)
    session = build_ui_session(args, env)
    store = Store.open(state / STATE_DB_FILENAME, SystemClock())
    tui = GrogApp(session, PositionJournal(store))

    async def drive() -> None:
        async with tui.run_test(size=(160, 48)) as pilot:
            await pilot.press("plus", "plus", "space")  # FAST, then play on the app's own timer
            deadline = time.monotonic() + TIMEOUT_S
            while session.playback is not Playback.ENDED:
                assert time.monotonic() < deadline, "Textual replay did not end"
                await pilot.pause(0.05)

    try:
        asyncio.run(drive())
    finally:
        store.close()
    return session, tui.tracker


def _desktop(app, state: Path):
    window = GoldWindow(LoadRequest("syn", config=CONFIG, state_dir=str(state)))
    window.show()

    def wait(pred, what):
        deadline = time.monotonic() + TIMEOUT_S
        while not pred():
            assert time.monotonic() < deadline, f"timed out: {what}"
            app.processEvents()
            QThread.msleep(1)

    try:
        wait(lambda: isinstance(window.frame, OverviewFrame), "first frame")
        window.faster_requested.emit()
        window.faster_requested.emit()
        wait(lambda: window.frame.transport.pace_text == "FAST", "FAST")
        window.toggle_play()
        wait(
            lambda: (
                isinstance(window.frame, OverviewFrame)
                and window.frame.transport.playback is Playback.ENDED
            ),
            "desktop REPLAY ENDED",
        )
        end = window.frame
    finally:
        window.close()
        wait(window.thread.isFinished, "owner thread stop")
        app.processEvents()
    return window.worker._session, window.worker._tracker, end  # read after the join


def _exact(records) -> list[str]:
    return [repr(r) for r in records]  # repr keeps Decimal('4119.960') scale and int ms


def test_gui05_62_textual_and_desktop_replay_identically_to_the_end(app, state, isolated_env):
    tui, tui_tracker = _textual(state, isolated_env)
    qt, qt_tracker, end = _desktop(app, state)

    assert tui.playback is qt.playback is Playback.ENDED
    assert end.transport.processed == end.transport.total == len(qt.quotes) == len(tui.quotes)
    assert _exact(qt.quotes) == _exact(tui.quotes)
    assert _exact(qt.feed) == _exact(tui.feed)
    assert _exact(qt.pipeline.detector.events) == _exact(tui.pipeline.detector.events)
    sig_qt, sig_tui = qt.pipeline.signals.events, tui.pipeline.signals.events
    assert _exact(sig_qt) == _exact(sig_tui)
    assert sig_qt, "fixture config must produce signal events or the comparison is vacuous"
    kinds = {e.kind.value for e in sig_qt}
    assert len(kinds) >= 2, kinds
    assert [e.signal_id for e in sig_qt] == [e.signal_id for e in sig_tui]
    assert _exact(qt.snapshot().signals) == _exact(tui.snapshot().signals)  # final statuses
    assert qt.snapshot().virtual_time_ms == tui.snapshot().virtual_time_ms
    times = [q.received_time_ms for q in qt.quotes]
    assert times == sorted(times)  # causal source order (same-ms ties kept in source order)
    assert qt.pipeline.detector.events and qt_tracker.touches  # comparisons are not vacuous
    assert _exact(qt_tracker.touches) == _exact(tui_tracker.touches)
    prices = [d for e in sig_qt for d in vars_decimals(e)]
    assert prices and all(isinstance(d, Decimal) for d in prices)


def vars_decimals(record) -> list[Decimal]:
    fields = getattr(record, "__dataclass_fields__", {})
    return [v for k in fields if isinstance(v := getattr(record, k), Decimal)]
