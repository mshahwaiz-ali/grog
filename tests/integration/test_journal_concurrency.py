"""R0 audit F-06 (docs/14): journal concurrency, first-action uniqueness and recovery.

Two independent SQLite connections (two Grog processes) write the same local journal.
Every validation must be repeated inside the ``BEGIN IMMEDIATE`` write transaction, and a
signal can receive at most one first operator action (ENTERED or USER_SKIPPED). The
deterministic race tests run the competing writer exactly in the gap between the caller's
pre-checks and its write transaction. Fixture values are declared test values only.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from grog.domain.clock import FixedClock
from grog.domain.enums import Side
from grog.journal.positions import (
    EntryRequest,
    JournalError,
    PlanRef,
    PositionJournal,
    PositionState,
    new_action_id,
)
from grog.journal.store import STATE_DB_FILENAME, Store, available_migrations

D = Decimal
T0 = 1_767_607_200_000
CLOCK = FixedClock(1_793_450_000_000)
SRC = "syn-1"
PLAN = PlanRef(
    signal_id="S1-BUY-race",
    source_id=SRC,
    strategy_version="S1_MTF_V0_2",
    side=Side.BUY,
    e0=D("4000.20"),
    sl0=D("3998.00"),
    tp1=D("4002.40"),
    tp2=D("4004.60"),
    entry_low=D("4000.20"),
    entry_high=D("4000.42"),
    original_risk=D("2.20"),
    first_ready_ms=T0,
    expiry_ms=T0 + 300_000,
    fidelity="SIMULATED",
)


def entry(plan: PlanRef | None = PLAN, **kw) -> EntryRequest:
    base = dict(
        action_id=new_action_id(),
        side=Side.BUY,
        price=D("4000.30"),
        qty=D("0.30"),
        fill_ms=T0 + 5_000,
        source_id=SRC,
        plan=plan,
        signal_ready=plan is not None,
    )
    base.update(kw)
    return EntryRequest(**base)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "state" / STATE_DB_FILENAME


@pytest.fixture
def pair(db: Path):
    a, b = Store.open(db, CLOCK), Store.open(db, CLOCK)
    yield PositionJournal(a), PositionJournal(b)
    a.close()
    b.close()


def interleave(journal: PositionJournal, competitor) -> list[object]:
    """Run ``competitor`` (another connection's write) once, right before ``journal``
    opens its write transaction — i.e. after any check done outside the transaction."""
    original = journal.store.transaction
    done: list[object] = []

    @contextmanager
    def racing():
        if not done:
            done.append(competitor())
        with original() as conn:
            yield conn

    journal.store.transaction = racing  # type: ignore[method-assign]
    return done


def rows(db: Path, sql: str) -> list[tuple]:
    conn = sqlite3.connect(db)
    try:
        return [tuple(r) for r in conn.execute(sql)]
    finally:
        conn.close()


def snapshot(db: Path) -> tuple:
    return tuple(
        rows(db, f"SELECT * FROM {t} ORDER BY 1")
        for t in (
            "manual_positions",
            "position_events",
            "signal_decisions",
            "signal_operator_actions",
        )
    )


# --------------------------------------------------------------------------- first action


def test_entry_racing_a_skip_on_another_connection_is_rejected(pair, db: Path) -> None:
    a, b = pair
    interleave(a, lambda: b.record_skip(new_action_id(), PLAN, effective_ms=T0 + 1))
    with pytest.raises(JournalError) as exc:
        a.record_entry(entry())
    assert exc.value.code == "SIGNAL_ALREADY_SKIPPED"
    assert rows(db, "SELECT count(*) FROM manual_positions") == [(0,)]
    assert rows(db, "SELECT action FROM signal_operator_actions") == [("USER_SKIPPED",)]


def test_two_on_plan_entries_racing_record_only_one(pair, db: Path) -> None:
    a, b = pair
    interleave(a, lambda: b.record_entry(entry()))
    with pytest.raises(JournalError) as exc:
        a.record_entry(entry())
    assert exc.value.code == "SIGNAL_ALREADY_ENTERED"
    assert rows(db, "SELECT count(*) FROM manual_positions WHERE signal_link='PLAN'") == [(1,)]


def test_skip_racing_an_entry_is_rejected(pair, db: Path) -> None:
    a, b = pair
    interleave(a, lambda: b.record_entry(entry()))
    with pytest.raises(JournalError) as exc:
        a.record_skip(new_action_id(), PLAN, effective_ms=T0 + 1)
    assert exc.value.code == "SIGNAL_ALREADY_ENTERED"
    assert rows(db, "SELECT count(*) FROM signal_decisions") == [(0,)]


def test_unlinked_entries_never_claim_a_signal(pair) -> None:
    a, _ = pair
    a.record_entry(entry(plan=None, informational_signal_id=PLAN.signal_id))
    a.record_entry(entry(plan=None, informational_signal_id=PLAN.signal_id))
    assert a.signal_status(SRC, PLAN.signal_id) is None
    pos, created = a.record_entry(entry())  # the on-plan entry is still the first action
    assert created and a.signal_status(SRC, PLAN.signal_id) == "ENTERED"
    assert a.signal_actions(SRC) == {PLAN.signal_id: ("ENTERED", pos.position_id)}


def test_threaded_writers_never_record_conflicting_first_actions(db: Path) -> None:
    Store.open(db, CLOCK).close()  # migrate once
    plans = [replace(PLAN, signal_id=f"S1-BUY-{i:03d}") for i in range(25)]
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker(kind: str) -> None:
        store = Store.open(db, CLOCK)
        j = PositionJournal(store)
        try:
            for p in plans:
                barrier.wait()
                try:
                    if kind == "entry":
                        j.record_entry(entry(plan=p))
                    else:
                        j.record_skip(new_action_id(), p, effective_ms=T0 + 1)
                except JournalError as exc:
                    assert exc.code.startswith("SIGNAL_ALREADY_") or exc.code == "NOT_SAVED"
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)
        finally:
            store.close()

    threads = [threading.Thread(target=worker, args=(k,)) for k in ("entry", "skip")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    entered = {r[0] for r in rows(db, "SELECT linked_signal_id FROM manual_positions")}
    skipped = {r[0] for r in rows(db, "SELECT signal_id FROM signal_decisions")}
    assert not entered & skipped
    claims = rows(db, "SELECT signal_id, action FROM signal_operator_actions")
    assert len(claims) == len(entered) + len(skipped) == len({c[0] for c in claims})


# --------------------------------------------------------------------------- positions


def test_partial_racing_another_partial_is_validated_inside_the_transaction(pair, db: Path) -> None:
    a, b = pair
    pos, _ = a.record_entry(entry())
    interleave(
        a,
        lambda: b.record_partial(
            new_action_id(), pos.position_id, price=D("4001"), qty=D("0.05"), fill_ms=T0 + 6_000
        ),
    )
    p, created = a.record_partial(
        new_action_id(), pos.position_id, price=D("4001.5"), qty=D("0.20"), fill_ms=T0 + 7_000
    )
    assert created and p.remaining_qty == D("0.05")
    assert rows(db, "SELECT sequence FROM position_events ORDER BY sequence") == [(1,), (2,), (3,)]


def test_stale_close_after_concurrent_partial_is_rejected_unchanged(pair, db: Path) -> None:
    a, b = pair
    pos, _ = a.record_entry(entry())
    interleave(
        a,
        lambda: b.record_partial(
            new_action_id(), pos.position_id, price=D("4001"), qty=D("0.10"), fill_ms=T0 + 6_000
        ),
    )
    with pytest.raises(JournalError) as exc:
        a.record_close(
            new_action_id(), pos.position_id, price=D("4002"), qty=D("0.30"), fill_ms=T0 + 7_000
        )
    assert exc.value.code in ("QTY_EXCEEDS_REMAINING", "CLOSE_QTY_MISMATCH")
    before = a.get(pos.position_id)
    assert before.remaining_qty == D("0.20") and before.state is PositionState.MONITORING


def test_close_racing_a_close_cannot_close_twice(pair) -> None:
    a, b = pair
    pos, _ = a.record_entry(entry())
    interleave(
        a,
        lambda: b.record_close(
            new_action_id(), pos.position_id, price=D("4001"), qty=D("0.30"), fill_ms=T0 + 6_000
        ),
    )
    with pytest.raises(JournalError) as exc:
        a.record_close(
            new_action_id(), pos.position_id, price=D("4002"), qty=D("0.30"), fill_ms=T0 + 7_000
        )
    assert exc.value.code == "POSITION_CLOSED"
    assert len(a.events(pos.position_id)) == 2


def test_identical_resubmission_from_two_connections_is_idempotent(pair, db: Path) -> None:
    a, b = pair
    pos, _ = a.record_entry(entry())
    kw = dict(price=D("4001"), qty=D("0.10"), fill_ms=T0 + 6_000)
    interleave(a, lambda: b.record_partial("same-action", pos.position_id, **kw))
    p, created = a.record_partial("same-action", pos.position_id, **kw)
    assert not created and p.remaining_qty == D("0.20")
    assert len(a.events(pos.position_id)) == 2
    with pytest.raises(JournalError) as exc:  # same ID, different content: rejected
        a.record_partial("same-action", pos.position_id, **(kw | {"qty": D("0.05")}))
    assert exc.value.code == "DUPLICATE_ACTION_ID"


def test_modify_and_confirm_validate_inside_the_transaction(pair) -> None:
    a, b = pair
    pos, _ = a.record_entry(entry())
    interleave(
        a,
        lambda: b.record_close(
            new_action_id(), pos.position_id, price=D("4001"), qty=D("0.30"), fill_ms=T0 + 6_000
        ),
    )
    with pytest.raises(JournalError) as exc:
        a.record_modify(
            new_action_id(), pos.position_id, effective_ms=T0 + 7_000, new_stop=D("3999")
        )
    assert exc.value.code == "POSITION_CLOSED"


def test_two_instances_restoring_at_startup_write_one_event(db: Path) -> None:
    with Store.open(db, CLOCK) as s:
        pos, _ = PositionJournal(s).record_entry(entry())
    a, b = Store.open(db, CLOCK), Store.open(db, CLOCK)
    try:
        ja, jb = PositionJournal(a), PositionJournal(b)
        interleave(ja, jb.restore_on_startup)
        restored = ja.restore_on_startup()
        assert [p.state for p in restored] == [PositionState.RECONCILIATION_REQUIRED]
        actions = [e.action.value for e in ja.events(pos.position_id)]
        assert actions == ["ENTRY", "RESTORED_UNVERIFIED"]
    finally:
        a.close()
        b.close()


# --------------------------------------------------------------------------- recovery


def test_failure_after_event_insert_rolls_back_entry_and_claim_then_retry_saves(
    db: Path,
) -> None:
    with Store.open(db, CLOCK) as s:
        j = PositionJournal(s)
        before = snapshot(db)
        req = entry()
        j._inject_failure = "after_event"
        with pytest.raises(JournalError) as exc:
            j.record_entry(req)
        assert exc.value.code == "NOT_SAVED"
        assert snapshot(db) == before
        j._inject_failure = None
        pos, created = j.record_entry(req)  # same action ID retried after the failure
        assert created and j.signal_status(SRC, PLAN.signal_id) == "ENTERED"
        assert j.record_entry(req) == (pos, False)


def test_failure_during_skip_rolls_back_and_retry_saves(db: Path) -> None:
    with Store.open(db, CLOCK) as s:
        j = PositionJournal(s)
        j._inject_failure = "after_event"
        with pytest.raises(JournalError):
            j.record_skip("skip-1", PLAN, effective_ms=T0 + 1)
        assert j.signal_status(SRC, PLAN.signal_id) is None and j.decisions() == []
        j._inject_failure = None
        rec, created = j.record_skip("skip-1", PLAN, effective_ms=T0 + 1)
        assert created and rec.decision == "USER_SKIPPED"


def test_claims_are_append_only(db: Path) -> None:
    with Store.open(db, CLOCK) as s:
        PositionJournal(s).record_skip(new_action_id(), PLAN, effective_ms=T0)
        for sql in ("UPDATE signal_operator_actions SET action='ENTERED'",
                    "DELETE FROM signal_operator_actions"):  # fmt: skip
            with pytest.raises(sqlite3.DatabaseError):
                s._conn.execute(sql)


def test_migration_0004_backfills_history_without_rewriting_it(db: Path) -> None:
    v3 = [m for m in available_migrations() if m[0] <= 3]
    with Store.open(db, CLOCK, migrations=v3) as s:
        j = PositionJournal(s)
        assert s.schema_versions() == [1, 2, 3]
        # Pre-0004 history written through the base tables only (no claims table yet).
        pos, _ = j.record_entry(entry())
        j.record_skip("old-skip", replace(PLAN, signal_id="S1-SELL-old"), effective_ms=T0)
        # A legacy conflict (possible before F-06 was fixed): skip after an entry.
        s._conn.execute(
            "INSERT INTO signal_decisions VALUES ('conflict', ?, ?, 'REPLAY', 'USER_SKIPPED',"
            " ?, ?, NULL, '{}', 'conflict')",
            (PLAN.signal_id, SRC, T0 + 9, CLOCK.now_ms() + 1),
        )
    base_before = snapshot_base(db)
    with Store.open(db, CLOCK) as s:
        assert s.schema_versions() == [1, 2, 3, 4]
        j = PositionJournal(s)
        assert j.signal_actions(SRC) == {
            PLAN.signal_id: ("ENTERED", pos.position_id),
            "S1-SELL-old": ("USER_SKIPPED", None),
        }
    assert snapshot_base(db) == base_before
    assert db.with_name(f"{STATE_DB_FILENAME}.pre-migration-v3.bak").is_file()


def snapshot_base(db: Path) -> tuple:
    return tuple(
        rows(db, f"SELECT * FROM {t} ORDER BY 1")
        for t in ("manual_positions", "position_events", "signal_decisions")
    )
