"""Configuration validation (docs/09 Section 9; CL-11)."""

from __future__ import annotations

import copy
import tomllib
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from grog.settings import (
    ConfigError,
    Settings,
    default_config_path,
    default_state_dir,
    load_settings,
    parse_utc_timestamp_ms,
    resolve_state_dir,
    settings_from_mapping,
)

EXAMPLE_CONFIG = Path(__file__).resolve().parents[2] / "config" / "research.example.toml"

FULL_LIVE_POLICIES: dict[str, Any] = {
    "live": {
        "max_quote_age_ms": 1500,
        "max_first_postclose_delay_ms": 3000,
        "max_spread_cost_r": "0.25",
    },
    "events": {"blackout_window": "user-defined"},
    "risk": {"max_account_risk": "0.005", "live_execution_fidelity": "REFERENCE"},
}


def example_data() -> dict[str, Any]:
    with EXAMPLE_CONFIG.open("rb") as handle:
        return tomllib.load(handle)


def with_changes(**changes: Any) -> dict[str, Any]:
    data = copy.deepcopy(example_data())
    for dotted, value in changes.items():
        parts = dotted.split("__")
        target = data
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
    return data


def assert_rejects(data: dict[str, Any], field: str, reason: str) -> None:
    with pytest.raises(ConfigError) as info:
        settings_from_mapping(data)
    assert (info.value.field, info.value.reason) == (field, reason), str(info.value)


# ---------------------------------------------------------------- positive / defaults


def test_example_config_is_valid_and_equals_safe_defaults() -> None:
    loaded = load_settings(EXAMPLE_CONFIG)
    defaults = Settings()
    assert loaded.config_source == str(EXAMPLE_CONFIG)
    assert loaded.to_canonical_dict() == defaults.to_canonical_dict()
    assert loaded.config_hash == defaults.config_hash
    assert loaded.mode == "REPLAY" and loaded.source == "SYNTHETIC"
    assert loaded.profile == "S1_RESEARCH_V0_2" and loaded.symbol == "XAUUSD"
    assert loaded.synthetic_tick_size == Decimal("0.01")
    assert loaded.allow_trade_execution is False
    assert loaded.risk.contract_metadata == "UNKNOWN"
    assert loaded.risk.live_numeric_score_enabled is False
    assert len(loaded.unset_live_policies()) == 5


def test_example_config_contains_no_secret_like_keys() -> None:
    text = EXAMPLE_CONFIG.read_text(encoding="utf-8").lower()
    for word in ("password", "token", "api_key", "secret =", "login =", "account ="):
        assert word not in text


def test_config_hash_is_reproducible_and_sensitive() -> None:
    a = settings_from_mapping(example_data())
    b = settings_from_mapping(example_data())
    assert a.config_hash == b.config_hash and len(a.config_hash) == 64
    c = settings_from_mapping(with_changes(ui__max_refresh_hz=2))
    assert c.config_hash != a.config_hash


def test_historical_source_allowed_in_replay() -> None:
    assert settings_from_mapping(with_changes(source="HISTORICAL")).source == "HISTORICAL"


def test_minimal_config_falls_back_to_safe_defaults() -> None:
    s = settings_from_mapping({"config_version": 1})
    assert s.to_canonical_dict() == Settings().to_canonical_dict()


def test_settings_are_immutable() -> None:
    s = Settings()
    with pytest.raises(AttributeError):
        s.mode = "REFERENCE_LIVE"  # type: ignore[misc]


# ---------------------------------------------------------------- negative


@pytest.mark.parametrize("mode", ["LIVE", "replay", "AUTO_TRADE", ""])
def test_rejects_unknown_mode(mode: str) -> None:
    assert_rejects(with_changes(mode=mode), "mode", "UNKNOWN_MODE")


def test_rejects_unknown_keys_with_field_path() -> None:
    assert_rejects(with_changes(broker_password="x"), "broker_password", "UNKNOWN_KEY")
    assert_rejects(with_changes(ui__theme="light"), "ui.theme", "UNKNOWN_KEY")


