"""Shared test isolation: tests never see or touch the real user home or XDG dirs."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(var, raising=False)
    return home


@pytest.fixture
def isolated_env(isolated_home: Path) -> dict[str, str]:
    return {"HOME": str(isolated_home)}
