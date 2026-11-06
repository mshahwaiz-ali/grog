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
    quote = dataclasses.replace(
        snap.quote, bid=Decimal("4119.9600"), ask=Decimal("4120.2700")
    )
    model = from_snapshot(dataclasses.replace(snap, quote=quote), (), {}, open_positions=0)
    assert model.bid == "4,119.9600"
    assert model.ask == "4,120.2700"

def test_qt_preview_uses_actual_snapshot_and_is_read_only(tmp_path, monkeypatch) -> None:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from grog.desktop.window import GoldWindow
    from ui_support import open_journal

    s = session()
    store, journal = open_journal(tmp_path)
    try:
        app = QApplication.instance() or QApplication(["gold-desktop-test"])
        window = GoldWindow(s, journal)
        window.show()
        app.processEvents()
        assert "SIMULATED" in window.source.text()
        assert window.bid.text() == format(s.snapshot().quote.bid, ",f")
        cursor = s.cursor
        window._step()
        assert s.cursor == cursor + 1
        window.close()
    finally:
        store.close()