@pytest.mark.parametrize(
    ("changes", "field", "reason"),
    [
        ({"allow_trade_execution": True}, "allow_trade_execution", "TRADE_EXECUTION_FORBIDDEN"),
        ({"allow_trade_execution": "false"}, "allow_trade_execution", "EXPECTED_BOOLEAN"),
        (
            {"risk__live_numeric_score_enabled": True},
            "risk.live_numeric_score_enabled",
            "UNCALIBRATED_SCORE_FORBIDDEN",
        ),
        (
            {"market_data__require_bid_ask": False},
            "market_data.require_bid_ask",
            "BID_ASK_REQUIRED",
        ),
        (
            {"market_data__strict_no_lookahead": False},
            "market_data.strict_no_lookahead",
            "LOOKAHEAD_FORBIDDEN",
        ),
        (
            {"risk__contract_metadata": "1 lot = 100 oz"},
            "risk.contract_metadata",
            "CONTRACT_METADATA_NOT_SUPPORTED",
        ),
        ({"symbol": "BTCUSD"}, "symbol", "UNSUPPORTED_SYMBOL"),
        ({"profile": "S1_TUNED"}, "profile", "UNKNOWN_PROFILE"),
        ({"source": "REFERENCE_LIVE"}, "source", "SOURCE_NOT_ALLOWED_FOR_MODE"),
        ({"source": "MIXED"}, "source", "UNKNOWN_SOURCE"),
        ({"timezone_display": "Mars/Base"}, "timezone_display", "UNKNOWN_TIMEZONE"),
        ({"synthetic_tick_size": 0.01}, "synthetic_tick_size", "EXPECTED_DECIMAL_STRING"),
        ({"synthetic_tick_size": "NaN"}, "synthetic_tick_size", "EXPECTED_POSITIVE_DECIMAL"),
        ({"synthetic_tick_size": "-0.01"}, "synthetic_tick_size", "EXPECTED_POSITIVE_DECIMAL"),
        ({"synthetic_tick_size": "abc"}, "synthetic_tick_size", "INVALID_DECIMAL"),
        ({"ui__max_refresh_hz": 0}, "ui.max_refresh_hz", "EXPECTED_POSITIVE_INTEGER"),
        ({"ui__max_refresh_hz": True}, "ui.max_refresh_hz", "EXPECTED_POSITIVE_INTEGER"),
        ({"live__max_quote_age_ms": -1}, "live.max_quote_age_ms", "EXPECTED_POSITIVE_INTEGER"),
        ({"config_version": 2}, "config_version", "UNSUPPORTED_VERSION"),
    ],
)
def test_rejects_invalid_values(changes: dict[str, Any], field: str, reason: str) -> None:
    assert_rejects(with_changes(**changes), field, reason)


def test_rejects_missing_config_version() -> None:
    data = example_data()
    del data["config_version"]
    assert_rejects(data, "config_version", "MISSING_KEY")


def test_reference_live_rejected_while_live_policies_unset() -> None:
    assert_rejects(
        with_changes(mode="REFERENCE_LIVE", source="REFERENCE_LIVE"),
        "live.max_quote_age_ms",
        "LIVE_POLICY_UNSET",
    )


def test_reference_live_rejects_each_single_unset_policy() -> None:
    for missing in (
        "live.max_quote_age_ms",
        "live.max_first_postclose_delay_ms",
        "live.max_spread_cost_r",
        "events.blackout_window",
        "risk.max_account_risk",
    ):
        data = copy.deepcopy(FULL_LIVE_POLICIES)
        table, key = missing.split(".")
        del data[table][key]
        data.update(config_version=1, mode="REFERENCE_LIVE", source="REFERENCE_LIVE")
        assert_rejects(data, missing, "LIVE_POLICY_UNSET")


