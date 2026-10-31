"""M06: deterministic replay runs, persistence/restart, reports (CL-09/10, ADV-04/08,
ST-11..14, zero-opportunity days, rejected-winner accounting)."""

from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path

import pytest

from grog.cli import EXIT_NOT_FOUND, EXIT_OK, main
from grog.domain.clock import SystemClock
from grog.journal.research import ResearchStore, get_run
from grog.journal.store import STATE_DB_FILENAME, Store
from grog.replay import synthetic
from grog.replay.service import replay_source
from grog.settings import load_settings

EXAMPLE = Path(__file__).resolve().parents[2] / "config" / "research.example.toml"


def fixture_config(tmp: Path, age: int = 60_000, delay: int = 30_000) -> Path:
    """Fixture-only declarations of OPEN live thresholds (never broker values)."""
    text = (
        EXAMPLE.read_text()
        .replace("# max_quote_age_ms = <int>", f"max_quote_age_ms = {age}")
        .replace(
            "# max_first_postclose_delay_ms = <int>", f"max_first_postclose_delay_ms = {delay}"
        )
    )
    path = tmp / f"cfg-{age}-{delay}.toml"
    path.write_text(text)
    return path


def cli(argv: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, env=env, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> dict:
    root = tmp_path_factory.mktemp("m06")
    env = {"HOME": str(root / "home")}
    csv = root / "syn.csv"
    csv.write_bytes(synthetic.generate_csv())
    state = root / "state"
    code, _, err = cli(
        [
            "import-ticks",
            "--file",
            str(csv),
            "--source-id",
            "syn",
            "--origin",
            "SYNTHETIC",
            "--state-dir",
            str(state),
        ],
        env,
    )
    assert code == EXIT_OK, err
    cfg = fixture_config(root)
    code, out, err = cli(
        ["replay", "--source-id", "syn", "--state-dir", str(state), "--config", str(cfg)], env
    )
    assert code == EXIT_OK, err
    run_id = out.split("RUN: ")[1].split()[0]
    return {"root": root, "env": env, "state": state, "cfg": cfg, "out": out, "run_id": run_id}


def report_json(world: dict, run_id: str) -> dict:
    code, out, err = cli(
        ["report", "--run-id", run_id, "--format", "json", "--state-dir", str(world["state"])],
        world["env"],
    )
    assert code == EXIT_OK, err
    return json.loads(out)


def db(world: dict) -> sqlite3.Connection:
    conn = sqlite3.connect(world["state"] / STATE_DB_FILENAME)
    conn.row_factory = sqlite3.Row
    return conn


def test_replay_report_banners_and_no_win_rate(world: dict) -> None:
    out = world["out"]
    for label in (
        "MODE: REPLAY",
        "FIDELITY: SIMULATED",
        "SYNTHETIC data: no market-performance",
        "Assumptions:",
        "Thresholds:",
        "Net:   UNKNOWN (no declared cost model)",
        "NOT CLAIMED",
    ):
        assert label in out
    lowered = out.lower()
    assert "%" not in out and "win rate:" not in lowered.replace("win rate: not claimed", "")
    assert "confidence" not in lowered and "probability of" not in lowered


def test_valid_trigger_scenario_with_funnel_counts(world: dict) -> None:
    s = report_json(world, world["run_id"])["result"]["summary"]
    f = s["funnel"]
    assert f["trigger_observations"] >= 1 and f["ready_offered"] >= 1
    assert f["trigger_observations"] == f["first_quote_decisions"]
    assert f["first_quote_decisions"] == (
        f["ready_offered"] + f["missed_data_gap"] + f["missed_price_chase"] + f["not_issued"]
    )
    assert f["simulated_filled"] <= f["fillable"] <= f["ready_offered"]
    assert s["simulated_outcomes"]["count"] == f["ready_offered"]
    assert s["execution_fidelity"] == "SIMULATED" and s["mode"] == "REPLAY"


def test_cl09_identical_replay_twice(world: dict) -> None:
    args = [
        "replay",
        "--source-id",
        "syn",
        "--state-dir",
        str(world["state"]),
        "--config",
        str(world["cfg"]),
    ]
    code, out, _ = cli(args, world["env"])
    assert code == EXIT_OK and out == world["out"]
    conn = db(world)
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM research_runs WHERE run_id = ?", (world["run_id"],)
        ).fetchone()[0]
        == 1
    )
    conn.close()


def test_cl10_report_nonexistent_run(world: dict, tmp_path: Path) -> None:
    code, out, err = cli(
        ["report", "--run-id", "RUN-missing", "--state-dir", str(world["state"])], world["env"]
    )
    assert code == EXIT_NOT_FOUND and out == "" and "code=NOT_FOUND" in err
    empty = tmp_path / "empty"
    code, _, err = cli(["report", "--run-id", "RUN-x", "--state-dir", str(empty)], world["env"])
    assert code == EXIT_NOT_FOUND and not empty.exists()  # read-only: nothing created


