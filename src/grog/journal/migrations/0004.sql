-- Grog schema migration 0004: one first operator action per signal (R0 audit F-06).
-- Contract: docs/09-architecture.md Section 7, docs/07 Section 8, docs/14 F-06.
-- Additive only. Existing manual_positions / position_events / signal_decisions rows are
-- never changed or deleted; this table is a uniqueness claim written in the same
-- transaction as the ENTRY event or USER_SKIPPED decision it refers to, so two writers can
-- never both record a first action (ENTERED vs USER_SKIPPED, or two on-plan entries) for
-- the same signal. No wallet/order tables.

CREATE TABLE signal_operator_actions (
    source_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('ENTERED', 'USER_SKIPPED')),
    action_id TEXT NOT NULL UNIQUE,
    position_id TEXT REFERENCES manual_positions (position_id),
    recorded_at_ms INTEGER NOT NULL CHECK (typeof(recorded_at_ms) = 'integer'),
    PRIMARY KEY (source_id, signal_id),
    CHECK ((action = 'ENTERED') = (position_id IS NOT NULL))
);

-- Backfill from already-recorded history, earliest record first. If a pre-0004 database
-- ever holds two first actions for one signal, both original rows stay untouched and the
-- earliest one becomes the claim (nothing is deleted or rewritten).
INSERT OR IGNORE INTO signal_operator_actions
    (source_id, signal_id, action, action_id, position_id, recorded_at_ms)
SELECT source_id, signal_id, action, action_id, position_id, recorded_at_ms FROM (
    SELECT source_id, signal_id, 'USER_SKIPPED' AS action, decision_id AS action_id,
        NULL AS position_id, recorded_at_ms
    FROM signal_decisions
    UNION ALL
    SELECT mp.source_id, mp.linked_signal_id, 'ENTERED', pe.event_id, mp.position_id,
        mp.entry_recorded_ms
    FROM manual_positions AS mp
    JOIN position_events AS pe ON pe.position_id = mp.position_id AND pe.sequence = 1
    WHERE mp.signal_link = 'PLAN' AND mp.linked_signal_id IS NOT NULL
) ORDER BY recorded_at_ms, action_id;

CREATE TRIGGER signal_operator_actions_no_update BEFORE UPDATE ON signal_operator_actions
BEGIN SELECT RAISE(ABORT, 'signal_operator_actions are append-only'); END;
CREATE TRIGGER signal_operator_actions_no_delete BEFORE DELETE ON signal_operator_actions
BEGIN SELECT RAISE(ABORT, 'signal_operator_actions are append-only'); END;
