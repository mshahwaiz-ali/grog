-- Grog schema migration 0002: research run records, SIMULATED signal records and
-- append-only replay events (M06). Contract: docs/09-architecture.md Section 7.
-- Research results are keyed by run and never mixed with real (manual) trades.
-- No wallet/order tables.

CREATE TABLE research_runs (
    run_id TEXT PRIMARY KEY NOT NULL,
    source_id TEXT NOT NULL REFERENCES quote_sources (source_id),
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    data_hash TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    run_key_json TEXT NOT NULL,
    window_from_ms INTEGER CHECK (window_from_ms IS NULL OR typeof(window_from_ms) = 'integer'),
    window_to_ms INTEGER CHECK (window_to_ms IS NULL OR typeof(window_to_ms) = 'integer'),
    source_fidelity TEXT NOT NULL CHECK (source_fidelity IN ('SIMULATED')),
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETE')),
    processed_quotes INTEGER NOT NULL CHECK (typeof(processed_quotes) = 'integer'),
    result_json TEXT,
    created_at_ms INTEGER NOT NULL CHECK (typeof(created_at_ms) = 'integer'),
    completed_at_ms INTEGER CHECK (completed_at_ms IS NULL OR typeof(completed_at_ms) = 'integer'),
    CHECK (status = 'RUNNING' OR result_json IS NOT NULL)
);

CREATE TABLE signal_records (
    run_id TEXT NOT NULL REFERENCES research_runs (run_id),
    signal_id TEXT NOT NULL,
    pair_key TEXT NOT NULL,
    version TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    first_ready_ms INTEGER NOT NULL CHECK (typeof(first_ready_ms) = 'integer'),
    immutable_plan_json TEXT NOT NULL,
    current_state TEXT NOT NULL CHECK (current_state IN ('READY', 'EXPIRED', 'INVALIDATED')),
    expires_ms INTEGER NOT NULL CHECK (typeof(expires_ms) = 'integer'),
    PRIMARY KEY (run_id, signal_id),
    UNIQUE (run_id, pair_key)
);

CREATE TABLE signal_events (
    event_id TEXT PRIMARY KEY NOT NULL,
    run_id TEXT NOT NULL REFERENCES research_runs (run_id),
    signal_id TEXT,
    event_type TEXT NOT NULL,
    effective_at_ms INTEGER NOT NULL CHECK (typeof(effective_at_ms) = 'integer'),
    recorded_at_ms INTEGER NOT NULL CHECK (typeof(recorded_at_ms) = 'integer'),
    reason_codes_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE
);

CREATE INDEX signal_events_run ON signal_events (run_id, effective_at_ms);

CREATE TRIGGER signal_events_no_update BEFORE UPDATE ON signal_events
BEGIN SELECT RAISE(ABORT, 'signal_events are append-only'); END;
CREATE TRIGGER signal_events_no_delete BEFORE DELETE ON signal_events
BEGIN SELECT RAISE(ABORT, 'signal_events are append-only'); END;
CREATE TRIGGER signal_records_plan_immutable BEFORE UPDATE OF immutable_plan_json, signal_id,
    pair_key, version, side, first_ready_ms, expires_ms, run_id ON signal_records
BEGIN SELECT RAISE(ABORT, 'signal_records original plan is immutable'); END;
CREATE TRIGGER signal_records_no_delete BEFORE DELETE ON signal_records
BEGIN SELECT RAISE(ABORT, 'signal_records are never deleted'); END;
CREATE TRIGGER research_runs_complete_immutable BEFORE UPDATE ON research_runs
WHEN OLD.status = 'COMPLETE'
BEGIN SELECT RAISE(ABORT, 'completed research runs are immutable'); END;
CREATE TRIGGER research_runs_no_delete BEFORE DELETE ON research_runs
BEGIN SELECT RAISE(ABORT, 'research runs are never deleted'); END;
