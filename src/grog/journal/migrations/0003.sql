-- Grog schema migration 0003: local manual-position journal (M08).
-- Contract: docs/09-architecture.md Section 7 (manual_positions, position_events),
-- docs/07 Section 8 and docs/02 Section 9. Additive only: existing rows are untouched.
-- These rows are operator-recorded local journal data, NOT an account, wallet or
-- broker order. No orders/wallet tables.

CREATE TABLE manual_positions (
    position_id TEXT PRIMARY KEY NOT NULL,
    linked_signal_id TEXT,
    signal_link TEXT NOT NULL CHECK (signal_link IN ('PLAN', 'INFORMATIONAL', 'NONE')),
    source_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('REPLAY', 'REFERENCE')),
    source_fidelity TEXT NOT NULL CHECK (source_fidelity IN ('SIMULATED', 'MANUAL')),
    plan_status TEXT NOT NULL CHECK (plan_status IN ('ON_PLAN', 'OFF_PLAN')),
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    initial_qty_text TEXT NOT NULL,
    remaining_qty_text TEXT NOT NULL,
    entry_price_text TEXT NOT NULL,
    entry_ms INTEGER NOT NULL CHECK (typeof(entry_ms) = 'integer'),
    entry_recorded_ms INTEGER NOT NULL CHECK (typeof(entry_recorded_ms) = 'integer'),
    state TEXT NOT NULL CHECK (state IN ('MONITORING', 'RECONCILIATION_REQUIRED', 'CLOSED')),
    snapshot_json TEXT NOT NULL,
    updated_at_ms INTEGER NOT NULL CHECK (typeof(updated_at_ms) = 'integer'),
    CHECK (state != 'CLOSED' OR remaining_qty_text = '0'),
    CHECK (substr(remaining_qty_text, 1, 1) != '-')
);

CREATE INDEX manual_positions_signal ON manual_positions (linked_signal_id);

CREATE TABLE position_events (
    event_id TEXT PRIMARY KEY NOT NULL,
    position_id TEXT NOT NULL REFERENCES manual_positions (position_id),
    sequence INTEGER NOT NULL CHECK (typeof(sequence) = 'integer'),
    action_type TEXT NOT NULL CHECK (action_type IN ('ENTRY', 'PARTIAL_CLOSE', 'MODIFY',
        'CLOSE', 'RESTORED_UNVERIFIED', 'CONFIRMED_OPEN')),
    effective_at_ms INTEGER NOT NULL CHECK (typeof(effective_at_ms) = 'integer'),
    recorded_at_ms INTEGER NOT NULL CHECK (typeof(recorded_at_ms) = 'integer'),
    qty_text TEXT,
    price_text TEXT,
    fees_text TEXT,
    payload_json TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    UNIQUE (position_id, sequence)
);

-- Operator decisions on a signal that create no position (docs/02 §9 Skip: USER_SKIPPED,
-- distinct from system EXPIRED/MISSED). Append only.
CREATE TABLE signal_decisions (
    decision_id TEXT PRIMARY KEY NOT NULL,
    signal_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('REPLAY', 'REFERENCE')),
    decision TEXT NOT NULL CHECK (decision IN ('USER_SKIPPED')),
    effective_at_ms INTEGER NOT NULL CHECK (typeof(effective_at_ms) = 'integer'),
    recorded_at_ms INTEGER NOT NULL CHECK (typeof(recorded_at_ms) = 'integer'),
    reason TEXT,
    payload_json TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    UNIQUE (source_id, signal_id, decision)
);

CREATE TRIGGER position_events_no_update BEFORE UPDATE ON position_events
BEGIN SELECT RAISE(ABORT, 'position_events are append-only'); END;
CREATE TRIGGER position_events_no_delete BEFORE DELETE ON position_events
BEGIN SELECT RAISE(ABORT, 'position_events are append-only'); END;
CREATE TRIGGER manual_positions_no_delete BEFORE DELETE ON manual_positions
BEGIN SELECT RAISE(ABORT, 'manual positions are never deleted'); END;
CREATE TRIGGER manual_positions_identity_immutable BEFORE UPDATE OF position_id,
    linked_signal_id, signal_link, source_id, mode, source_fidelity, plan_status, side,
    initial_qty_text,
    entry_price_text, entry_ms, entry_recorded_ms ON manual_positions
BEGIN SELECT RAISE(ABORT, 'manual position entry record is immutable'); END;
CREATE TRIGGER manual_positions_closed_final BEFORE UPDATE ON manual_positions
WHEN OLD.state = 'CLOSED'
BEGIN SELECT RAISE(ABORT, 'closed manual positions are final'); END;
CREATE TRIGGER signal_decisions_no_update BEFORE UPDATE ON signal_decisions
BEGIN SELECT RAISE(ABORT, 'signal_decisions are append-only'); END;
CREATE TRIGGER signal_decisions_no_delete BEFORE DELETE ON signal_decisions
BEGIN SELECT RAISE(ABORT, 'signal_decisions are append-only'); END;
