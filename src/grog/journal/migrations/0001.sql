-- Grog schema migration 0001: durable quote source and import batch catalog (M01).
-- Contract: docs/09-architecture.md Section 7. Later tables (signals, positions,
-- research runs) are added by separate additive migrations. No wallet/order tables.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY CHECK (typeof(version) = 'integer'),
    applied_at_utc_ms INTEGER NOT NULL CHECK (typeof(applied_at_utc_ms) = 'integer')
);

CREATE TABLE quote_sources (
    source_id TEXT PRIMARY KEY NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('SYNTHETIC', 'HISTORICAL', 'BACKFILL', 'REFERENCE_LIVE')),
    symbol TEXT NOT NULL CHECK (symbol = 'XAUUSD'),
    metadata_json TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL CHECK (typeof(created_at_ms) = 'integer')
);

CREATE TABLE import_batches (
    batch_id TEXT PRIMARY KEY NOT NULL,
    source_id TEXT NOT NULL REFERENCES quote_sources (source_id),
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    origin TEXT NOT NULL CHECK (origin IN ('SYNTHETIC', 'HISTORICAL', 'BACKFILL', 'REFERENCE_LIVE')),
    format_version TEXT NOT NULL,
    path TEXT NOT NULL,
    min_provider_ms INTEGER NOT NULL CHECK (typeof(min_provider_ms) = 'integer'),
    max_provider_ms INTEGER NOT NULL CHECK (typeof(max_provider_ms) = 'integer'),
    quote_count INTEGER NOT NULL CHECK (typeof(quote_count) = 'integer' AND quote_count > 0),
    status TEXT NOT NULL CHECK (status IN ('COMMITTED')),
    imported_at_ms INTEGER NOT NULL CHECK (typeof(imported_at_ms) = 'integer'),
    stats_json TEXT NOT NULL,
    UNIQUE (source_id, sha256),
    CHECK (min_provider_ms <= max_provider_ms)
);

CREATE INDEX import_batches_source_range ON import_batches (source_id, min_provider_ms);

-- Source identity and committed batches are immutable historical records.
CREATE TRIGGER quote_sources_no_update BEFORE UPDATE ON quote_sources
BEGIN SELECT RAISE(ABORT, 'quote_sources rows are immutable'); END;
CREATE TRIGGER quote_sources_no_delete BEFORE DELETE ON quote_sources
BEGIN SELECT RAISE(ABORT, 'quote_sources rows are immutable'); END;
CREATE TRIGGER import_batches_no_update BEFORE UPDATE ON import_batches
BEGIN SELECT RAISE(ABORT, 'import_batches rows are immutable'); END;
CREATE TRIGGER import_batches_no_delete BEFORE DELETE ON import_batches
BEGIN SELECT RAISE(ABORT, 'import_batches rows are immutable'); END;