def test_report_text_matches_replay_and_is_read_only(world: dict) -> None:
    db_file = world["state"] / STATE_DB_FILENAME
    before = db_file.read_bytes()
    code, out, _ = cli(
        ["report", "--run-id", world["run_id"], "--state-dir", str(world["state"])], world["env"]
    )
    assert code == EXIT_OK and out in world["out"]
    assert db_file.read_bytes() == before


def test_replay_unknown_source_and_naive_window(world: dict) -> None:
    code, _, err = cli(
        ["replay", "--source-id", "nope", "--state-dir", str(world["state"])], world["env"]
    )
    assert code == EXIT_NOT_FOUND and "NOT_FOUND" in err
    code, _, err = cli(
        [
            "replay",
            "--source-id",
            "syn",
            "--state-dir",
            str(world["state"]),
            "--from",
            "2026-10-05T00:00:00",
        ],
        world["env"],
    )
    assert code != EXIT_OK and "NAIVE_TIMESTAMP" in err


def test_zero_signal_scenario_default_thresholds_unset(world: dict) -> None:
    code, out, _ = cli(
        ["replay", "--source-id", "syn", "--state-dir", str(world["state"])], world["env"]
    )
    assert code == EXIT_OK
    run_id = out.split("RUN: ")[1].split()[0]
    s = report_json(world, run_id)["result"]["summary"]
    assert s["funnel"]["ready_offered"] == 0
    assert s["not_issued_reasons"].get("FEED_HEALTH_UNKNOWN", 0) >= 1
    days = s["days"]
    assert days["zero_opportunity"] == days["covered"] > 0  # every day reported, even empty
    assert all(n == 0 for n in days["per_day_ready"].values())
    # Rejected setups still accounted separately as COUNTERFACTUAL (rejected-winner check).
    rc = s["rejected_counterfactual"]
    assert rc["count"] + rc["not_evaluable"] == s["funnel"]["first_quote_decisions"]
    assert s["simulated_outcomes"]["count"] == 0


def test_rejected_winners_kept_apart_from_simulated(world: dict) -> None:
    res = report_json(world, world["run_id"])["result"]
    cf = [o for o in res["outcomes"] if o["counterfactual"]]
    real = [o for o in res["outcomes"] if not o["counterfactual"]]
    assert all(o["signal_id"] is None for o in cf)
    assert all(o["signal_id"] for o in real)
    s = res["summary"]
    assert s["rejected_counterfactual"]["count"] == len(cf)
    assert s["simulated_outcomes"]["count"] == len(real)
    assert "COUNTERFACTUAL" in s["rejected_counterfactual"]["label"]


def test_adv04_report_gives_totals_not_filter_precision(world: dict) -> None:
    s = report_json(world, world["run_id"])["result"]["summary"]
    g = s["simulated_outcomes"]["gross"]
    assert set(g) == {"resolved", "total_r", "mean_r"}
    assert {"ready_offered", "first_quote_decisions"} <= set(s["funnel"])
    assert "per_day_ready" in s["days"]
    assert s["assumptions"].pop("probability_or_win_rate") == "NOT CLAIMED"
    text = json.dumps(s)
    assert "precision" not in text and "win_rate" not in text


def test_adv08_dataset_reuse_disclosed(world: dict) -> None:
    other = fixture_config(world["root"], age=90_000, delay=45_000)
    code, out, _ = cli(
        [
            "replay",
            "--source-id",
            "syn",
            "--state-dir",
            str(world["state"]),
            "--config",
            str(other),
        ],
        world["env"],
    )
    assert code == EXIT_OK and "Dataset reuse: " in out and world["run_id"] in out
    second = out.split("RUN: ")[1].split()[0]
    assert second != world["run_id"]
    doc = report_json(world, second)
    assert world["run_id"] in [r["run_id"] for r in doc["comparable_runs"]]


def test_window_preroll_is_history_only(world: dict) -> None:
    args = [
        "replay",
        "--source-id",
        "syn",
        "--state-dir",
        str(world["state"]),
        "--config",
        str(world["cfg"]),
        "--from",
        "2026-10-13T00:00:00Z",
        "--to",
        "2026-10-18T00:00:00Z",
    ]
    code, out, _ = cli(args, world["env"])
    assert code == EXIT_OK
    s = report_json(world, out.split("RUN: ")[1].split()[0])["result"]["summary"]
    assert s["quotes"]["pre_roll"] > 0 and s["quotes"]["in_window"] > 0
    assert s["window"]["first_quote_ms"] >= 1791849600000  # 2026-10-13Z
    assert s["window"]["last_quote_ms"] < 1792281600000  # 2026-10-18Z
    full = report_json(world, world["run_id"])["result"]["summary"]
    assert (
        s["funnel"]["ready_offered"] + s["funnel"]["pre_roll_ready_history"]
        <= (full["funnel"]["ready_offered"])
    )
    assert s["days"]["covered"] == 5


