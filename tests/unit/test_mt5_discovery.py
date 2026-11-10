"""TF-1a: read-only Wine/MT5 path discovery; never a feed-readiness claim."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from grog.desktop.mt5_discovery import discover_mt5


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def _setup(tmp_path: Path, user: str = "tester") -> tuple[Path, Path, Path]:
    home = tmp_path / "home"
    prefix = home / ".mt5"
    terminal = prefix / "drive_c/Program Files/MetaTrader 5/terminal64.exe"
    user_files = prefix / "drive_c" / "users" / user
    exporter = user_files / "AppData/Roaming/MetaQuotes/Terminal/Common/Files/grog"
    wine = tmp_path / "wine-staging" / "wine"
    terminal.parent.mkdir(parents=True)
    terminal.write_bytes(b"MZ")
    exporter.mkdir(parents=True)
    (exporter / "historical.grogref").write_bytes(b"M,1,...\n")
    wine.parent.mkdir(parents=True)
    wine.write_text("#!/bin/sh\nexit 0\n")
    wine.chmod(0o755)
    return home, wine, exporter


def test_finds_observed_layout_without_writes_or_feed_claims(tmp_path: Path) -> None:
    home, wine, exporter = _setup(tmp_path)
    before = _snapshot(tmp_path)
    found = discover_mt5(home=home, wine_binary=wine, wine_user="tester")
    assert found.files_found and found.issues == ()
    assert found.wine_binary == wine
    assert found.terminal.name == "terminal64.exe"
    assert found.exporter_directory == exporter
    assert not hasattr(found, "live")  # no inference from installed files
    assert _snapshot(tmp_path) == before


def test_missing_installation_is_reported_and_not_created(tmp_path: Path) -> None:
    home = tmp_path / "no-home"
    found = discover_mt5(home=home, wine_binary=tmp_path / "missing-wine", wine_user="tester")
    assert found.wine_binary is None
    assert found.issues == (
        "WINE_NOT_FOUND",
        "PREFIX_NOT_FOUND",
        "TERMINAL_NOT_FOUND",
        "EXPORTER_DIRECTORY_NOT_FOUND",
    )
    assert not home.exists()


def test_missing_exporter_is_not_silently_accepted(tmp_path: Path) -> None:
    home, wine, _ = _setup(tmp_path)
    # Construct another Wine user to verify a different folder cannot be accepted.
    result = discover_mt5(home=home, wine_binary=wine, wine_user="unconfigured")
    assert result.issues == ("EXPORTER_DIRECTORY_NOT_FOUND",)
    assert not result.files_found
    assert not result.exporter_directory.exists()


@pytest.mark.parametrize("invalid", ["", ".", "..", "../other", "/tmp/other", "..\\other"])
def test_rejects_unsafe_wine_user_component(tmp_path: Path, invalid: str) -> None:
    with pytest.raises(ValueError, match="one directory name"):
        discover_mt5(home=tmp_path, wine_binary=tmp_path / "wine", wine_user=invalid)


def test_command_does_not_claim_live_feed(tmp_path: Path, capsys) -> None:
    from grog.desktop.mt5_discovery import main

    home, wine, _ = _setup(tmp_path)
    rc = main(["--prefix", str(home / ".mt5"), "--wine", str(wine), "--wine-user", "tester"])
    output = capsys.readouterr().out
    assert rc == 0
    assert "LOCAL_FILES_FOUND" in output
    assert "No MT5 login, active connection, live ticks or clock accuracy verified" in output
