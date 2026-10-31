"""M08 local manual-position journal (docs/07 §1, §5-§8; docs/09 §3.6, §7; docs/02 §9).

Covers ST-01..ST-08 and ST-15 at the journal-service layer; UI-15..21 live in tests/ui.
Fixture values are the documented docs/07 §5 illustration, not a live quote.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from grog.analysis.params import CALC_CONTEXT
from grog.domain.clock import FixedClock
from grog.domain.enums import Side, SourceOrigin
from grog.domain.models import NormalizedQuote
from grog.journal.positions import (
    EntryRequest,
    JournalError,
    PlanRef,
    PlanStatus,
    PositionAction,
    PositionJournal,
    PositionState,
    TouchTracker,
    entry_preview,
    exit_preview,
    mark_position,
    new_action_id,
    observations,
    parse_amount,
    stop_further_away,
)
from grog.journal.store import STATE_DB_FILENAME, Store, available_migrations
from grog.risk.quotes_and_plans import ContractSpec

D = Decimal
T0 = 1_767_607_200_000  # 2026-01-05 10:00:00 UTC (fixture)
CLOCK = FixedClock(1_793_450_000_000)
SRC = "syn-1"

# docs/07 §5: READY BID 4000.00 / ASK 4000.20, BUY E0 4000.20, SL 3998.00, TP2 4004.60.
PLAN = PlanRef(
    signal_id="S1-BUY-fixture",
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


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "state" / STATE_DB_FILENAME


@pytest.fixture
def journal(db: Path):
    store = Store.open(db, CLOCK)
    yield PositionJournal(store)
    store.close()


def entry(**kw) -> EntryRequest:
    base = dict(
        action_id=new_action_id(),
        side=Side.BUY,
        price=D("4000.30"),
        qty=D("0.30"),
        fill_ms=T0 + 5_000,
        source_id=SRC,
        plan=PLAN,
        signal_ready=True,
    )
    base.update(kw)
    return EntryRequest(**base)


def table(db: Path, name: str) -> list[tuple]:
    conn = sqlite3.connect(db)
    try:
        return [tuple(r) for r in conn.execute(f"SELECT * FROM {name} ORDER BY 1")]
    finally:
        conn.close()


def journal_state(db: Path) -> tuple:
    return tuple(table(db, t) for t in ("manual_positions", "position_events", "signal_decisions"))


# --------------------------------------------------------------------------- schema


def test_st01_schema_v3_tables_foreign_keys_no_wallet_or_orders(journal: PositionJournal) -> None:
    conn = journal.store._conn
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"manual_positions", "position_events", "signal_decisions"} <= names
    assert not {n for n in names if any(w in n for w in ("wallet", "order", "account"))}
    assert journal.store.schema_versions() == [v for v, _ in available_migrations()]
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO position_events VALUES ('e','missing',1,'MODIFY',1,1,NULL,NULL,NULL,"
            "'{}','e')"
        )


def test_st15_additive_migration_preserves_history_and_backs_up(db: Path) -> None:
    v2 = [m for m in available_migrations() if m[0] <= 2]
    with Store.open(db, CLOCK, migrations=v2) as store:
        with store.transaction() as conn:
            conn.execute(
                "INSERT INTO quote_sources VALUES (?,?,?,?,?)",
                (SRC, "SYNTHETIC", "XAUUSD", "{}", 1),
            )
        assert store.schema_versions() == [1, 2]
    before = table(db, "quote_sources")
    with Store.open(db, CLOCK) as store:
        assert store.schema_versions() == [1, 2, 3]
    assert table(db, "quote_sources") == before
    backup = db.with_name(f"{STATE_DB_FILENAME}.pre-migration-v2.bak")
    assert backup.is_file()
    conn = sqlite3.connect(backup)
    try:
        assert conn.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 2
        assert conn.execute("SELECT source_id FROM quote_sources").fetchall() == [(SRC,)]
    finally:
        conn.close()
    with Store.open(db, CLOCK) as store:  # re-open: idempotent, no new backup churn
        assert store.schema_versions() == [1, 2, 3]


# --------------------------------------------------------------------------- validation


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("", "MISSING_VALUE"),
        ("  ", "MISSING_VALUE"),
        ("-1", "INVALID_NUMBER"),
        ("0", "INVALID_NUMBER"),
        ("NaN", "INVALID_NUMBER"),
        ("Infinity", "INVALID_NUMBER"),
        ("abc", "INVALID_NUMBER"),
        ("--1", "INVALID_NUMBER"),
    ],
)
def test_missing_negative_or_nonfinite_amounts_rejected(text: str, code: str) -> None:
    with pytest.raises(JournalError) as exc:
        parse_amount(text, "qty")
    assert exc.value.code == code


def test_blank_optional_fee_is_unknown_never_zero() -> None:
    assert parse_amount("", "fees", required=False, allow_zero=True) is None
    assert parse_amount("0", "fees", required=False, allow_zero=True) == 0
    with pytest.raises(JournalError):
        parse_amount("-0.5", "fees", required=False, allow_zero=True)


def test_service_rejects_nonpositive_values_without_writing(
    journal: PositionJournal, db: Path
) -> None:
    before = journal_state(db)
    for bad in (dict(qty=D("0")), dict(qty=D("-1")), dict(price=D("-4000")), dict(fees=D("-1"))):
        with pytest.raises(JournalError):
            journal.record_entry(entry(**bad))
    assert journal_state(db) == before


# --------------------------------------------------------------------------- entries


def test_on_plan_entry_keeps_original_plan(journal: PositionJournal) -> None:
    pos, created = journal.record_entry(entry())
    assert created and pos.plan_status is PlanStatus.ON_PLAN and pos.off_plan_reasons == ()
    assert pos.state is PositionState.MONITORING
    assert pos.linked_signal_id == PLAN.signal_id and pos.signal_link == "PLAN"
    assert pos.initial_risk == D("2.30") and pos.current_sl == PLAN.sl0
    assert pos.plan == PLAN  # frozen copy, unchanged
    assert pos.fees_text == "UNKNOWN"  # no fee fabricated
    assert pos.fidelity == "SIMULATED" and pos.mode == "REPLAY"


def test_late_off_plan_fill_changes_actual_r_not_original_signal(journal: PositionJournal) -> None:
    """docs/07 §5: late ASK 4001.10 -> actual risk 3.10, reward 3.50, ~1.13R before fees."""
    prev = entry_preview(Side.BUY, D("4001.10"), T0 + 400_000, PLAN, signal_ready=True)
    assert prev.plan_status is PlanStatus.OFF_PLAN
    assert set(prev.off_plan_reasons) == {"OUTSIDE_ENTRY_BAND", "AFTER_SIGNAL_EXPIRY"}
    assert prev.original_risk == D("2.20") and prev.original_target_r == D("2")
    assert prev.actual_risk == D("3.10")
    assert prev.actual_target_r.quantize(D("0.01")) == D("1.13")
    assert prev.entry_difference == D("0.90")
    pos, _ = journal.record_entry(entry(price=D("4001.10"), fill_ms=T0 + 400_000))
    assert pos.plan_status is PlanStatus.OFF_PLAN and pos.initial_risk == D("3.10")
    assert pos.plan == PLAN and pos.plan.e0 == D("4000.20") and pos.plan.tp2 == D("4004.60")
    assert pos.current_tp == PLAN.tp2  # never enlarged to restore 2R


def test_ui21_unlinked_off_plan_entry_informational_link(journal: PositionJournal) -> None:
    req = entry(
        plan=None,
        signal_ready=False,
        informational_signal_id="S1-SELL-expired",
        side=Side.SELL,
        price=D("3990.00"),
        stop=None,
    )
    pos, _ = journal.record_entry(req)
    assert pos.plan_status is PlanStatus.OFF_PLAN
    assert pos.off_plan_reasons == ("NO_READY_SIGNAL_LINK",)
    assert pos.signal_link == "INFORMATIONAL" and pos.linked_signal_id == "S1-SELL-expired"
    assert pos.initial_risk is None and pos.realized_r is None  # no stop -> risk UNKNOWN
    # The informational link never counts as an entry on that signal.
    assert journal.signal_status(SRC, "S1-SELL-expired") is None


def test_stop_target_differences_and_blocked_signal_are_off_plan() -> None:
    p = entry_preview(Side.BUY, D("4000.30"), T0 + 1, PLAN, stop=D("3997"), signal_ready=True)
    assert p.off_plan_reasons == ("STOP_DIFFERS_FROM_PLAN",) and p.actual_risk == D("3.30")
    p = entry_preview(Side.BUY, D("4000.30"), T0 + 1, PLAN, signal_ready=True, signal_blocked=True)
    assert "EXECUTION_BLOCKED_AT_RECORD" in p.off_plan_reasons
    p = entry_preview(Side.BUY, D("3997.50"), T0 + 1, PLAN, signal_ready=True)
    assert p.actual_risk is None and any("WRONG_SIDE" in w for w in p.warnings)
    p = entry_preview(Side.BUY, D("4000.30"), T0 + 10, PLAN, signal_ready=True, known_clock_ms=T0)
    assert "FILL_TIME_AHEAD_OF_KNOWN_CLOCK" in p.warnings


def test_st05_duplicate_submission_is_idempotent(journal: PositionJournal, db: Path) -> None:
    req = entry()
    first, created = journal.record_entry(req)
    again, created2 = journal.record_entry(req)
    assert created and not created2 and again == first
    assert len(journal.positions()) == 1 and len(journal.events()) == 1
    with pytest.raises(JournalError) as exc:
        journal.record_entry(replace(req, qty=D("0.5")))
    assert exc.value.code == "DUPLICATE_ACTION_ID"
    pid = first.position_id
    aid = new_action_id()
    journal.record_partial(aid, pid, price=D("4002"), qty=D("0.1"), fill_ms=T0 + 60_000)
    state = journal_state(db)
    _, created3 = journal.record_partial(
        aid, pid, price=D("4002"), qty=D("0.1"), fill_ms=T0 + 60_000
    )
    assert not created3 and journal_state(db) == state
    assert journal.get(pid).remaining_qty == D("0.2")


def test_second_on_plan_entry_or_skip_on_same_signal_rejected(journal: PositionJournal) -> None:
    journal.record_entry(entry())
    with pytest.raises(JournalError) as exc:
        journal.record_entry(entry())
    assert exc.value.code == "SIGNAL_ALREADY_ENTERED"
    with pytest.raises(JournalError):
        journal.record_skip(new_action_id(), PLAN, effective_ms=T0 + 1)


def test_skip_is_user_skipped_and_blocks_on_plan_entry(journal: PositionJournal) -> None:
    aid = new_action_id()
    rec, created = journal.record_skip(aid, PLAN, effective_ms=T0 + 1_000, reason="spread")
    assert created and rec.decision == "USER_SKIPPED" and rec.reason == "spread"
    assert journal.record_skip(aid, PLAN, effective_ms=T0 + 1_000, reason="spread")[1] is False
    assert journal.signal_status(SRC, PLAN.signal_id) == "USER_SKIPPED"
    with pytest.raises(JournalError) as exc:
        journal.record_entry(entry())
    assert exc.value.code == "SIGNAL_ALREADY_SKIPPED"
    assert journal.positions() == []


# --------------------------------------------------------------------------- partial / close


def test_ui16_partial_quantity_exceeding_remaining_rejected_db_unchanged(
    journal: PositionJournal, db: Path
) -> None:
    pos, _ = journal.record_entry(entry())
    before = journal_state(db)
    for qty in (D("0.31"), D("5")):
        with pytest.raises(JournalError) as exc:
            journal.record_partial(
                new_action_id(), pos.position_id, price=D("4001"), qty=qty, fill_ms=T0 + 9_000
            )
        assert exc.value.code == "QTY_EXCEEDS_REMAINING"
    with pytest.raises(JournalError):
        journal.record_partial(
            new_action_id(), pos.position_id, price=D("4001"), qty=D("0.1"), fill_ms=T0
        )  # before entry fill time
    assert journal_state(db) == before


def test_st07_partials_close_remaining_and_fees(journal: PositionJournal) -> None:
    pos, _ = journal.record_entry(entry(fees=D("1.50")))
    pid = pos.position_id
    p1, _ = journal.record_partial(
        new_action_id(),
        pid,
        price=D("4002.40"),
        qty=D("0.10"),
        fill_ms=T0 + 60_000,
        fees=D("0.50"),
    )
    assert p1.remaining_qty == D("0.20") and p1.state is PositionState.MONITORING
    p2, _ = journal.record_partial(
        new_action_id(), pid, price=D("3999.30"), qty=D("0.05"), fill_ms=T0 + 90_000
    )
    assert p2.remaining_qty == D("0.15")
    assert p2.fees_known == D("2.00") and p2.fees_text == "2 + UNKNOWN"
    with pytest.raises(JournalError) as exc:
        journal.record_close(
            new_action_id(), pid, price=D("4004.60"), qty=D("0.10"), fill_ms=T0 + 120_000
        )
    assert exc.value.code == "CLOSE_QTY_MISMATCH"
    closed, _ = journal.record_close(
        new_action_id(),
        pid,
        price=D("4004.60"),
        qty=D("0.15"),
        fill_ms=T0 + 120_000,
        fees=D("0.40"),
    )
    assert closed.state is PositionState.CLOSED and closed.remaining_qty == 0
    # realized gross price units: 0.21 - 0.05 + 0.645 (exit - entry) x qty
    assert closed.realized_price_units == D("0.2100") + D("-0.0500") + D("0.6450")
    assert closed.realized_r == CALC_CONTEXT.divide(closed.realized_price_units, D("0.690"))
    assert closed.fees_text == "2.4 + UNKNOWN"
    actions = [e.action for e in journal.events(pid)]
    assert actions == [
        PositionAction.ENTRY,
        PositionAction.PARTIAL_CLOSE,
        PositionAction.PARTIAL_CLOSE,
        PositionAction.CLOSE,
    ]
    with pytest.raises(JournalError) as exc:
        journal.record_partial(
            new_action_id(), pid, price=D("4005"), qty=D("0.01"), fill_ms=T0 + 200_000
        )
    assert exc.value.code == "POSITION_CLOSED"


def test_partial_equal_to_remaining_must_use_close(journal: PositionJournal) -> None:
    pos, _ = journal.record_entry(entry())
    with pytest.raises(JournalError) as exc:
        journal.record_partial(
            new_action_id(), pos.position_id, price=D("4001"), qty=D("0.30"), fill_ms=T0 + 9_000
        )
    assert exc.value.code == "PARTIAL_IS_FULL"


def test_st08_bid_ask_path_charges_spread_once_commissions_separate(
    journal: PositionJournal,
) -> None:
    """Long enters at ASK and exits at BID: spread already inside the price difference."""
    pos, _ = journal.record_entry(entry(price=D("4000.20"), qty=D("1"), fees=D("3")))
    remaining, units, r = exit_preview(pos, D("4000.00"), D("1"))  # immediate exit at BID
    assert units == D("-0.20") and remaining == 0  # exactly one spread, no extra deduction
    assert r == CALC_CONTEXT.divide(D("-0.20"), D("2.20"))
    closed, _ = journal.record_close(
        new_action_id(),
        pos.position_id,
        price=D("4000.00"),
        qty=D("1"),
        fill_ms=T0 + 6_000,
        fees=D("3"),
    )
    assert closed.realized_price_units == D("-0.20")  # commission never mixed into price P/L
    assert closed.fees_known == D("6")


def test_st09_currency_pnl_unknown_without_contract_known_with_fixture_contract(
    journal: PositionJournal,
) -> None:
    pos, _ = journal.record_entry(entry(price=D("4000.20"), qty=D("0.5")))
    q = NormalizedQuote(
        source_id=SRC,
        canonical_symbol="XAUUSD",
        raw_symbol="XAUUSD",
        provider_time_ms=T0 + 30_000,
        received_time_ms=T0 + 30_000,
        ingest_order=1,
        bid=D("4001.20"),
        ask=D("4001.40"),
        source_origin=SourceOrigin.SYNTHETIC,
        source_event_key="k",
    )
    m = mark_position(pos, q)
    assert m.closeable == D("4001.20") and m.closeable_side == "BID"
    assert m.unrealized_price_units == D("0.50") and m.unrealized_r == CALC_CONTEXT.divide(
        D("0.50") / D("0.5"), D("2.20")
    )
    assert m.money is not None and m.money.native_amount is None  # UNKNOWN, not 0
    fixture_contract = ContractSpec(D("100"), "USD")  # declared test fixture only
    m2 = mark_position(pos, q, contract=fixture_contract)
    assert m2.money.native_amount == D("50.0") and m2.money.native_currency == "USD"
    early = replace(q, received_time_ms=T0, provider_time_ms=T0)
    assert mark_position(pos, early).closeable is None
    assert mark_position(pos, None).reason.startswith("monitoring UNAVAILABLE")
    assert "STALE" in mark_position(pos, q, stale=True).reason


# --------------------------------------------------------------------------- modify


def test_modify_records_stop_target_and_flags_further_away(journal: PositionJournal) -> None:
    pos, _ = journal.record_entry(entry())
    assert stop_further_away(pos, D("3997.00")) and not stop_further_away(pos, D("3999.00"))
    mod, _ = journal.record_modify(
        new_action_id(),
        pos.position_id,
        effective_ms=T0 + 30_000,
        new_stop=D("3997.00"),
        note="widened at broker",
    )
    assert mod.current_sl == D("3997.00") and mod.initial_sl == PLAN.sl0
    assert mod.initial_risk == D("2.30")  # original risk snapshot never rewritten
    ev = journal.events(pos.position_id)[-1]
    assert ev.action is PositionAction.MODIFY and ev.payload["further_away"] is True
    with pytest.raises(JournalError) as exc:
        journal.record_modify(new_action_id(), pos.position_id, effective_ms=T0 + 30_000)
    assert exc.value.code == "MISSING_VALUE"


# --------------------------------------------------------------------------- restart / failures


def test_st06_ui18_restart_restores_reconciliation_required(db: Path) -> None:
    with Store.open(db, CLOCK) as store:
        j = PositionJournal(store)
        open_pos, _ = j.record_entry(entry())
        closed, _ = j.record_entry(entry(plan=None, signal_ready=False))
        j.record_close(
            new_action_id(), closed.position_id, price=D("4001"), qty=D("0.30"), fill_ms=T0 + 9_000
        )
    with Store.open(db, CLOCK) as store:
        j = PositionJournal(store)
        restored = j.restore_on_startup()
        assert [p.position_id for p in restored] == [open_pos.position_id]
        assert restored[0].state is PositionState.RECONCILIATION_REQUIRED
        assert j.get(closed.position_id).state is PositionState.CLOSED
        n_events = len(j.events())
        j.restore_on_startup()  # already unverified: no duplicate event
        assert len(j.events()) == n_events
        with pytest.raises(JournalError):
            j.confirm_open(new_action_id(), closed.position_id, effective_ms=T0)
        ok, _ = j.confirm_open(new_action_id(), open_pos.position_id, effective_ms=T0 + 10)
        assert ok.state is PositionState.MONITORING
        with pytest.raises(JournalError) as exc:
            j.confirm_open(new_action_id(), open_pos.position_id, effective_ms=T0 + 10)
        assert exc.value.code == "NOT_REQUIRED"
    with Store.open(db, CLOCK) as store:  # every program start requires verification again
        assert PositionJournal(store).restore_on_startup()[0].state.value == (
            "RECONCILIATION_REQUIRED"
        )


def test_recording_an_action_on_unverified_position_verifies_it(db: Path) -> None:
    with Store.open(db, CLOCK) as store:
        PositionJournal(store).record_entry(entry())
    with Store.open(db, CLOCK) as store:
        j = PositionJournal(store)
        (pos,) = j.restore_on_startup()
        p, _ = j.record_partial(
            new_action_id(), pos.position_id, price=D("4001"), qty=D("0.1"), fill_ms=T0 + 9_000
        )
        assert p.state is PositionState.MONITORING and p.remaining_qty == D("0.2")


def test_st04_failure_mid_transaction_leaves_no_partial_change(
    journal: PositionJournal, db: Path
) -> None:
    pos, _ = journal.record_entry(entry())
    before = journal_state(db)
    with pytest.raises(JournalError) as exc:
        journal._exit(
            PositionAction.PARTIAL_CLOSE,
            new_action_id(),
            pos.position_id,
            D("4001"),
            D("0.1"),
            T0 + 9_000,
            None,
            None,
            _fail_after_event=True,
        )
    assert exc.value.code == "NOT_SAVED" and "NOT saved" in exc.value.message
    assert journal_state(db) == before
    assert journal.get(pos.position_id).remaining_qty == D("0.30")


def test_db_lock_rolls_back_and_reports_not_saved(db: Path) -> None:
    with Store.open(db, CLOCK) as store:
        pos, _ = PositionJournal(store).record_entry(entry())
    store = Store.open(db, CLOCK, busy_timeout_ms=50)
    j = PositionJournal(store)
    other = sqlite3.connect(db, isolation_level=None)
    try:
        before = journal_state(db)
        other.execute("BEGIN IMMEDIATE")
        with pytest.raises(JournalError) as exc:
            j.record_partial(
                new_action_id(), pos.position_id, price=D("4001"), qty=D("0.1"), fill_ms=T0 + 9_000
            )
        assert exc.value.code == "NOT_SAVED"
        with pytest.raises(JournalError):
            j.record_entry(entry(plan=None, signal_ready=False))
        other.execute("ROLLBACK")
        assert journal_state(db) == before
        # After the lock clears the same action can be retried and saved once.
        j.record_partial(
            "retry-1", pos.position_id, price=D("4001"), qty=D("0.1"), fill_ms=T0 + 9_000
        )
        assert j.get(pos.position_id).remaining_qty == D("0.2")
    finally:
        other.close()
        store.close()


def test_events_and_entry_identity_are_append_only(journal: PositionJournal) -> None:
    pos, _ = journal.record_entry(entry())
    conn = journal.store._conn
    for sql in (
        "UPDATE position_events SET price_text = '1'",
        "DELETE FROM position_events",
        "DELETE FROM manual_positions",
        "UPDATE manual_positions SET entry_price_text = '1'",
    ):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(sql)
    journal.record_skip(new_action_id(), replace(PLAN, signal_id="other"), effective_ms=T0)
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM signal_decisions")


# --------------------------------------------------------------------------- observations


def _quote(t: int, bid: str, ask: str) -> NormalizedQuote:
    return NormalizedQuote(
        source_id=SRC,
        canonical_symbol="XAUUSD",
        raw_symbol="XAUUSD",
        provider_time_ms=t,
        received_time_ms=t,
        ingest_order=t,
        bid=D(bid),
        ask=D(ask),
        source_origin=SourceOrigin.SYNTHETIC,
        source_event_key=f"k{t}",
    )


def test_touch_tracker_records_observations_only(journal: PositionJournal) -> None:
    pos, _ = journal.record_entry(entry(h1_bias_at_entry="UP"))
    tracker = TouchTracker()
    tracker.track(journal.open_positions())
    tracker.on_quote(_quote(T0, "3990", "3990.2"))  # before the fill: ignored
    assert tracker.touched(pos) == {}
    tracker.on_quote(_quote(T0 + 6_000, "4002.40", "4002.60"))  # BID reaches TP1
    tracker.on_quote(_quote(T0 + 7_000, "3998.00", "3998.20"))  # BID reaches SL
    assert tracker.touched(pos) == {"TP1": T0 + 6_000, "STOP": T0 + 7_000}
    obs = observations(
        pos, tracker.touched(pos), feed_status="STALE", h1_bias_now="DOWN",
        replay_ended=False, clock_ms=T0 + 7_000,
    )  # fmt: skip
    assert obs == [
        "STOP TOUCHED (NOT VERIFIED FILL)",
        "TP1 TOUCHED — execution unconfirmed",
        "FEED STALE",
        "H1 BIAS CHANGED",
    ]
    assert journal.get(pos.position_id) == pos  # nothing was closed or written
    # After a recorded stop modification the old touch no longer applies to the new level.
    mod, _ = journal.record_modify(
        new_action_id(), pos.position_id, effective_ms=T0 + 8_000, new_stop=D("3990")
    )
    assert "STOP" not in tracker.touched(mod)


def test_observations_unavailable_before_fill_and_reconciliation_flag(db: Path) -> None:
    with Store.open(db, CLOCK) as store:
        PositionJournal(store).record_entry(entry())
    with Store.open(db, CLOCK) as store:
        (pos,) = PositionJournal(store).restore_on_startup()
    obs = observations(
        pos, {}, feed_status="FRESH", h1_bias_now="UP", replay_ended=False, clock_ms=T0
    )
    assert obs == [
        "MANUAL BROKER VERIFICATION NEEDED",
        "MONITORING UNAVAILABLE (no quote at/after the recorded fill)",
    ]
    sell = TouchTracker()
    p = replace(pos, side=Side.SELL, current_sl=D("4003"), tp1=None, current_tp=None)
    sell.track([p])
    sell.on_quote(_quote(T0 + 9_000, "4002.80", "4003.00"))  # ASK reaches a SELL stop
    assert set(sell.touched(p)) == {"STOP"}
