"""`grog ui` command contract (docs/09 §8): replay session from local state, read-only,
reference mode NOT_CONFIGURED, no mock live quotes, no broker writes."""

from __future__ import annotations

import argparse
import io
from pathlib import Path

from grog.cli import EXIT_CONFIG, EXIT_NOT_FOUND, EXIT_OK, EXIT_USAGE, build_ui_session, main
from grog.journal.store import STATE_DB_FILENAME
from grog.replay import synthetic
from grog.replay.session import Playback
from grog.ui.app import GrogApp
from ui_support import run


def cli(argv: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    return main(argv, env=env, stdout=out, stderr=err), out.getvalue(), err.getvalue()


def snapshot(root: Path) -> dict[str, bytes]:
    """Database and batch bytes. SQLite may create its transient -wal/-shm index files for a
    read-only reader of a WAL database; they carry no Grog state and are ignored."""
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and not p.name.endswith(("-wal", "-shm"))
    }


def test_reference_mode_is_not_configured(isolated_env: dict[str, str]) -> None:
    code, out, err = cli(["ui", "--mode", "reference"], isolated_env)
    assert code == EXIT_CONFIG and out == "" and "code=NOT_CONFIGURED" in err
    assert "no live or mock quotes" in err


def test_replay_mode_needs_existing_source(isolated_env: dict[str, str], tmp_path: Path) -> None:
    code, _, err = cli(["ui", "--mode", "replay"], isolated_env)
    assert code == EXIT_USAGE and "--source-id" in err
    empty = tmp_path / "none"
    code, _, err = cli(
        ["ui", "--mode", "replay", "--source-id", "x", "--state-dir", str(empty)], isolated_env
    )
    assert code == EXIT_NOT_FOUND and "NOT_FOUND" in err and not empty.exists()
    code, _, err = cli(["ui", "--mode", "nope", "--source-id", "x"], isolated_env)
    assert code == EXIT_USAGE


def test_ui_session_loads_read_only_and_starts_paused(
    isolated_env: dict[str, str], tmp_path: Path
) -> None:
    csv = tmp_path / "syn.csv"
    csv.write_bytes(synthetic.generate_csv(days=12))
    state = tmp_path / "state"
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
        isolated_env,
    )
    assert code == EXIT_OK, err
    before = snapshot(state)
    args = argparse.Namespace(source_id="syn", from_ts=None, config=None, state_dir=str(state))
    session = build_ui_session(args, isolated_env)
    assert session is not None and session.playback is Playback.PAUSED
    assert session.source.origin == "SYNTHETIC" and len(session.source.batch_sha256s) == 1
    assert snapshot(state) == before  # read-only: no migration, no new rows or files
    missing = argparse.Namespace(source_id="nope", from_ts=None, config=None, state_dir=str(state))
    assert build_ui_session(missing, isolated_env) is None

    async def scenario() -> None:
        app = GrogApp(session, autoplay_timer=False)
        async with app.run_test(size=(120, 34)) as pilot:
            await pilot.press("5")
            diag = app.query_one("#diag").plain
            assert "Status: REPLAY_PAUSED" in diag and session.source.batch_sha256s[0] in diag
            # Default config leaves OPEN thresholds unset: feed health UNKNOWN, no READY.
            assert "STALE_THRESHOLD_UNSET" in app.query_one("#banner").plain

    run(scenario)
    assert snapshot(state) == before
    assert (state / STATE_DB_FILENAME).is_file()
