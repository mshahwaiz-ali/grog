"""Atomic, idempotent batch import (CL-04..08, MD-02/13/19/22; roadmap M01 Done)."""

from __future__ import annotations

import gzip
import hashlib
import os
import sqlite3
from pathlib import Path

import pytest

from grog.domain.clock import FixedClock
from grog.domain.enums import ImportRejectReason, SourceOrigin
from grog.journal.store import STATE_DB_FILENAME, Store
from grog.market_data import batches
from grog.market_data.batches import (
    BatchIntegrityError,
    CatalogError,
    import_file,
    read_batch_quotes,
)
from grog.market_data.import_csv import CsvImportError, parse_canonical_csv

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic_xauusd_v1.csv"
HEADER = "provider_time_utc_ms,received_time_utc_ms,bid,ask\n"
CLOCK = FixedClock(1793450000000)


def open_store(state: Path) -> Store:
    return Store.open(state / STATE_DB_FILENAME, CLOCK)


def do_import(
    state: Path, path: Path = FIXTURE, source_id: str = "syn-1", origin: str = "SYNTHETIC"
):
    with open_store(state) as store:
        return import_file(path, source_id=source_id, origin=origin, state_dir=state, catalog=store)


def catalog_dump(state: Path) -> list[tuple]:
    conn = sqlite3.connect(state / STATE_DB_FILENAME)
    try:
        out: list[tuple] = []
        for table in ("schema_migrations", "quote_sources", "import_batches"):
            out += [(table, *r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]
        return out
    finally:
        conn.close()


def market_files(state: Path) -> list[str]:
    root = state / "market"
    if not root.exists():
        return []
    return sorted(str(p.relative_to(state)) for p in root.rglob("*") if p.is_file())


def write_csv(path: Path, rows: list[str]) -> Path:
    path.write_text(HEADER + "".join(r + "\n" for r in rows), encoding="utf-8")
    return path


def test_import_commits_one_durable_batch(tmp_path: Path) -> None:
    state = tmp_path / "state"
    result = do_import(state)
    data = FIXTURE.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    assert result.status == "COMMITTED"
    assert result.batch.sha256 == sha and result.batch.quote_count == 6
    assert result.batch.path == f"market/syn-1/2026/10/31/{sha}.csv.gz"
    assert market_files(state) == [result.batch.path]
    assert gzip.decompress((state / result.batch.path).read_bytes()) == data
    with open_store(state) as store:
        assert [b.batch_id for b in store.list_batches()] == [result.batch.batch_id]
        src = store.get_source("syn-1")
    assert src is not None and src.kind is SourceOrigin.SYNTHETIC
    assert src.metadata_json == '{"raw_symbol":"XAUUSD"}'


def test_importing_twice_yields_exactly_one_batch(tmp_path: Path) -> None:  # CL-04, Done
    state = tmp_path / "state"
    first = do_import(state)
    before = catalog_dump(state)
    copy = tmp_path / "renamed.csv"
    copy.write_bytes(FIXTURE.read_bytes())
    second = do_import(state, copy)
    assert second.status == "ALREADY_IMPORTED" and second.batch == first.batch
    assert catalog_dump(state) == before
    assert len(market_files(state)) == 1


@pytest.mark.parametrize(
    ("bad_row", "reason"),
    [
        ("1793440000300,1793440000313,4000.30,4000.10", ImportRejectReason.ASK_BELOW_BID),
        ("1793440000300,1793440000313,NaN,4000.10", ImportRejectReason.INVALID_DECIMAL),
        ("1793440000300,1793440000313,-1,4000.10", ImportRejectReason.NONPOSITIVE_PRICE),
        ("17934400003.5,1793440000313,4000,4000.10", ImportRejectReason.INVALID_UTC_MS),
    ],
)
def test_corrupt_file_does_not_change_prior_state(
    tmp_path: Path, bad_row: str, reason: ImportRejectReason
) -> None:  # CL-05, CL-07
    state = tmp_path / "state"
    do_import(state)
    before, files = catalog_dump(state), market_files(state)
    rows = FIXTURE.read_text().splitlines()
    rows.insert(3, bad_row)
    bad = tmp_path / "bad.csv"
    bad.write_text("\n".join(rows) + "\n")
    with pytest.raises(CsvImportError) as info:
        do_import(state, bad, source_id="syn-2")
    assert info.value.reason is reason and info.value.line == 4
    assert catalog_dump(state) == before and market_files(state) == files


def test_rejected_first_import_leaves_no_batch(tmp_path: Path) -> None:
    state = tmp_path / "state"
    bad = write_csv(tmp_path / "bad.csv", ["1,1,4000.2,4000.1"])
    with pytest.raises(CsvImportError):
        do_import(state, bad)
    assert market_files(state) == []
    with open_store(state) as store:
        assert store.list_batches() == [] and store.list_sources() == []


def test_crash_after_file_write_before_commit_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # CL-08, MD-19
    state = tmp_path / "state"

    def crash(self: Store, *_a: object) -> None:
        raise KeyboardInterrupt("simulated crash before catalog commit")

    with monkeypatch.context() as m:
        m.setattr(Store, "commit_import", crash)
        with pytest.raises(KeyboardInterrupt):
            do_import(state)
    with open_store(state) as store:
        assert store.list_batches() == []  # no phantom batch
    assert len(market_files(state)) == 1  # unreferenced raw file only
    result = do_import(state)
    assert result.status == "COMMITTED"
    assert len(market_files(state)) == 1
    with open_store(state) as store:
        assert len(store.list_batches()) == 1


def test_crash_during_file_write_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"

    def failing_replace(*_a: object) -> None:
        raise OSError("disk full")

    with monkeypatch.context() as m:
        m.setattr(batches.os, "replace", failing_replace)
        with pytest.raises(OSError):
            do_import(state)
    assert market_files(state) == []
    leftovers = [p for p in (state / "market").rglob("*") if p.is_file()]
    assert leftovers == []
    with open_store(state) as store:
        assert store.list_batches() == [] and store.list_sources() == []
    assert do_import(state).status == "COMMITTED"


def test_corrupted_orphan_raw_file_is_replaced(tmp_path: Path) -> None:
    state = tmp_path / "state"
    data = FIXTURE.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    orphan = state / f"market/syn-1/2026/10/31/{sha}.csv.gz"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"partial garbage")
    result = do_import(state)
    assert gzip.decompress((state / result.batch.path).read_bytes()) == data


