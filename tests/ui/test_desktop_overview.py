"""Read-only desktop Overview parity tests using the existing synthetic engine fixtures."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from grog.desktop.overview_model import from_snapshot
from grog.domain.enums import SignalEventKind
from ui_support import session, step_until


def _view(s, overlay=None, positions: int = 0):
    return from_snapshot(
        s.snapshot(), s.pipeline.signals.events, overlay or {}, open_positions=positions
    )


def test_overview_is_simulated_and_carries_virtual_clock() -> None:
    s = session()
    before = s.cursor
    view = _view(s)
    assert "SIMULATED" in view.source and "REPLAY" in view.source
    assert "virtual" in view.virtual_utc
    assert "PAUSED" in view.playback
    assert view.bid == format(s.snapshot().quote.bid, ",f")
    assert view.ask == format(s.snapshot().quote.ask, ",f")
    assert s.cursor == before  # model creation cannot advance the engine


def test_forming_never_becomes_ready_in_overview() -> None:
    s = session()
    while not s.snapshot().forming:
        assert s.step()
    view = _view(s)
    assert "no trade yet" in view.headline.lower()
    assert view.watchlist
    assert all("No confirmed trade signal" in x for x in view.watchlist)


def test_ready_uses_immutable_price_sides_and_no_fabricated_fill() -> None:
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED)
    v = next(v for v in s.snapshot().signals if v.record.signal_id == sid)
    view = _view(s)
    assert "proposal ready in simulation" in view.headline
    assert "simulated" in view.description.lower()
    side = "ASK" if v.record.side.value == "BUY" else "BID"
    assert f"{side} entry" in view.description
    assert format(v.record.e0, ",f") in view.description
    assert format(v.record.tp1, ",f") in view.description
    assert format(v.record.tp2, ",f") in view.description


def test_entered_signal_is_not_readvertised_as_new() -> None:
    s = session()
    sid = step_until(s, SignalEventKind.READY_ISSUED)
    view = _view(s, {sid: ("ENTERED", "manual-position")}, positions=1)
    assert "proposal ready in simulation" not in view.headline
    assert "1 stored open position" in view.open_positions
    assert "reconciliation has not been performed" in view.open_positions


def test_missing_data_is_not_zero_or_fresh() -> None:
    s = session()
    snap = dataclasses.replace(s.snapshot(), quote=None, health=None)
    view = from_snapshot(snap, (), {}, open_positions=0)
    assert view.bid == view.ask == "\u2014"
    assert view.source_health == "UNKNOWN"
    assert view.headline == "No market data"


def test_price_scale_remains_lossless_in_quote_cards() -> None:
    s = session()
    snap = s.snapshot()
    quote = dataclasses.replace(snap.quote, bid=Decimal("4119.9600"), ask=Decimal("4120.2700"))
    model = from_snapshot(dataclasses.replace(snap, quote=quote), (), {}, open_positions=0)
    assert model.bid == "4,119.9600"
    assert model.ask == "4,120.2700"


def test_qt_preview_uses_actual_snapshot_and_is_read_only(tmp_path, monkeypatch) -> None:
    """D01: the window renders worker frames of the real engine and never writes the journal.

    The engine now lives on the replay owner thread, so stepping goes through the worker.
    """
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication

    from grog.desktop.frames import OverviewFrame
    from grog.desktop.loading import LoadRequest, read_journal
    from grog.desktop.replay_worker import ReplayWorker
    from grog.desktop.window import GoldWindow
    from ui_support import open_journal

    store, _journal = open_journal(tmp_path)
    store.close()
    db = tmp_path / "state" / "state.sqlite3"
    before = db.read_bytes()
    sessions = []

    def loader(_request):
        sessions.append(session())
        return sessions[-1]

    request = LoadRequest("syn", state_dir=str(tmp_path / "state"))
    app = QApplication.instance() or QApplication(["gold-desktop-test"])
    worker = ReplayWorker(loader=loader, journal_reader=read_journal)
    window = GoldWindow(request, worker=worker)
    window.show()

    def wait(predicate):
        for _ in range(60_000):
            if predicate():
                return
            app.processEvents()
            QThread.msleep(1)
        raise AssertionError("timed out")

    try:
        wait(lambda: isinstance(window.frame, OverviewFrame))
        frame = window.frame
        assert "SIMULATED" in window.fidelity_pill.text()
        assert window.bid.value.text() == format(sessions[0].snapshot().quote.bid, ",f")
        cursor = frame.transport.processed
        window.step_once()
        wait(lambda: window.frame.transport.processed == cursor + 1)
        assert sessions[0].cursor == cursor + 1
    finally:
        window.close()  # asynchronous: wait for the replay owner thread to stop
        wait(window.thread.isFinished)
    assert db.read_bytes() == before  # read-only: no journal or catalog write
