"""Stored batches -> causal 4-timeframe bars, reproducible across replays (MD-22, M02 Done)."""

from __future__ import annotations

from pathlib import Path

import pytest

from grog.domain.clock import FixedClock
from grog.domain.enums import Timeframe
from grog.journal.store import STATE_DB_FILENAME, Store
from grog.market_data.bars import aggregate, bar_to_dict, gap_to_dict
from grog.market_data.batches import import_file, load_source_quotes
from grog.market_data.import_csv import parse_canonical_csv

T0 = 1793430000000  # 2026-10-31T07:00:00Z
HEADER = "provider_time_utc_ms,received_time_utc_ms,bid,ask\n"


def write_part(path: Path, start: int, count: int, step: int, base_cents: int) -> Path:
    rows = []
    for i in range(count):
        t = start + i * step
        cents = base_cents + (i * 7) % 250
        bid = f"{cents // 100}.{cents % 100:02d}"
        ask_c = cents + 20 + i % 5
        rows.append(f"{t},{t + i % 9},{bid},{ask_c // 100}.{ask_c % 100:02d}")
    path.write_text(HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def parts(tmp_path: Path) -> list[Path]:
    a = write_part(tmp_path / "a.csv", T0, 6000, 900, 400_000)  # 07:00 .. ~08:30
    # 25-minute outage, then a second adjacent batch.
    b = write_part(tmp_path / "b.csv", T0 + 6000 * 900 + 25 * 60_000, 6000, 900, 400_100)
    return [a, b]


def replay(state: Path, parts: list[Path]) -> tuple[list[dict], list[dict]]:
    with Store.open(state / STATE_DB_FILENAME, FixedClock(1)) as store:
        for p in parts:
            import_file(p, source_id="syn-1", origin="SYNTHETIC", state_dir=state, catalog=store)
        quotes = load_source_quotes(store, state, "syn-1")
    agg = aggregate("syn-1", quotes)
    return (
        [bar_to_dict(b) for tf in Timeframe for b in agg.history.all(tf)],
        [gap_to_dict(g) for g in agg.gaps],
    )


def test_two_replays_from_same_bytes_are_identical(tmp_path: Path, parts: list[Path]) -> None:
    first = replay(tmp_path / "state-a", parts)
    second = replay(tmp_path / "state-b", list(reversed(parts)))  # import order irrelevant
    assert first == second
    bars, gaps = first
    by_tf = {tf.value: [b for b in bars if b["timeframe"] == tf.value] for tf in Timeframe}
    assert all(by_tf[tf.value] for tf in Timeframe)
    assert {g["kind"] for g in gaps} == {"DATA_GAP"}
    assert any(b["quality"] == "GAPPED" for b in by_tf["H1"])


def test_catalog_replay_equals_direct_parse(tmp_path: Path, parts: list[Path]) -> None:
    quotes = []
    for p in parts:
        quotes += parse_canonical_csv(p.read_bytes(), source_id="syn-1", origin="SYNTHETIC").quotes
    agg = aggregate("syn-1", quotes)
    direct = (
        [bar_to_dict(b) for tf in Timeframe for b in agg.history.all(tf)],
        [gap_to_dict(g) for g in agg.gaps],
    )
    assert replay(tmp_path / "state", parts) == direct


def test_unknown_source(tmp_path: Path) -> None:
    with Store.open(tmp_path / STATE_DB_FILENAME, FixedClock(1)) as store, pytest.raises(KeyError):
        load_source_quotes(store, tmp_path, "missing")
