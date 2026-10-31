"""Package import and entry point (CL-01)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import grog
from grog import cli, settings


def test_package_imports_with_version() -> None:
    assert isinstance(grog.__version__, str)
    assert grog.__version__ not in ("", "0+unknown")
    assert callable(cli.main)
    assert settings.CONFIG_SCHEMA_VERSION == 1


def _run(args: list[str], home: Path) -> subprocess.CompletedProcess[str]:
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8"}
    return subprocess.run(args, capture_output=True, text=True, env=env, timeout=60, check=False)


def test_python_dash_m_entry_point(isolated_home: Path) -> None:
    result = _run([sys.executable, "-m", "grog", "--help"], isolated_home)
    assert result.returncode == 0, result.stderr
    assert "usage: grog" in result.stdout
    assert "doctor" in result.stdout and "version" in result.stdout


def test_installed_console_script(isolated_home: Path) -> None:
    script = Path(sys.executable).parent / "grog"
    assert script.exists(), "console script 'grog' should be installed by uv sync"
    result = _run([str(script), "version"], isolated_home)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(f"grog {grog.__version__}")


def test_engine_free_of_ui_and_network_imports() -> None:
    # M00 modules must not pull in the TUI, sqlite or networking stacks at import time.
    code = (
        "import sys, grog, grog.cli, grog.settings; "
        "bad=[m for m in ('textual','rich','sqlite3','urllib.request','http.client') "
        "if m in sys.modules]; print(','.join(bad))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=True
    )
    assert result.stdout.strip() == ""


def test_strategy_layer_is_pure() -> None:
    # docs/09: analysis -> strategies; no UI, persistence, journal or network coupling.
    code = (
        "import sys, grog.market_data.bars, grog.analysis.contexts, "
        "grog.strategies.s1_pullback, grog.signals.pipeline, grog.replay.runner; "
        "bad=[m for m in ('textual','rich','sqlite3','urllib.request','http.client',"
        "'grog.journal','grog.journal.store') if m in sys.modules]; print(','.join(bad))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=True
    )
    assert result.stdout.strip() == ""
