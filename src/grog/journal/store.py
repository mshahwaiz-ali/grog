"""SQLite storage for the local catalog (docs/09 Section 7, SQLite policy).

* Foreign keys on, WAL journal, bounded busy timeout, one explicit transaction
  per logical write (``BEGIN IMMEDIATE`` ... ``COMMIT``; rollback on any error).
* Forward-only, idempotent migrations from versioned ``migrations/NNNN.sql``.
* Decimals as exact TEXT, UTC ms as INTEGER, JSON with canonical key order.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path

from grog.domain.clock import Clock
from grog.domain.enums import ImportRejectReason, SourceOrigin
from grog.domain.models import ImportBatch, QuoteSource
from grog.market_data.batches import CatalogError

STATE_DB_FILENAME = "state.sqlite3"
BUSY_TIMEOUT_MS = 5000

__all__ = [
    "BUSY_TIMEOUT_MS",
    "LATEST_SCHEMA_VERSION",
    "STATE_DB_FILENAME",
    "CatalogError",
    "Store",
    "available_migrations",
]


def available_migrations() -> list[tuple[int, str]]:
    """``[(version, sql)]`` sorted by version, read from package data."""
    folder = resources.files("grog.journal.migrations")
    found = []
    for entry in folder.iterdir():
        name = entry.name
        if name.endswith(".sql") and name[:-4].isdigit():
            found.append((int(name[:-4]), entry.read_text(encoding="utf-8")))
    return sorted(found)


LATEST_SCHEMA_VERSION = max(v for v, _ in available_migrations())


def _source_from_row(row: sqlite3.Row) -> QuoteSource:
    return QuoteSource(
        source_id=row["source_id"],
        kind=SourceOrigin(row["kind"]),
        symbol=row["symbol"],
        metadata_json=row["metadata_json"],
        created_at_ms=row["created_at_ms"],
    )


def _batch_from_row(row: sqlite3.Row) -> ImportBatch:
    return ImportBatch(
        batch_id=row["batch_id"],
        source_id=row["source_id"],
        sha256=row["sha256"],
        origin=SourceOrigin(row["origin"]),
        format_version=row["format_version"],
        path=row["path"],
        min_provider_ms=row["min_provider_ms"],
        max_provider_ms=row["max_provider_ms"],
        quote_count=row["quote_count"],
        status=row["status"],
        imported_at_ms=row["imported_at_ms"],
        stats_json=row["stats_json"],
    )


class Store:
    """Single serialized writer over the local state database."""

    def __init__(self, conn: sqlite3.Connection, clock: Clock, path: Path) -> None:
        self._conn = conn
        self._clock = clock
        self.path = path

    # ------------------------------------------------------------------ lifecycle

    @classmethod
    def open(
        cls,
        db_path: Path,
        clock: Clock,
        migrations: list[tuple[int, str]] | None = None,
    ) -> Store:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, isolation_level=None, timeout=BUSY_TIMEOUT_MS / 1000)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            store = cls(conn, clock, db_path)
            store._migrate(available_migrations() if migrations is None else migrations)
        except BaseException:
            conn.close()
            raise
        return store

    @classmethod
    def open_read_only(cls, db_path: Path, clock: Clock) -> Store:
        """Existing database, SQLite read-only mode: never created, migrated or written."""
        if not db_path.is_file():
            raise FileNotFoundError(db_path)
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=BUSY_TIMEOUT_MS / 1000)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        return cls(conn, clock, db_path)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Explicit write transaction; any exception rolls back everything inside it."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")

    def _migrate(self, migrations: list[tuple[int, str]]) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version INTEGER PRIMARY KEY CHECK (typeof(version) = 'integer'),"
            " applied_at_utc_ms INTEGER NOT NULL CHECK (typeof(applied_at_utc_ms) = 'integer'))"
        )
        for version, sql in migrations:
            if self._is_applied(version):
                continue
            script = (
                "BEGIN IMMEDIATE;\n"
                f"{sql}\n"
                "INSERT INTO schema_migrations (version, applied_at_utc_ms) "
                f"VALUES ({int(version)}, {int(self._clock.now_ms())});\n"
                "COMMIT;\n"
            )
            try:
                self._conn.executescript(script)
            except BaseException:
                if self._conn.in_transaction:
                    self._conn.execute("ROLLBACK")
                raise

    def _is_applied(self, version: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?", (version,)
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------ reads

    def schema_versions(self) -> list[int]:
        rows = self._conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        return [r["version"] for r in rows]

    def get_source(self, source_id: str) -> QuoteSource | None:
        row = self._conn.execute(
            "SELECT * FROM quote_sources WHERE source_id = ?", (source_id,)
        ).fetchone()
        return None if row is None else _source_from_row(row)

    def list_sources(self) -> list[QuoteSource]:
        rows = self._conn.execute("SELECT * FROM quote_sources ORDER BY source_id")
        return [_source_from_row(r) for r in rows]

    def get_batch(self, batch_id: str) -> ImportBatch | None:
        row = self._conn.execute(
            "SELECT * FROM import_batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        return None if row is None else _batch_from_row(row)

    def find_batch(self, source_id: str, sha256: str) -> ImportBatch | None:
        row = self._conn.execute(
            "SELECT * FROM import_batches WHERE source_id = ? AND sha256 = ?", (source_id, sha256)
        ).fetchone()
        return None if row is None else _batch_from_row(row)

    def list_batches(self, source_id: str | None = None) -> list[ImportBatch]:
        if source_id is None:
            rows = self._conn.execute(
                "SELECT * FROM import_batches ORDER BY source_id, min_provider_ms, batch_id"
            )
        else:
            rows = self._conn.execute(
                "SELECT * FROM import_batches WHERE source_id = ? "
                "ORDER BY min_provider_ms, batch_id",
                (source_id,),
            )
        return [_batch_from_row(r) for r in rows]

    def overlapping_batches(
        self, source_id: str, min_ms: int, max_ms: int, exclude_sha256: str | None = None
    ) -> list[ImportBatch]:
        """Committed batches of the same source whose inclusive provider-time range intersects."""
        rows = self._conn.execute(
            "SELECT * FROM import_batches WHERE source_id = ? AND min_provider_ms <= ? "
            "AND max_provider_ms >= ? AND sha256 IS NOT ? ORDER BY min_provider_ms, batch_id",
            (source_id, max_ms, min_ms, exclude_sha256),
        )
        return [_batch_from_row(r) for r in rows]

    # ------------------------------------------------------------------ writes

    def check_source_compatible(self, source: QuoteSource) -> QuoteSource | None:
        """Return the existing source if identical identity, ``None`` if new; raise on conflict."""
        existing = self.get_source(source.source_id)
        if existing is None:
            return None
        if (existing.kind, existing.symbol, existing.metadata_json) != (
            source.kind,
            source.symbol,
            source.metadata_json,
        ):
            raise CatalogError(
                ImportRejectReason.SOURCE_METADATA_CONFLICT,
                f"source {source.source_id!r} is recorded as kind={existing.kind.value} "
                f"metadata={existing.metadata_json}; requested kind={source.kind.value} "
                f"metadata={source.metadata_json}. Use a new source ID.",
            )
        return existing

    def commit_import(self, source: QuoteSource, batch: ImportBatch) -> tuple[ImportBatch, bool]:
        """Atomically record a batch (and its source if new). Returns ``(batch, created)``.

        Idempotent: the same source+SHA-256 returns the existing batch with ``created=False``.
        """
        if batch.source_id != source.source_id or batch.origin != source.kind:
            raise CatalogError(
                ImportRejectReason.SOURCE_METADATA_CONFLICT, "batch does not match its source"
            )
        with self.transaction() as conn:
            existing_batch = self.find_batch(batch.source_id, batch.sha256)
            if existing_batch is not None:
                return existing_batch, False
            if self.check_source_compatible(source) is None:
                conn.execute(
                    "INSERT INTO quote_sources "
                    "(source_id, kind, symbol, metadata_json, created_at_ms) VALUES (?,?,?,?,?)",
                    (
                        source.source_id,
                        source.kind.value,
                        source.symbol,
                        source.metadata_json,
                        source.created_at_ms,
                    ),
                )
            overlaps = self.overlapping_batches(
                batch.source_id, batch.min_provider_ms, batch.max_provider_ms, batch.sha256
            )
            if overlaps:
                raise CatalogError(
                    ImportRejectReason.OVERLAPS_EXISTING_BATCH,
                    f"provider-time range overlaps committed batch {overlaps[0].batch_id}",
                )
            conn.execute(
                "INSERT INTO import_batches (batch_id, source_id, sha256, origin, format_version,"
                " path, min_provider_ms, max_provider_ms, quote_count, status, imported_at_ms,"
                " stats_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    batch.batch_id,
                    batch.source_id,
                    batch.sha256,
                    batch.origin.value,
                    batch.format_version,
                    batch.path,
                    batch.min_provider_ms,
                    batch.max_provider_ms,
                    batch.quote_count,
                    batch.status,
                    batch.imported_at_ms,
                    batch.stats_json,
                ),
            )
        return batch, True

    def now_ms(self) -> int:
        return self._clock.now_ms()
