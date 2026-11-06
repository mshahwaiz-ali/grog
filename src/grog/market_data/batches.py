"""Durable, atomic, idempotent batch import (docs/09 Sections 6, 7 and 10).

Order of operations makes interruption safe:

1. Read and **fully** validate the file in memory (any error: nothing written).
2. If the same source + SHA-256 is already committed: idempotent no-op.
3. Refuse source-identity conflicts and overlapping provider-time ranges.
4. Write the immutable raw batch as ``market/<source_id>/YYYY/MM/DD/<sha256>.csv.gz``
   via temp file + fsync + atomic rename (an existing intact file is reused).
5. Commit source + batch rows in **one** SQLite transaction.

The catalog row is the only proof of an import. A crash before step 5 leaves at
most an unreferenced raw file, which a retry verifies and reuses; it never
produces a phantom or duplicate batch.
"""

from __future__ import annotations

import gzip
import json
import os
import zlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from grog.domain.enums import ImportRejectReason, SourceOrigin
from grog.domain.ids import batch_id as make_batch_id
from grog.domain.ids import canonical_json, sha256_hex
from grog.domain.models import CANONICAL_SYMBOL, ImportBatch, NormalizedQuote, QuoteSource
from grog.market_data.import_csv import (
    BatchStats,
    CsvImportError,
    ParsedBatch,
    parse_canonical_csv,
)

MARKET_DIRNAME = "market"
BATCH_STATUS_COMMITTED = "COMMITTED"


class CatalogError(RuntimeError):
    """A catalog write was refused; nothing was committed and prior state is unchanged."""

    def __init__(self, reason: ImportRejectReason, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"reason={reason.value} detail={detail}")


class BatchIntegrityError(RuntimeError):
    """A stored raw batch is missing or does not match its recorded SHA-256."""


class BatchCatalog(Protocol):
    """The storage port the importer needs (implemented by ``grog.journal.store.Store``)."""

    def now_ms(self) -> int: ...

    def find_batch(self, source_id: str, sha256: str) -> ImportBatch | None: ...

    def check_source_compatible(self, source: QuoteSource) -> QuoteSource | None: ...

    def overlapping_batches(
        self, source_id: str, min_ms: int, max_ms: int, exclude_sha256: str | None = None
    ) -> list[ImportBatch]: ...

    def commit_import(
        self, source: QuoteSource, batch: ImportBatch
    ) -> tuple[ImportBatch, bool]: ...


@dataclass(frozen=True, slots=True)
class ImportResult:
    status: str  # COMMITTED | ALREADY_IMPORTED
    batch: ImportBatch
    stats: BatchStats
    stored_path: Path


def source_metadata_json(raw_symbol: str) -> str:
    return canonical_json({"raw_symbol": raw_symbol})


def batch_relative_path(source_id: str, min_provider_ms: int, sha256: str) -> str:
    day = datetime.fromtimestamp(min_provider_ms / 1000, tz=UTC)
    return f"{MARKET_DIRNAME}/{source_id}/{day:%Y/%m/%d}/{sha256}.csv.gz"


def _stored_bytes_ok(path: Path, sha256: str) -> bool:
    try:
        return sha256_hex(gzip.decompress(path.read_bytes())) == sha256
    except (OSError, EOFError, gzip.BadGzipFile, zlib.error):
        return False


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:  # pragma: no cover - platform without directory fds
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_raw_batch(path: Path, data: bytes, sha256: str) -> None:
    """Persist ``data`` gzip-compressed (deterministic header) via temp file + atomic rename."""
    if path.exists() and _stored_bytes_ok(path, sha256):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with tmp.open("wb") as handle:
            handle.write(gzip.compress(data, mtime=0))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    _fsync_dir(path.parent)


def import_file(
    file_path: Path,
    *,
    source_id: str,
    origin: SourceOrigin | str,
    state_dir: Path,
    catalog: BatchCatalog,
    raw_symbol: str = CANONICAL_SYMBOL,
) -> ImportResult:
    """Validate and durably import one canonical CSV v1 file. Raises on any rejection."""
    parsed, data = read_and_parse(
        file_path, source_id=source_id, origin=origin, raw_symbol=raw_symbol
    )
    return import_parsed(parsed, data, state_dir=state_dir, catalog=catalog)


