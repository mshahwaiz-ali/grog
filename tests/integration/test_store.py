"""SQLite catalog: migration 0001, transactions, immutability (ST-01, CL-08, MD-13/14)."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from grog import settings
from grog.domain.clock import FixedClock
from grog.domain.enums import ImportRejectReason, SourceOrigin
from grog.domain.models import ImportBatch, QuoteSource
from grog.journal.store import (
    LATEST_SCHEMA_VERSION,
    STATE_DB_FILENAME,
    CatalogError,
    Store,
    available_migrations,
)

CLOCK = FixedClock(1793450000000)
SHA_A = "a" * 64
SHA_B = "b" * 64


def source(source_id: str = "syn-1", kind: SourceOrigin = SourceOrigin.SYNTHETIC) -> QuoteSource:
    return QuoteSource(source_id, kind, "XAUUSD", '{"raw_symbol":"XAUUSD"}', CLOCK.now_ms())


def batch(sha: str = SHA_A, lo: int = 100, hi: int = 200, source_id: str = "syn-1") -> ImportBatch:
    return ImportBatch(
        batch_id=f"id-{source_id}-{sha[:4]}",
        source_id=source_id,
        sha256=sha,
        origin=SourceOrigin.SYNTHETIC,
        format_version="CANONICAL_CSV_V1",
        path=f"market/{source_id}/x.csv.gz",
        min_provider_ms=lo,
        max_provider_ms=hi,
        quote_count=3,
        status="COMMITTED",
        imported_at_ms=CLOCK.now_ms(),
        stats_json="{}",
    )


@pytest.fixture
def store(tmp_path: Path):
    s = Store.open(tmp_path / "state" / STATE_DB_FILENAME, CLOCK)
    yield s
    s.close()


def dump(db: Path) -> list[tuple]:
    conn = sqlite3.connect(db)
    try:
        rows = []
        for table in ("schema_migrations", "quote_sources", "import_batches"):
            rows += [(table, *r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]
        return rows
    finally:
        conn.close()


def test_db_filename_matches_settings() -> None:
    assert STATE_DB_FILENAME == settings.STATE_DB_FILENAME


def test_migration_0001_schema(store: Store, tmp_path: Path) -> None:  # ST-01
    assert [v for v, _ in available_migrations()] == [1, 2, 3] and LATEST_SCHEMA_VERSION == 3
    assert store.schema_versions() == [1, 2, 3]
    conn = sqlite3.connect(store.path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert tables == {
        "schema_migrations",
        "quote_sources",
        "import_batches",
        "research_runs",
        "signal_records",
        "signal_events",
        "manual_positions",
        "position_events",
        "signal_decisions",
    }
    for forbidden in ("wallet", "order", "account", "trade", "broker"):
        assert not any(forbidden in t for t in tables)


def test_pragmas(store: Store) -> None:
    conn = store._conn
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_reopen_is_idempotent_and_preserves_rows(tmp_path: Path) -> None:
    db = tmp_path / "s" / STATE_DB_FILENAME
    with Store.open(db, CLOCK) as s:
        s.commit_import(source(), batch())
    before = dump(db)
    with Store.open(db, FixedClock(1)) as s:
        assert s.schema_versions() == [1, 2, 3]
        assert len(s.list_batches()) == 1
    assert dump(db) == before


def test_commit_and_idempotent_duplicate(store: Store) -> None:  # CL-04
    created, is_new = store.commit_import(source(), batch())
    assert is_new and store.get_batch(created.batch_id) == created
    again, is_new2 = store.commit_import(source(), replace(batch(), imported_at_ms=5))
    assert not is_new2 and again == created
    assert len(store.list_batches("syn-1")) == 1 and len(store.list_sources()) == 1
    assert store.find_batch("syn-1", SHA_A) == created


def test_same_bytes_under_two_sources_kept_distinct(store: Store) -> None:  # CL-06, MD-13
    store.commit_import(source("broker-a"), batch(source_id="broker-a"))
    store.commit_import(source("broker-b"), batch(source_id="broker-b"))
    assert [b.source_id for b in store.list_batches()] == ["broker-a", "broker-b"]


def test_source_metadata_conflict_rejected(store: Store) -> None:  # MD-14
    store.commit_import(source(), batch())
    changed = replace(source(), metadata_json='{"raw_symbol":"XAUUSD.m"}')
    with pytest.raises(CatalogError) as info:
        store.commit_import(changed, batch(SHA_B, 300, 400))
    assert info.value.reason is ImportRejectReason.SOURCE_METADATA_CONFLICT
    hist = replace(source(), kind=SourceOrigin.HISTORICAL)
    with pytest.raises(CatalogError):
        store.commit_import(hist, replace(batch(SHA_B, 300, 400), origin=SourceOrigin.HISTORICAL))
    assert len(store.list_batches()) == 1


@pytest.mark.parametrize(("lo", "hi"), [(150, 250), (50, 100), (200, 300), (120, 130)])
def test_overlapping_batch_rejected(store: Store, lo: int, hi: int) -> None:
    store.commit_import(source(), batch())
    with pytest.raises(CatalogError) as info:
        store.commit_import(source(), batch(SHA_B, lo, hi))
    assert info.value.reason is ImportRejectReason.OVERLAPS_EXISTING_BATCH
    assert len(store.list_batches()) == 1


def test_adjacent_batch_accepted(store: Store) -> None:
    store.commit_import(source(), batch())
    store.commit_import(source(), batch(SHA_B, 201, 300))
    assert len(store.list_batches()) == 2


def test_failed_transaction_rolls_back_new_source(store: Store) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        store.commit_import(source(), replace(batch(), quote_count=0))  # CHECK violation
    assert store.list_sources() == [] and store.list_batches() == []


def test_explicit_transaction_rollback(store: Store) -> None:
    with pytest.raises(RuntimeError), store.transaction() as conn:
        conn.execute("INSERT INTO quote_sources VALUES ('x','SYNTHETIC','XAUUSD','{}',1)")
        raise RuntimeError("crash before commit")
    assert store.list_sources() == []


def test_rows_are_immutable_and_foreign_keys_enforced(store: Store) -> None:
    store.commit_import(source(), batch())
    conn = store._conn
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE import_batches SET quote_count = 99")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM quote_sources")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO import_batches VALUES ('z','missing',?,'SYNTHETIC','v','p',1,2,1,"
            "'COMMITTED',1,'{}')",
            (SHA_B,),
        )


def test_failed_migration_rolls_back(tmp_path: Path) -> None:
    db = tmp_path / STATE_DB_FILENAME
    bad = [*available_migrations(), (99, "CREATE TABLE extra (x INTEGER);\nNOT VALID SQL;")]
    with pytest.raises(sqlite3.OperationalError):
        Store.open(db, CLOCK, migrations=bad)
    with Store.open(db, CLOCK) as s:
        assert s.schema_versions() == [1, 2, 3]
        tables = {r[0] for r in s._conn.execute("SELECT name FROM sqlite_master")}
        assert "extra" not in tables
