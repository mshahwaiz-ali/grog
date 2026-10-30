"""`grog import-ticks` CLI contract (docs/09 §8, docs/02 §13; CL-04/05/07)."""

from __future__ import annotations

import io
import socket
from pathlib import Path

import pytest

from grog.cli import EXIT_IMPORT_REJECTED, EXIT_OK, EXIT_USAGE, main

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic_xauusd_v1.csv"


def run(argv: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, env=env, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def imp(state: Path, env: dict[str, str], file: Path = FIXTURE, origin: str = "SYNTHETIC"):
    return run(
        [
            "import-ticks",
            "--file",
            str(file),
            "--source-id",
            "syn-1",
            "--origin",
            origin,
            "--state-dir",
            str(state),
        ],
        env,
    )


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_a: object, **_k: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def test_import_then_duplicate(
    tmp_path: Path, isolated_env: dict[str, str], isolated_home: Path
) -> None:
    state = tmp_path / "state"
    code, out, err = imp(state, isolated_env)
    assert code == EXIT_OK, err
    assert out.startswith("GROG / IMPORT    STATUS: COMMITTED  FIDELITY: SYNTHETIC")
    assert "Rows: 6 accepted | 0 rejected" in out
    assert "Range UTC (provider): 2026-10-31 09:46:40.000 UTC .. 2026-10-31 09:46:42.500 UTC" in out
    assert "Same-ms distinct quotes retained: 2" in out
    assert "Provider time ahead of receipt: 1 quotes (max 5 ms" in out
    assert "Gaps: NOT EVALUATED" in out and "contract/fees: UNKNOWN" in out
    assert list(isolated_home.iterdir()) == []  # isolated state only

    code, out2, _ = imp(state, isolated_env)
    assert code == EXIT_OK
    assert "STATUS: ALREADY_IMPORTED" in out2 and "nothing changed" in out2

    code, out3, _ = run(["doctor", "--state-dir", str(state)], isolated_env)
    assert code == EXIT_OK and "Database: AVAILABLE" in out3


def test_rejected_import_message(tmp_path: Path, isolated_env: dict[str, str]) -> None:
    bad = tmp_path / "bad.csv"
    rows = FIXTURE.read_text().splitlines()
    rows += ["1793440003000,1793440003000,4000.30,4000.10"]
    bad.write_text("\n".join(rows) + "\n")
    code, out, err = imp(tmp_path / "state", isolated_env, bad)
    assert code == EXIT_IMPORT_REJECTED and out == ""
    assert not (tmp_path / "state").exists()  # rejected before any local state is touched
    assert err.splitlines()[0] == (
        "IMPORT_REJECTED line=8 field=ask reason=ASK_BELOW_BID detail=4000.10<4000.30; "
        "batch NOT committed; prior data unchanged."
    )
    assert err.splitlines()[1].startswith("Next:")


def test_conflict_message(tmp_path: Path, isolated_env: dict[str, str]) -> None:
    state = tmp_path / "state"
    assert imp(state, isolated_env)[0] == EXIT_OK
    other = tmp_path / "other.csv"
    other.write_text(
        "provider_time_utc_ms,received_time_utc_ms,bid,ask\n1793450000000,1793450000000,1,2\n"
    )
    code, _, err = imp(state, isolated_env, other, origin="HISTORICAL")
    assert code == EXIT_IMPORT_REJECTED
    assert "reason=SOURCE_METADATA_CONFLICT" in err and "batch NOT committed" in err


def test_missing_file_and_bad_args(tmp_path: Path, isolated_env: dict[str, str]) -> None:
    code, _, err = imp(tmp_path / "state", isolated_env, tmp_path / "nope.csv")
    assert code == EXIT_IMPORT_REJECTED and "reason=FILE_UNREADABLE" in err
    code, _, err = imp(tmp_path / "state", isolated_env, origin="LIVE")
    assert code == EXIT_USAGE and "USAGE_ERROR" in err
    code, _, err = run(["import-ticks", "--file", str(FIXTURE)], isolated_env)
    assert code == EXIT_USAGE
    code, _, err = run(
        [
            "import-ticks",
            "--file",
            str(FIXTURE),
            "--source-id",
            "a/b",
            "--origin",
            "SYNTHETIC",
            "--state-dir",
            str(tmp_path / "s"),
        ],
        isolated_env,
    )
    assert code == EXIT_IMPORT_REJECTED and "reason=INVALID_SOURCE_ID" in err