def read_and_parse(
    file_path: Path,
    *,
    source_id: str,
    origin: SourceOrigin | str,
    raw_symbol: str = CANONICAL_SYMBOL,
) -> tuple[ParsedBatch, bytes]:
    """Read the file once and validate it completely; no state is touched."""
    try:
        data = Path(file_path).read_bytes()
    except OSError as exc:
        raise CsvImportError(0, "--file", ImportRejectReason.FILE_UNREADABLE, str(exc)) from exc
    parsed = parse_canonical_csv(data, source_id=source_id, origin=origin, raw_symbol=raw_symbol)
    return parsed, data


def import_parsed(
    parsed: ParsedBatch, data: bytes, *, state_dir: Path, catalog: BatchCatalog
) -> ImportResult:
    if sha256_hex(data) != parsed.file_sha256:
        raise ValueError("data does not match the parsed batch checksum")
    stats = parsed.stats
    rel_path = batch_relative_path(parsed.source_id, stats.min_provider_ms, parsed.file_sha256)
    stored_path = state_dir / rel_path

    existing = catalog.find_batch(parsed.source_id, parsed.file_sha256)
    if existing is not None:
        # Idempotent no-op; also repair a missing/damaged raw file from identical bytes.
        write_raw_batch(state_dir / existing.path, data, parsed.file_sha256)
        return ImportResult("ALREADY_IMPORTED", existing, stats, state_dir / existing.path)

    now = catalog.now_ms()
    source = QuoteSource(
        source_id=parsed.source_id,
        kind=parsed.source_origin,
        symbol=CANONICAL_SYMBOL,
        metadata_json=source_metadata_json(parsed.raw_symbol),
        created_at_ms=now,
    )
    catalog.check_source_compatible(source)
    overlaps = catalog.overlapping_batches(
        parsed.source_id, stats.min_provider_ms, stats.max_provider_ms, parsed.file_sha256
    )
    if overlaps:
        raise CatalogError(
            ImportRejectReason.OVERLAPS_EXISTING_BATCH,
            f"provider-time range overlaps committed batch {overlaps[0].batch_id}; "
            "canonical CSV v1 has no provider event ID to separate retransmits",
        )

    write_raw_batch(stored_path, data, parsed.file_sha256)
    batch = ImportBatch(
        batch_id=make_batch_id(parsed.source_id, parsed.file_sha256),
        source_id=parsed.source_id,
        sha256=parsed.file_sha256,
        origin=parsed.source_origin,
        format_version=parsed.format_version,
        path=rel_path,
        min_provider_ms=stats.min_provider_ms,
        max_provider_ms=stats.max_provider_ms,
        quote_count=stats.row_count,
        status=BATCH_STATUS_COMMITTED,
        imported_at_ms=now,
        stats_json=canonical_json(asdict(stats)),
    )
    committed, created = catalog.commit_import(source, batch)
    status = "COMMITTED" if created else "ALREADY_IMPORTED"
    return ImportResult(status, committed, stats, state_dir / committed.path)


def read_batch_quotes(
    state_dir: Path, source: QuoteSource, batch: ImportBatch
) -> tuple[NormalizedQuote, ...]:
    """Reload a committed batch's normalized quotes from its immutable raw file (verified)."""
    path = state_dir / batch.path
    try:
        data = gzip.decompress(path.read_bytes())
    except (OSError, EOFError, gzip.BadGzipFile, zlib.error) as exc:
        raise BatchIntegrityError(f"stored batch unreadable: {path}") from exc
    if sha256_hex(data) != batch.sha256:
        raise BatchIntegrityError(f"stored batch checksum mismatch: {path}")
    raw_symbol = json.loads(source.metadata_json)["raw_symbol"]
    parsed = parse_canonical_csv(
        data, source_id=batch.source_id, origin=batch.origin, raw_symbol=raw_symbol
    )
    if len(parsed.quotes) != batch.quote_count:
        raise BatchIntegrityError(f"stored batch row count mismatch: {path}")
    return parsed.quotes


class SourceReader(Protocol):
    """Read-only catalog access needed to reload a source's committed quotes."""

    def get_source(self, source_id: str) -> QuoteSource | None: ...

    def list_batches(self, source_id: str | None = None) -> list[ImportBatch]: ...


def load_source_quotes(
    catalog: SourceReader, state_dir: Path, source_id: str
) -> tuple[NormalizedQuote, ...]:
    """All committed quotes of one source, batch by batch in provider-time order (verified)."""
    source = catalog.get_source(source_id)
    if source is None:
        raise KeyError(f"source {source_id!r} not found in catalog")
    quotes: list[NormalizedQuote] = []
    for batch in catalog.list_batches(source_id):
        quotes.extend(read_batch_quotes(state_dir, source, batch))
    return tuple(quotes)
