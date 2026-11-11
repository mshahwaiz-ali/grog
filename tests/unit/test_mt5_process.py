"""TF-1b local read-only process inventory is conservative and side-effect free."""

from __future__ import annotations

from pathlib import Path

import pytest

from grog.desktop.mt5_process import ProcessState, inspect_mt5_processes


def _proc(
    root: Path,
    pid: int,
    *,
    comm: str = "terminal64.exe",
    argv: str = "terminal64.exe",
    prefix: str | None = None,
) -> Path:
    p = root / str(pid)
    p.mkdir(parents=True)
    (p / "comm").write_text(comm + "\n")
    (p / "cmdline").write_bytes(argv.encode() + b"\0")
    env = b"HOME=/home/user\0"
    if prefix is not None:
        env += f"WINEPREFIX={prefix}".encode() + b"\0"
    (p / "environ").write_bytes(env)
    return p


def test_absent_is_not_running(tmp_path: Path) -> None:
    result = inspect_mt5_processes(tmp_path / "prefix", proc_root=tmp_path)
    assert result.state is ProcessState.NO_CANDIDATE
    assert not result.matching_pids


def test_exact_prefix_is_running_candidate_not_live(tmp_path: Path) -> None:
    prefix = tmp_path / "mt5"
    p = _proc(tmp_path, 112, prefix=str(prefix))
    before = {x.name: x.read_bytes() for x in p.iterdir()}
    result = inspect_mt5_processes(prefix, proc_root=tmp_path)
    assert result.state is ProcessState.RUNNING_CANDIDATE
    assert result.matching_pids == (112,)
    assert {x.name: x.read_bytes() for x in p.iterdir()} == before
    assert not hasattr(result, "live")


def test_wine_windows_command_path(tmp_path: Path) -> None:
    prefix = tmp_path / "mt5"
    _proc(
        tmp_path,
        34,
        comm="wine-preloader",
        argv=r"C:\Program Files\MetaTrader 5\terminal64.exe",
        prefix=str(prefix),
    )
    result = inspect_mt5_processes(prefix, proc_root=tmp_path)
    assert result.matching_pids == (34,)


def test_other_prefix_not_treated_as_ours(tmp_path: Path) -> None:
    prefix = tmp_path / "ours"
    other = tmp_path / "other"
    _proc(tmp_path, 10, prefix=str(other))
    result = inspect_mt5_processes(prefix, proc_root=tmp_path)
    assert result.state is ProcessState.NO_CANDIDATE
    assert result.matching_pids == () and result.other_prefix_pids == (10,)


def test_unverified_missing_prefix_prevents_proving_stopped(tmp_path: Path) -> None:
    _proc(tmp_path, 12, prefix=None)
    result = inspect_mt5_processes(tmp_path / "ours", proc_root=tmp_path)
    assert result.state is ProcessState.AMBIGUOUS
    assert result.uncertain_pids == (12,)


def test_multiple_same_prefix_are_ambiguous(tmp_path: Path) -> None:
    prefix = tmp_path / "ours"
    _proc(tmp_path, 12, prefix=str(prefix))
    _proc(tmp_path, 13, prefix=str(prefix))
    result = inspect_mt5_processes(prefix, proc_root=tmp_path)
    assert result.state is ProcessState.AMBIGUOUS
    assert result.matching_pids == (12, 13)


def test_not_an_argument_substring_match(tmp_path: Path) -> None:
    _proc(tmp_path, 123, comm="python", argv="python", prefix=str(tmp_path / "ours"))
    result = inspect_mt5_processes(tmp_path / "ours", proc_root=tmp_path)
    assert result.state is ProcessState.NO_CANDIDATE


def test_ignores_exited_process(tmp_path: Path) -> None:
    (tmp_path / "155").mkdir()  # /proc race simulation: process directory without files
    result = inspect_mt5_processes(tmp_path / "ours", proc_root=tmp_path)
    assert result.state is ProcessState.NO_CANDIDATE


def test_nonexistent_proc_does_not_claim_stopped(tmp_path: Path) -> None:
    with pytest.raises(OSError, match="Cannot inspect"):
        inspect_mt5_processes(tmp_path / "ours", proc_root=tmp_path / "missing")


def test_invalid_relative_prefix_is_unverified(tmp_path: Path) -> None:
    _proc(tmp_path, 10, prefix="relative-folder")
    result = inspect_mt5_processes(tmp_path / "ours", proc_root=tmp_path)
    assert result.state is ProcessState.AMBIGUOUS