def test_reimport_repairs_missing_raw_file(tmp_path: Path) -> None:
    state = tmp_path / "state"
    first = do_import(state)
    (state / first.batch.path).unlink()
    again = do_import(state)
    assert again.status == "ALREADY_IMPORTED"
    assert gzip.decompress((state / first.batch.path).read_bytes()) == FIXTURE.read_bytes()


def test_same_bytes_under_two_sources_are_two_batches(tmp_path: Path) -> None:  # CL-06, MD-13
    state = tmp_path / "state"
    a = do_import(state, source_id="broker-a")
    b = do_import(state, source_id="broker-b")
    assert a.batch.batch_id != b.batch.batch_id and a.batch.sha256 == b.batch.sha256
    with open_store(state) as store:
        qa = read_batch_quotes(state, store.get_source("broker-a"), a.batch)
        qb = read_batch_quotes(state, store.get_source("broker-b"), b.batch)
    assert {q.source_id for q in qa} == {"broker-a"} and {q.source_id for q in qb} == {"broker-b"}


def test_origin_change_for_existing_source_rejected(tmp_path: Path) -> None:
    state = tmp_path / "state"
    do_import(state)
    before = catalog_dump(state)
    other = write_csv(tmp_path / "later.csv", ["1793450000000,1793450000000,4001.00,4001.20"])
    with pytest.raises(CatalogError) as info:
        do_import(state, other, origin="HISTORICAL")
    assert info.value.reason is ImportRejectReason.SOURCE_METADATA_CONFLICT
    assert catalog_dump(state) == before


