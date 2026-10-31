"""M09-A CLI: explicit NOT_CONFIGURED, read-only reference-status over FIXTURE files."""

from __future__ import annotations

import io
import shutil
import socket
from pathlib import Path

import pytest

from grog.cli import EXIT_CONFIG, EXIT_OK, main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "reference"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_a, **_k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def run(argv: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    return main(argv, env=env, stdout=out, stderr=err), out.getvalue(), err.getvalue()


def config(tmp_path: Path, exporter: Path, hb: bool = True) -> Path:
    p = tmp_path / "ref.toml"
    lines = [
        "config_version = 1",
        "[live]",
        "max_quote_age_ms = 60000  # fixture-only",
        "[reference]",
        'source_id = "syn"',
        f'exporter_dir = "{exporter}"',
    ]
    if hb:
        lines.append("max_heartbeat_age_ms = 5000  # fixture-only")
    p.write_text("\n".join(lines) + "\n")
    return p


def test_not_configured_everywhere(isolated_env: dict[str, str]) -> None:
    code, out, _ = run(["reference-status"], isolated_env)
    assert code == EXIT_CONFIG and "Link: NOT_CONFIGURED" in out and "BID" not in out
    code, _, err = run(["ui", "--mode", "reference"], isolated_env)
    assert code == EXIT_CONFIG and "NOT_CONFIGURED" in err


def test_reference_status_reads_fixture_files_read_only(
    tmp_path: Path, isolated_env: dict[str, str]
) -> None:
    exporter, state = tmp_path / "exp", tmp_path / "state"
    shutil.copytree(FIXTURES, exporter)
    before = {p.name: p.read_bytes() for p in exporter.iterdir()}
    cfg = config(tmp_path, exporter)
    code, out, _ = run(
        ["reference-status", "--config", str(cfg), "--state-dir", str(state)], isolated_env
    )
    assert code == EXIT_OK
    assert "Label: FIXTURE · SIMULATED" in out and "Broker-verified: NO" in out
    assert "REFERENCE · INDICATIVE" not in out  # fixture quotes are never shown as live ref
    assert "Link: OFFLINE" in out  # the fixture's heartbeats are from 2026-10-01: old now
    assert "BID 4000.20  ASK 4000.40" in out and "DUPLICATE 3" in out and "CROSSED 1" in out
    assert "READY actionable now: none" in out
    assert not state.exists()  # status never writes a cursor, journal or anything else
    assert {p.name: p.read_bytes() for p in exporter.iterdir()} == before
    code, _, err = run(["ui", "--mode", "reference", "--config", str(cfg)], isolated_env)
    assert code == EXIT_CONFIG and "NOT_AVAILABLE" in err and "BID" not in err


def test_unset_heartbeat_threshold_reports_unknown(
    tmp_path: Path, isolated_env: dict[str, str]
) -> None:
    exporter = tmp_path / "exp"
    shutil.copytree(FIXTURES, exporter)
    cfg = config(tmp_path, exporter, hb=False)
    code, out, _ = run(["reference-status", "--config", str(cfg)], isolated_env)
    assert code == EXIT_OK and "Link: UNKNOWN (HEARTBEAT_THRESHOLD_UNSET)" in out


def test_configured_but_empty_directory_is_no_data(
    tmp_path: Path, isolated_env: dict[str, str]
) -> None:
    cfg = config(tmp_path, tmp_path / "missing")
    code, out, _ = run(["reference-status", "--config", str(cfg)], isolated_env)
    assert code == EXIT_OK and "Link: NO_DATA" in out and "Last quote" not in out
