"""TF-1d: bounded exporter diagnostics distinguish heartbeats from live ticks."""

from __future__ import annotations

from pathlib import Path

import pytest

from grog.desktop.mt5_feed_probe import TailState, probe_exporter_tail
from reference_support import SRC, T0, Writer


def test_missing_source_never_claims_feed(tmp_path: Path) -> None:
    result = probe_exporter_tail(tmp_path, SRC)
    assert result.state is TailState.SOURCE_NOT_FOUND
    assert result.file is None and not result.feed_verified


def test_connected_open_heartbeats_only_are_not_live_ticks(tmp_path: Path) -> None:
    writer = Writer(tmp_path)
    writer.hb(T0, connected=1, session="OPEN")
    writer.hb(T0 + 1000, connected=1, session="OPEN")
    before = writer.path.read_bytes()
    result = probe_exporter_tail(tmp_path, SRC)
    assert result.state is TailState.HEARTBEAT_ONLY
    assert result.heartbeat_count == 2 and result.live_tick_count == 0
    assert result.last_heartbeat is not None and result.last_heartbeat.connected
    assert result.last_heartbeat.session == "OPEN"
    assert not result.feed_verified
    assert writer.path.read_bytes() == before


def test_heartbeat_reported_utc_age_uses_its_own_offset(tmp_path: Path) -> None:
    writer = Writer(tmp_path)
    writer.hb(T0 + 1000, connected=1, session="OPEN")
    result = probe_exporter_tail(tmp_path, SRC)
    assert result.reported_heartbeat_utc_ms == T0 + 1000
    assert result.reported_heartbeat_age_ms(T0 + 5000) == 4000
    assert result.estimated_live_tick_age_ms(T0 + 5000) is None
    assert not result.feed_verified


def test_negative_heartbeat_age_is_not_clamped_to_fresh(tmp_path: Path) -> None:
    writer = Writer(tmp_path)
    writer.hb(T0 + 10_000)
    result = probe_exporter_tail(tmp_path, SRC)
    assert result.reported_heartbeat_age_ms(T0) == -10_000
    assert not result.feed_verified


def test_live_record_age_is_estimate_not_time_certification(tmp_path: Path) -> None:
    writer = Writer(tmp_path)
    writer.tick(T0, "4000.00", "4000.20")
    writer.hb(T0 + 1000)
    result = probe_exporter_tail(tmp_path, SRC)
    assert result.estimated_live_tick_age_ms(T0 + 5000) == 5000
    assert result.state is TailState.LIVE_TICK_IN_TAIL
    assert not result.feed_verified


def test_backfill_is_never_counted_as_live(tmp_path: Path) -> None:
    writer = Writer(tmp_path)
    writer.tick(T0, "4000.00", "4000.20", mode="B")
    result = probe_exporter_tail(tmp_path, SRC)
    assert result.state is TailState.NO_LIVE_TICK_IN_TAIL
    assert result.backfill_tick_count == 1 and result.live_tick_count == 0


def test_live_tick_record_is_only_an_observation(tmp_path: Path) -> None:
    writer = Writer(tmp_path)
    writer.tick(T0, "4000.00", "4000.20")
    result = probe_exporter_tail(tmp_path, SRC)
    assert result.state is TailState.LIVE_TICK_IN_TAIL
    assert result.last_live_tick is not None
    assert str(result.last_live_tick.bid) == "4000.00"
    assert not result.feed_verified  # Could be stale or offset-ambiguous.


def test_recent_gap_overrides_live_record_in_diagnostic(tmp_path: Path) -> None:
    writer = Writer(tmp_path)
    writer.tick(T0, "4000.00", "4000.20")
    writer.line("G,{seq},123,456,4022")
    result = probe_exporter_tail(tmp_path, SRC)
    assert result.state is TailState.GAP_IN_TAIL
    assert result.last_gap is not None and result.last_gap.error == 4022


def test_malformed_line_does_not_produce_live_status(tmp_path: Path) -> None:
    writer = Writer(tmp_path)
    writer.raw("T,2,L,not-a-number,4000,4001,6\n")
    result = probe_exporter_tail(tmp_path, SRC)
    assert result.state is TailState.MALFORMED_TAIL
    assert result.malformed_count == 1


def test_incomplete_trailing_line_is_discarded(tmp_path: Path) -> None:
    writer = Writer(tmp_path)
    writer.hb(T0)
    writer.raw("T,3,L,1800000000,4000,4001,6")  # Missing terminal newline
    result = probe_exporter_tail(tmp_path, SRC)
    assert result.state is TailState.HEARTBEAT_ONLY
    assert result.live_tick_count == 0 and result.malformed_count == 0


def test_latest_session_selected_without_other_source(tmp_path: Path) -> None:
    a = Writer(tmp_path, session="20261001T000000Z")
    a.tick(T0, "4000.00", "4000.20")
    newer = Writer(tmp_path, session="20261002T000000Z")
    newer.hb(T0 + 1000)
    other = Writer(tmp_path, source="other", session="20261003T000000Z")
    other.tick(T0 + 2000, "5000.00", "5000.20")
    result = probe_exporter_tail(tmp_path, SRC)
    assert result.file == newer.path
    assert result.state is TailState.HEARTBEAT_ONLY


def test_window_is_bounded_not_entire_history(tmp_path: Path) -> None:
    writer = Writer(tmp_path)
    writer.raw(("H,2,1790812800000,1,OPEN,7200\n") * 2000)
    result = probe_exporter_tail(tmp_path, SRC, max_bytes=4096)
    assert result.bytes_examined <= 4096
    assert result.heartbeat_count > 0
    assert result.state is TailState.HEARTBEAT_ONLY


@pytest.mark.parametrize("bad", ["../other", "", "foo/bar"])
def test_invalid_source_rejected(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ValueError, match="invalid source ID"):
        probe_exporter_tail(tmp_path, bad)