def test_reference_live_not_available_offline_even_when_configured() -> None:
    data = copy.deepcopy(FULL_LIVE_POLICIES)
    data.update(config_version=1, mode="REFERENCE_LIVE", source="REFERENCE_LIVE")
    assert_rejects(data, "mode", "MODE_NOT_AVAILABLE")


def test_execution_verified_not_available() -> None:
    assert_rejects(with_changes(mode="EXECUTION_VERIFIED"), "mode", "MODE_NOT_AVAILABLE")


def test_load_settings_errors(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as missing:
        load_settings(tmp_path / "nope.toml")
    assert missing.value.reason == "CONFIG_NOT_FOUND"
    bad = tmp_path / "bad.toml"
    bad.write_text("config_version = = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError) as parse:
        load_settings(bad)
    assert parse.value.reason == "CONFIG_PARSE_ERROR"


# ---------------------------------------------------------------- timestamps


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1970-01-01T00:00:00Z", 0),
        ("2026-10-31T10:05:00Z", 1793441100000),
        ("2026-10-31T15:05:00+05:00", 1793441100000),
        ("2026-10-31T10:05:00.123Z", 1793441100123),
        ("1969-12-31T23:59:59.999Z", -1),
    ],
)
def test_parse_utc_timestamp_ms_accepts_explicit_offsets(text: str, expected: int) -> None:
    assert parse_utc_timestamp_ms(text, "--from") == expected


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("2026-10-31T10:05:00", "NAIVE_TIMESTAMP"),
        ("2026-10-31", "NAIVE_TIMESTAMP"),
        ("31/10/2026 10:05", "INVALID_TIMESTAMP"),
        ("1793441100000", "INVALID_TIMESTAMP"),
        ("", "INVALID_TIMESTAMP"),
        (1793441100000, "INVALID_TIMESTAMP"),
        ("2026-10-31T10:05:00.123456Z", "SUBMILLISECOND_TIMESTAMP"),
        ("2026-13-01T00:00:00Z", "INVALID_TIMESTAMP"),
    ],
)
def test_parse_utc_timestamp_ms_rejects_invalid(text: Any, reason: str) -> None:
    with pytest.raises(ConfigError) as info:
        parse_utc_timestamp_ms(text, "--from")
    assert info.value.reason == reason and info.value.field == "--from"


# ---------------------------------------------------------------- paths


def test_state_dir_injection_and_xdg_defaults(tmp_path: Path) -> None:
    env = {"HOME": str(tmp_path / "h")}
    assert default_state_dir(env) == tmp_path / "h" / ".local" / "share" / "grog"
    assert default_config_path(env) == tmp_path / "h" / ".config" / "grog" / "config.toml"
    env_xdg = {"HOME": str(tmp_path / "h"), "XDG_DATA_HOME": str(tmp_path / "xdg")}
    assert default_state_dir(env_xdg) == tmp_path / "xdg" / "grog"
    # Relative XDG values are invalid per the XDG spec and are ignored.
    env_rel = {"HOME": str(tmp_path / "h"), "XDG_DATA_HOME": "relative/dir"}
    assert default_state_dir(env_rel) == tmp_path / "h" / ".local" / "share" / "grog"
    explicit, origin = resolve_state_dir(tmp_path / "state", env)
    assert (explicit, origin) == (tmp_path / "state", "--state-dir")
    assert resolve_state_dir(None, env) == (default_state_dir(env), "XDG default")
    assert not (tmp_path / "state").exists() and not (tmp_path / "h").exists()


def test_user_config_discovered_via_xdg(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "cfg" / "grog"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.toml").write_text(
        'config_version = 1\nsource = "HISTORICAL"\n', encoding="utf-8"
    )
    s = load_settings(None, {"HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "cfg")})
    assert s.source == "HISTORICAL" and s.config_source == str(cfg_dir / "config.toml")
    assert (
        load_settings(None, {"HOME": str(tmp_path / "none")}).config_source == "built-in defaults"
    )
