"""TF-1f: dedicated MT5 config/preset preview is deterministic and non-trading."""

from __future__ import annotations

import configparser
from pathlib import Path

import pytest

from grog.desktop.mt5_launch_config import (
    CONFIG_NAME,
    PRESET_NAME,
    PROFILE_NAME,
    main,
    render_reference_launch_files,
)


def _tree_snapshot(root: Path) -> dict[str, bytes | None]:
    """Include directories and file contents, not just the directory's initial entries."""
    return {
        str(path.relative_to(root)): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
    }


def _settings(source_id: str = "mt5tf20261111"):
    files = render_reference_launch_files(source_id)
    parser = configparser.ConfigParser()
    parser.read_string(files.config_text)
    return files, parser


def test_dedicated_profile_rejects_automated_trading_and_dll_imports() -> None:
    files, config = _settings()
    assert files.profile_name == PROFILE_NAME
    assert config["Charts"]["ProfileLast"] == "Grog-Reference"
    assert config["Experts"]["AllowLiveTrading"] == "0"
    assert config["Experts"]["AllowDllImport"] == "0"
    assert config["Experts"]["Enabled"] == "1"
    assert config["Experts"]["Account"] == "1"
    assert config["Experts"]["Profile"] == "1"


def test_only_approved_reference_expert_and_xauusd_chart() -> None:
    files, config = _settings()
    assert files.config_name == CONFIG_NAME
    assert config["StartUp"]["Expert"] == "GrogReferenceExporterFullUAT"
    assert config["StartUp"]["ExpertParameters"] == PRESET_NAME
    assert config["StartUp"]["Symbol"] == "XAUUSD"
    assert config["StartUp"]["Period"] == "M1"
    assert "Script" not in config["StartUp"]
    assert "Tester" not in config
    assert "Common" not in config  # no credentials or account override


def test_preset_file_bytes_use_unicode_bom_and_crlf() -> None:
    """MT5 presets are Unicode text; never write the printable preview as UTF-8."""
    files, _ = _settings("mt5tf20261111")
    assert files.preset_bytes.startswith(b"\xff\xfe")
    assert files.preset_bytes.decode("utf-16") == files.preset_text
    assert files.preset_bytes.decode("utf-16") == "InpSourceId=mt5tf20261111\r\n"


def test_fresh_source_id_is_in_preset_not_hardcoded_old_source() -> None:
    files, _ = _settings("mt5tf20261111")
    assert files.preset_text == "InpSourceId=mt5tf20261111\r\n"
    assert "mt5full20261108" not in files.config_text + files.preset_text
    assert "InpWarmupDays" not in files.preset_text  # no arbitrary new policy defaults


@pytest.mark.parametrize(
    "invalid",
    ["", "__bad", "bad__source", "../escape", "bad\n[Common]\nPassword=oops", "a" * 65],
)
def test_invalid_or_injectable_source_ids_rejected(invalid: str) -> None:
    with pytest.raises(ValueError, match="safe MQL5 exporter identifier"):
        render_reference_launch_files(invalid)


def test_render_is_deterministic_and_does_not_touch_current_directory(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    before = _tree_snapshot(tmp_path)
    a = render_reference_launch_files("mt5tf20261111")
    b = render_reference_launch_files("mt5tf20261111")
    assert a == b
    assert _tree_snapshot(tmp_path) == before


def test_cli_prints_preview_but_does_not_write_files(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    before = _tree_snapshot(tmp_path)
    assert main(["--source-id", "mt5tf20261111"]) == 0
    out = capsys.readouterr().out
    assert "PREVIEW ONLY" in out and "NO FILES WRITTEN" in out
    assert "AllowLiveTrading=0" in out
    assert "InpSourceId=mt5tf20261111" in out
    assert _tree_snapshot(tmp_path) == before
