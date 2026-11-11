"""TF-1c: startup plan never launches MT5 or guesses permissions."""

from pathlib import Path

import pytest

from grog.desktop.mt5_discovery import LocalMT5
from grog.desktop.mt5_process import ProcessInventory, ProcessState
from grog.desktop.mt5_startup import StartupState, plan_mt5_startup


def _installed(tmp_path: Path) -> LocalMT5:
    prefix = tmp_path / ".mt5"
    terminal = prefix / "drive_c/Program Files/MetaTrader 5/terminal64.exe"
    exporter = prefix / "drive_c/users/person/AppData/Roaming/MetaQuotes/Terminal/Common/Files/grog"
    wine = tmp_path / "wine-staging/bin/wine"
    terminal.parent.mkdir(parents=True)
    terminal.write_bytes(b"MZ")
    exporter.mkdir(parents=True)
    wine.parent.mkdir(parents=True)
    wine.write_text("#!/bin/sh\nexit 0\n")
    wine.chmod(0o755)
    return LocalMT5(prefix, wine, terminal, exporter, ())


def _inventory(state=ProcessState.NO_CANDIDATE, matched=(), uncertain=(), other=()):
    return ProcessInventory(state, matched, uncertain, other)


def test_no_consent_does_not_prepare_launch(tmp_path: Path) -> None:
    local = _installed(tmp_path)
    p = plan_mt5_startup(local, _inventory())
    assert p.state is StartupState.PERMISSION_REQUIRED
    assert not p.may_start and not p.argv and not p.environment


def test_permission_alone_does_not_bypass_profile_check(tmp_path: Path) -> None:
    local = _installed(tmp_path)
    p = plan_mt5_startup(local, _inventory(), allow_local_launch=True)
    assert p.state is StartupState.PROFILE_UNVERIFIED
    assert not p.may_start and not p.argv


def test_verified_profile_and_permission_produce_argv_only(tmp_path: Path) -> None:
    local = _installed(tmp_path)
    p = plan_mt5_startup(
        local,
        _inventory(),
        allow_local_launch=True,
        dedicated_read_only_profile_verified=True,
    )
    assert p.state is StartupState.READY_TO_START and p.may_start
    assert p.argv == (str(local.wine_binary), str(local.terminal))
    assert p.environment == (("WINEPREFIX", str(local.prefix)),)
    assert not hasattr(p, "process")


def test_already_running_reused_even_without_launch_consent(tmp_path: Path) -> None:
    local = _installed(tmp_path)
    p = plan_mt5_startup(local, _inventory(ProcessState.RUNNING_CANDIDATE, (123,)))
    assert p.state is StartupState.REUSE_EXISTING
    assert not p.may_start and not p.argv


@pytest.mark.parametrize(
    "inventory",
    [
        _inventory(ProcessState.AMBIGUOUS),
        _inventory(uncertain=(99,)),
        _inventory(ProcessState.RUNNING_CANDIDATE, (1, 2)),
        _inventory(ProcessState.RUNNING_CANDIDATE, ()),
        _inventory(ProcessState.NO_CANDIDATE, (1,)),
    ],
)
def test_ambiguous_or_inconsistent_processes_never_start(tmp_path: Path, inventory) -> None:
    local = _installed(tmp_path)
    p = plan_mt5_startup(
        local,
        inventory,
        allow_local_launch=True,
        dedicated_read_only_profile_verified=True,
    )
    assert p.state is StartupState.PROCESS_AMBIGUOUS
    assert not p.may_start and not p.argv


def test_other_prefix_does_not_get_taken_over(tmp_path: Path) -> None:
    local = _installed(tmp_path)
    p = plan_mt5_startup(local, _inventory(other=(456,)))
    assert p.state is StartupState.PERMISSION_REQUIRED
    assert not p.may_start


def test_stale_discovery_rechecked(tmp_path: Path) -> None:
    local = _installed(tmp_path)
    local.terminal.unlink()
    p = plan_mt5_startup(
        local,
        _inventory(),
        allow_local_launch=True,
        dedicated_read_only_profile_verified=True,
    )
    assert p.state is StartupState.SETUP_REQUIRED
    assert "TERMINAL_NOT_FOUND" in p.reasons and not p.may_start


def test_missing_wine_binary_blocks_and_never_falls_back(tmp_path: Path) -> None:
    local = _installed(tmp_path)
    local.wine_binary.unlink()
    p = plan_mt5_startup(local, _inventory(), allow_local_launch=True,
                         dedicated_read_only_profile_verified=True)
    assert p.state is StartupState.SETUP_REQUIRED
    assert "WINE_NOT_FOUND" in p.reasons and not p.may_start


def test_no_file_mutation_during_planning(tmp_path: Path) -> None:
    local = _installed(tmp_path)
    originals = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    plan_mt5_startup(
        local,
        _inventory(),
        allow_local_launch=True,
        dedicated_read_only_profile_verified=True,
    )
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == originals