def test_st11_st13_attribution_and_simulated_only(world: dict) -> None:
    conn = db(world)
    run = conn.execute(
        "SELECT * FROM research_runs WHERE run_id = ?", (world["run_id"],)
    ).fetchone()
    assert run["source_id"] == "syn" and run["source_fidelity"] == "SIMULATED"
    plans = [
        json.loads(r[0])
        for r in conn.execute(
            "SELECT immutable_plan_json FROM signal_records WHERE run_id = ?", (world["run_id"],)
        )
    ]
    assert plans and all(p["original_source_id"] == "syn" for p in plans)
    assert all(p["execution_fidelity"] == "SIMULATED" for p in plans)
    assert "LIVE" not in {
        r[0] for r in conn.execute("SELECT DISTINCT source_fidelity FROM research_runs")
    }
    conn.close()


def test_st14_no_duplicate_signals_or_events(world: dict) -> None:
    conn = db(world)
    rid = world["run_id"]
    n_sig = conn.execute("SELECT COUNT(*) FROM signal_records WHERE run_id=?", (rid,)).fetchone()
    pairs = conn.execute(
        "SELECT COUNT(DISTINCT pair_key) FROM signal_records WHERE run_id=?", (rid,)
    ).fetchone()
    assert n_sig[0] == pairs[0]
    ready = conn.execute(
        "SELECT COUNT(*) FROM signal_events WHERE run_id=? AND event_type='SIG:READY_ISSUED'",
        (rid,),
    ).fetchone()[0]
    assert ready == n_sig[0]
    s = report_json(world, rid)["result"]["summary"]
    assert ready == s["funnel"]["ready_offered"]  # no double-counted signals
    piv = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT dedupe_key) FROM signal_events WHERE run_id=?", (rid,)
    ).fetchone()
    assert piv[0] == piv[1]
    conn.close()


def test_research_tables_append_only(world: dict) -> None:
    conn = db(world)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE signal_events SET payload_json = '{}'")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM signal_records")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE signal_records SET immutable_plan_json = '{}'")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE research_runs SET result_json = '{}' WHERE status='COMPLETE'")
    conn.close()


class Interrupt(Exception):
    pass


def test_interrupted_replay_restarts_idempotently(world: dict, tmp_path: Path) -> None:
    import shutil

    state = tmp_path / "state"
    shutil.copytree(world["state"], state)
    (state / STATE_DB_FILENAME).unlink()
    for extra in state.glob(f"{STATE_DB_FILENAME}-*"):
        extra.unlink()
    shutil.copy(world["state"] / STATE_DB_FILENAME, state / STATE_DB_FILENAME)
    settings = load_settings(str(fixture_config(tmp_path, age=61_000)), world["env"])

    def stop(n: int) -> None:
        if n >= 60_000:
            raise Interrupt

    with Store.open(state / STATE_DB_FILENAME, SystemClock()) as store:
        with pytest.raises(Interrupt):
            replay_source(
                store, state, "syn", settings, checkpoint_every=20_000, after_checkpoint=stop
            )
        conn = store._conn
        runs = conn.execute(
            "SELECT run_id, status, processed_quotes FROM research_runs WHERE status = 'RUNNING'"
        ).fetchall()
        assert len(runs) == 1 and runs[0]["processed_quotes"] == 60_000
        rid = runs[0]["run_id"]
        partial = conn.execute(
            "SELECT COUNT(*) FROM signal_events WHERE run_id=?", (rid,)
        ).fetchone()[0]
        assert partial > 0
        result, run = replay_source(store, state, "syn", settings, checkpoint_every=20_000)
        assert run.status == "COMPLETE" and run.run_id == rid
        total = conn.execute(
            "SELECT COUNT(*) FROM signal_events WHERE run_id=?", (rid,)
        ).fetchone()[0]
        assert total == len(result.s1_events) + len(result.signal_events) >= partial
        # Third run on a COMPLETE run adds nothing and verifies the stored result.
        again, run2 = replay_source(store, state, "syn", settings)
        assert run2.result == run.result
        assert (
            conn.execute("SELECT COUNT(*) FROM signal_events WHERE run_id=?", (rid,)).fetchone()[0]
            == total
        )
        assert ResearchStore(store).checkpoint  # store API present
        assert get_run(conn, rid).processed_quotes == result.processed_quotes