def test_overlapping_and_adjacent_batches(tmp_path: Path) -> None:  # MD-02 (fail closed)
    state = tmp_path / "state"
    do_import(state)
    files = market_files(state)
    # Overlaps the inclusive boundary of the first batch (same last millisecond).
    overlap = write_csv(tmp_path / "overlap.csv", ["1793440002500,1793440002600,4000.11,4000.31"])
    with pytest.raises(CatalogError) as info:
        do_import(state, overlap)
    assert info.value.reason is ImportRejectReason.OVERLAPS_EXISTING_BATCH
    assert market_files(state) == files
    adjacent = write_csv(tmp_path / "next.csv", ["1793440002501,1793440002600,4000.11,4000.31"])
    assert do_import(state, adjacent).status == "COMMITTED"
    with open_store(state) as store:
        assert len(store.list_batches("syn-1")) == 2


def test_reload_matches_direct_parse_and_is_reproducible(tmp_path: Path) -> None:  # MD-22
    data = FIXTURE.read_bytes()
    direct = parse_canonical_csv(data, source_id="syn-1", origin="SYNTHETIC").quotes
    loaded = []
    for name in ("run-a", "run-b"):
        state = tmp_path / name
        result = do_import(state)
        with open_store(state) as store:
            loaded.append(
                (result.batch, read_batch_quotes(state, store.get_source("syn-1"), result.batch))
            )
    (batch_a, quotes_a), (batch_b, quotes_b) = loaded
    assert quotes_a == quotes_b == direct
    assert batch_a == batch_b
    assert (tmp_path / "run-a" / batch_a.path).read_bytes() == (
        tmp_path / "run-b" / batch_b.path
    ).read_bytes()


def test_tampered_raw_file_detected(tmp_path: Path) -> None:
    state = tmp_path / "state"
    result = do_import(state)
    (state / result.batch.path).write_bytes(gzip.compress(b"tampered", mtime=0))
    with open_store(state) as store, pytest.raises(BatchIntegrityError):
        read_batch_quotes(state, store.get_source("syn-1"), result.batch)


def test_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(CsvImportError) as info:
        do_import(tmp_path / "state", tmp_path / "missing.csv")
    assert info.value.reason is ImportRejectReason.FILE_UNREADABLE


def test_no_temp_files_left_after_success(tmp_path: Path) -> None:
    state = tmp_path / "state"
    do_import(state)
    names = [p.name for p in (state / "market").rglob("*") if p.is_file()]
    assert all(not n.startswith(".") for n in names)
    assert os.listdir(state)  # state dir created only by an explicit import


def _deflate_corrupt(path: Path) -> None:
    """Keep a valid gzip header but make the DEFLATE block type invalid (BTYPE=11).

    gzip.decompress raises zlib.error here, not OSError/EOFError/BadGzipFile.
    """
    damaged = bytearray(path.read_bytes())
    damaged[10] = 0xFF  # first DEFLATE byte after the 10-byte gzip header
    path.write_bytes(bytes(damaged))


def test_damaged_deflate_payload_is_an_integrity_error(tmp_path: Path) -> None:
    import zlib

    state = tmp_path / "state"
    result = do_import(state)
    stored = state / result.batch.path
    _deflate_corrupt(stored)
    with pytest.raises(zlib.error):
        gzip.decompress(stored.read_bytes())  # the exact corruption under test
    assert batches._stored_bytes_ok(stored, result.batch.sha256) is False
    with open_store(state) as store, pytest.raises(BatchIntegrityError) as info:
        read_batch_quotes(state, store.get_source("syn-1"), result.batch)
    assert "stored batch unreadable" in str(info.value)
    assert isinstance(info.value.__cause__, zlib.error)


def test_reimport_of_identical_file_repairs_damaged_deflate_payload(tmp_path: Path) -> None:
    state = tmp_path / "state"
    first = do_import(state)
    stored = state / first.batch.path
    original = stored.read_bytes()
    _deflate_corrupt(stored)
    again = do_import(state)
    assert again.status == "ALREADY_IMPORTED" and again.batch == first.batch
    assert stored.read_bytes() == original
    with open_store(state) as store:
        assert read_batch_quotes(state, store.get_source("syn-1"), first.batch)
