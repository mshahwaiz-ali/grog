"""CLI contract for M00: help, version, read-only doctor, structured errors (CL-01/02/11)."""

from __future__ import annotations

import io
import re
import socket
from pathlib import Path

import pytest

import grog
from grog.cli import EXIT_CONFIG, EXIT_OK, EXIT_USAGE, main

EXAMPLE_CONFIG = Path(__file__).resolve().parents[2] / "config" / "research.example.toml"


def run(argv: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, env=env, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def snapshot(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


# ---------------------------------------------------------------- help / version


def test_help_lists_only_finished_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--help"]) == EXIT_OK
    text = capsys.readouterr().out
    listed = re.findall(r"^    (\S+)\s{2,}", text, flags=re.MULTILINE)
    assert listed == ["version", "doctor"]
    for unavailable in ("import-ticks", "replay", "buy", "sell", "close-broker-order"):
        assert unavailable not in text


def test_no_command_prints_help(isolated_env: dict[str, str]) -> None:
    code, out, _ = run([], isolated_env)
    assert code == EXIT_OK and "usage: grog" in out


def test_subcommand_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["doctor", "--help"]) == EXIT_OK
    assert "--state-dir" in capsys.readouterr().out


def test_version(isolated_env: dict[str, str]) -> None:
    code, out, err = run(["version"], isolated_env)
    assert code == EXIT_OK and err == ""
    assert out.splitlines()[0] == f"grog {grog.__version__}"
    assert "Config schema: 1" in out and "State schema:" in out


# ---------------------------------------------------------------- doctor


def test_doctor_empty_state_is_read_only_and_offline(
    tmp_path: Path, isolated_home: Path, isolated_env: dict[str, str], no_network: None
) -> None:
    state = tmp_path / "state"
    before = snapshot(tmp_path)
    code, out, err = run(["doctor", "--state-dir", str(state)], isolated_env)
    assert code == EXIT_OK, err
    assert snapshot(tmp_path) == before  # nothing created anywhere, incl. home
    assert not state.exists()
    assert out.startswith("GROG / DOCTOR")
    assert "MODE: REPLAY" in out
    assert f"VERSION: {grog.__version__}" in out
    assert "Python: 3.11" in out
    assert "Config: built-in defaults" in out
    assert f"Local state: {state} [--state-dir, NOT CREATED]  Database: NOT INITIALIZED" in out
    assert "Market feed: NOT CONFIGURED [offline mode — expected]" in out
    assert "Live broker: NOT REQUIRED FOR REPLAY" in out
    assert "Trading/orders: DISABLED" in out
    assert "Source configured: NONE" in out


def test_doctor_default_state_dir_does_not_write_user_home(
    isolated_home: Path, isolated_env: dict[str, str], no_network: None
) -> None:
    code, out, _ = run(["doctor"], isolated_env)
    assert code == EXIT_OK
    assert list(isolated_home.iterdir()) == []
    expected = isolated_home / ".local" / "share" / "grog"
    assert f"Local state: {expected} [XDG default, NOT CREATED]" in out


def test_doctor_reports_existing_state_without_modifying_it(
    tmp_path: Path, isolated_env: dict[str, str]
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    db = state / "state.sqlite3"
    db.write_bytes(b"placeholder")
    mtime = db.stat().st_mtime_ns
    code, out, _ = run(["doctor", "--state-dir", str(state)], isolated_env)
    assert code == EXIT_OK
    assert "[--state-dir, EXISTS]  Database: AVAILABLE" in out
    assert db.read_bytes() == b"placeholder" and db.stat().st_mtime_ns == mtime
    assert sorted(p.name for p in state.iterdir()) == ["state.sqlite3"]


def test_doctor_with_example_config(isolated_env: dict[str, str]) -> None:
    code, out, _ = run(["doctor", "--config", str(EXAMPLE_CONFIG)], isolated_env)
    assert code == EXIT_OK
    assert f"Config: {EXAMPLE_CONFIG}" in out
    assert "Strategy profile: S1_RESEARCH_V0_2" in out


def test_doctor_output_is_deterministic(tmp_path: Path, isolated_env: dict[str, str]) -> None:
    args = ["doctor", "--state-dir", str(tmp_path / "s")]
    assert run(args, isolated_env) == run(args, isolated_env)


# ---------------------------------------------------------------- errors (CL-11)


@pytest.mark.parametrize("argv", [["buy"], ["trade"], ["import-ticks"], ["replay"], ["doctorr"]])
def test_unknown_or_unimplemented_command_fails_clearly(
    argv: list[str], isolated_env: dict[str, str]
) -> None:
    code, out, err = run(argv, isolated_env)
    assert code == EXIT_USAGE and out == ""
    assert err.startswith("GROG ERROR code=USAGE_ERROR")
    assert "grog --help" in err


def test_unknown_option_fails(isolated_env: dict[str, str]) -> None:
    code, _, err = run(["doctor", "--live"], isolated_env)
    assert code == EXIT_USAGE and "USAGE_ERROR" in err


def test_doctor_rejects_unknown_mode_config(tmp_path: Path, isolated_env: dict[str, str]) -> None:
    cfg = tmp_path / "bad.toml"
    cfg.write_text('config_version = 1\nmode = "LIVE"\n', encoding="utf-8")
    code, out, err = run(["doctor", "--config", str(cfg)], isolated_env)
    assert code == EXIT_CONFIG and out == ""
    assert "CONFIG_INVALID field=mode reason=UNKNOWN_MODE" in err
    assert "Next:" in err


def test_doctor_rejects_trade_execution_config(
    tmp_path: Path, isolated_env: dict[str, str]
) -> None:
    cfg = tmp_path / "exec.toml"
    cfg.write_text("config_version = 1\nallow_trade_execution = true\n", encoding="utf-8")
    code, _, err = run(["doctor", "--config", str(cfg)], isolated_env)
    assert code == EXIT_CONFIG
    assert "reason=TRADE_EXECUTION_FORBIDDEN" in err


def test_doctor_missing_config_file(tmp_path: Path, isolated_env: dict[str, str]) -> None:
    code, _, err = run(["doctor", "--config", str(tmp_path / "missing.toml")], isolated_env)
    assert code == EXIT_CONFIG and "CONFIG_NOT_FOUND" in err
