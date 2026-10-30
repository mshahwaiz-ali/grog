"""Typed, validated Grog configuration and injectable local paths.

Contract: docs/09-architecture.md Sections 7 (directories) and 9 (configuration).

* Configuration is TOML, validated at startup with explicit field-path errors,
  a versioned schema and a reproducible SHA-256 hash.
* Unknown keys, unknown modes, unsafe flags and naive timestamps are rejected.
* Live safety values are unset (absent) by default. An unset live value is not
  permission for unlimited exposure: it blocks the corresponding live mode.
* Nothing here writes to disk, opens a database or touches the network.
"""

from __future__ import annotations

import hashlib
import json
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CONFIG_SCHEMA_VERSION = 1
"""Version of the configuration schema understood by this build."""

KNOWN_MODES = ("REPLAY", "REFERENCE_LIVE", "EXECUTION_VERIFIED")
"""Runtime profiles named in docs/09 Section 5. Only REPLAY is available offline."""

AVAILABLE_MODES = ("REPLAY",)
KNOWN_PROFILES = ("S1_RESEARCH_V0_2",)
KNOWN_SOURCES = ("SYNTHETIC", "HISTORICAL", "REFERENCE_LIVE")
REPLAY_SOURCES = ("SYNTHETIC", "HISTORICAL")
CANONICAL_SYMBOL = "XAUUSD"

STATE_DB_FILENAME = "state.sqlite3"
CONFIG_FILENAME = "config.toml"

# Live safety values (docs/09 Section 9). All unset by default; REFERENCE_LIVE
# readiness is blocked until every one of them is configured and validated.
LIVE_POLICY_FIELDS = (
    "live.max_quote_age_ms",
    "live.max_first_postclose_delay_ms",
    "live.max_spread_cost_r",
    "events.blackout_window",
    "risk.max_account_risk",
)


class ConfigError(ValueError):
    """Configuration or input validation failure with a field path and reason code."""

    def __init__(self, field: str, reason: str, detail: str = "") -> None:
        self.field = field
        self.reason = reason
        self.detail = detail
        message = f"CONFIG_INVALID field={field} reason={reason}"
        if detail:
            message += f" ({detail})"
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class UISettings:
    max_refresh_hz: int = 4


@dataclass(frozen=True, slots=True)
class MarketDataSettings:
    require_bid_ask: bool = True
    strict_no_lookahead: bool = True


@dataclass(frozen=True, slots=True)
class RiskSettings:
    contract_metadata: str = "UNKNOWN"
    live_numeric_score_enabled: bool = False
    live_execution_fidelity: str | None = None
    max_account_risk: Decimal | None = None


@dataclass(frozen=True, slots=True)
class LiveSettings:
    max_quote_age_ms: int | None = None
    max_first_postclose_delay_ms: int | None = None
    max_spread_cost_r: Decimal | None = None


@dataclass(frozen=True, slots=True)
class EventSettings:
    blackout_window: str | None = None


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated, immutable configuration. Defaults are the safe offline profile."""

    config_version: int = CONFIG_SCHEMA_VERSION
    profile: str = "S1_RESEARCH_V0_2"
    mode: str = "REPLAY"
    source: str = "SYNTHETIC"
    symbol: str = CANONICAL_SYMBOL
    timezone_display: str = "Asia/Karachi"
    synthetic_tick_size: Decimal = Decimal("0.01")
    allow_trade_execution: bool = False
    ui: UISettings = UISettings()
    market_data: MarketDataSettings = MarketDataSettings()
    risk: RiskSettings = RiskSettings()
    live: LiveSettings = LiveSettings()
    events: EventSettings = EventSettings()
    config_source: str = "built-in defaults"

    def to_canonical_dict(self) -> dict[str, Any]:
        """Stable, JSON-serializable view (Decimals as exact strings, None kept)."""

        def dec(value: Decimal | None) -> str | None:
            return None if value is None else str(value)

        return {
            "config_version": self.config_version,
            "profile": self.profile,
            "mode": self.mode,
            "source": self.source,
            "symbol": self.symbol,
            "timezone_display": self.timezone_display,
            "synthetic_tick_size": dec(self.synthetic_tick_size),
            "allow_trade_execution": self.allow_trade_execution,
            "ui": {"max_refresh_hz": self.ui.max_refresh_hz},
            "market_data": {
                "require_bid_ask": self.market_data.require_bid_ask,
                "strict_no_lookahead": self.market_data.strict_no_lookahead,
            },
            "risk": {
                "contract_metadata": self.risk.contract_metadata,
                "live_numeric_score_enabled": self.risk.live_numeric_score_enabled,
                "live_execution_fidelity": self.risk.live_execution_fidelity,
                "max_account_risk": dec(self.risk.max_account_risk),
            },
            "live": {
                "max_quote_age_ms": self.live.max_quote_age_ms,
                "max_first_postclose_delay_ms": self.live.max_first_postclose_delay_ms,
                "max_spread_cost_r": dec(self.live.max_spread_cost_r),
            },
            "events": {"blackout_window": self.events.blackout_window},
        }

    @property
    def config_hash(self) -> str:
        """SHA-256 of the canonical validated settings (independent of file formatting)."""
        payload = json.dumps(
            self.to_canonical_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def unset_live_policies(self) -> tuple[str, ...]:
        values = {
            "live.max_quote_age_ms": self.live.max_quote_age_ms,
            "live.max_first_postclose_delay_ms": self.live.max_first_postclose_delay_ms,
            "live.max_spread_cost_r": self.live.max_spread_cost_r,
            "events.blackout_window": self.events.blackout_window,
            "risk.max_account_risk": self.risk.max_account_risk,
        }
        return tuple(name for name in LIVE_POLICY_FIELDS if values[name] is None)


# --------------------------------------------------------------------------- helpers

_TOP_LEVEL_KEYS = {
    "config_version",
    "profile",
    "mode",
    "source",
    "symbol",
    "timezone_display",
    "synthetic_tick_size",
    "allow_trade_execution",
    "ui",
    "market_data",
    "risk",
    "live",
    "events",
}
_TABLE_KEYS = {
    "ui": {"max_refresh_hz"},
    "market_data": {"require_bid_ask", "strict_no_lookahead"},
    "risk": {
        "contract_metadata",
        "live_numeric_score_enabled",
        "live_execution_fidelity",
        "max_account_risk",
    },
    "live": {"max_quote_age_ms", "max_first_postclose_delay_ms", "max_spread_cost_r"},
    "events": {"blackout_window"},
}


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(field, "EXPECTED_NONEMPTY_STRING", f"got {value!r}")
    return value


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(field, "EXPECTED_BOOLEAN", f"got {value!r}")
    return value


def _require_positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(field, "EXPECTED_POSITIVE_INTEGER", f"got {value!r}")
    return value


def _require_positive_decimal(value: Any, field: str) -> Decimal:
    # Decimals must be quoted strings so no binary float ever enters the config.
    if not isinstance(value, str):
        raise ConfigError(field, "EXPECTED_DECIMAL_STRING", f"got {value!r}")
    try:
        number = Decimal(value.strip())
    except InvalidOperation as exc:
        raise ConfigError(field, "INVALID_DECIMAL", f"got {value!r}") from exc
    if not number.is_finite() or number <= 0:
        raise ConfigError(field, "EXPECTED_POSITIVE_DECIMAL", f"got {value!r}")
    return number


def _require_choice(value: Any, field: str, choices: tuple[str, ...], reason: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ConfigError(field, reason, f"got {value!r}; allowed: {', '.join(choices)}")
    return value


def parse_utc_timestamp_ms(text: Any, field: str = "timestamp") -> int:
    """Parse an ISO-8601 timestamp that carries ``Z`` or an explicit offset to UTC epoch ms.

    Timezone-naive input is rejected (no guessed timezone). Sub-millisecond
    precision is rejected rather than silently truncated.
    """
    if not isinstance(text, str) or not text.strip():
        raise ConfigError(field, "INVALID_TIMESTAMP", f"got {text!r}")
    raw = text.strip()
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ConfigError(field, "INVALID_TIMESTAMP", f"not ISO-8601: {raw!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConfigError(
            field, "NAIVE_TIMESTAMP", f"{raw!r} has no 'Z' or UTC offset; timezone is not guessed"
        )
    if parsed.microsecond % 1000:
        raise ConfigError(field, "SUBMILLISECOND_TIMESTAMP", f"{raw!r} exceeds ms precision")
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = parsed - epoch
    return (delta.days * 86_400 + delta.seconds) * 1000 + delta.microseconds // 1000


# --------------------------------------------------------------------------- validation


def settings_from_mapping(data: Mapping[str, Any], config_source: str = "mapping") -> Settings:
    """Validate a decoded TOML mapping into :class:`Settings` (raises :class:`ConfigError`)."""
    if not isinstance(data, Mapping):
        raise ConfigError("<root>", "EXPECTED_TABLE")
    for key in data:
        if key not in _TOP_LEVEL_KEYS:
            raise ConfigError(str(key), "UNKNOWN_KEY")
    for table, allowed in _TABLE_KEYS.items():
        if table in data:
            if not isinstance(data[table], Mapping):
                raise ConfigError(table, "EXPECTED_TABLE")
            for key in data[table]:
                if key not in allowed:
                    raise ConfigError(f"{table}.{key}", "UNKNOWN_KEY")

    defaults = Settings()

    if "config_version" not in data:
        raise ConfigError("config_version", "MISSING_KEY", f"expected {CONFIG_SCHEMA_VERSION}")
    version = data["config_version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise ConfigError("config_version", "EXPECTED_INTEGER", f"got {version!r}")
    if version != CONFIG_SCHEMA_VERSION:
        raise ConfigError(
            "config_version",
            "UNSUPPORTED_VERSION",
            f"got {version}; supported {CONFIG_SCHEMA_VERSION}",
        )

    mode = _require_choice(data.get("mode", defaults.mode), "mode", KNOWN_MODES, "UNKNOWN_MODE")
    profile = _require_choice(
        data.get("profile", defaults.profile), "profile", KNOWN_PROFILES, "UNKNOWN_PROFILE"
    )
    source = _require_choice(
        data.get("source", defaults.source), "source", KNOWN_SOURCES, "UNKNOWN_SOURCE"
    )
    symbol = _require_choice(
        data.get("symbol", defaults.symbol), "symbol", (CANONICAL_SYMBOL,), "UNSUPPORTED_SYMBOL"
    )

    tz_name = _require_str(
        data.get("timezone_display", defaults.timezone_display), "timezone_display"
    )
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError("timezone_display", "UNKNOWN_TIMEZONE", f"got {tz_name!r}") from exc

    tick_raw = data.get("synthetic_tick_size", str(defaults.synthetic_tick_size))
    synthetic_tick_size = _require_positive_decimal(tick_raw, "synthetic_tick_size")

    allow_trade_execution = _require_bool(
        data.get("allow_trade_execution", False), "allow_trade_execution"
    )
    if allow_trade_execution:
        raise ConfigError(
            "allow_trade_execution", "TRADE_EXECUTION_FORBIDDEN", "Grog never places broker orders"
        )

    ui_data = data.get("ui", {})
    ui = UISettings(
        max_refresh_hz=_require_positive_int(
            ui_data.get("max_refresh_hz", defaults.ui.max_refresh_hz), "ui.max_refresh_hz"
        )
    )

    md_data = data.get("market_data", {})
    require_bid_ask = _require_bool(
        md_data.get("require_bid_ask", True), "market_data.require_bid_ask"
    )
    if not require_bid_ask:
        raise ConfigError("market_data.require_bid_ask", "BID_ASK_REQUIRED")
    strict_no_lookahead = _require_bool(
        md_data.get("strict_no_lookahead", True), "market_data.strict_no_lookahead"
    )
    if not strict_no_lookahead:
        raise ConfigError("market_data.strict_no_lookahead", "LOOKAHEAD_FORBIDDEN")
    market_data = MarketDataSettings(require_bid_ask, strict_no_lookahead)

    risk_data = data.get("risk", {})
    contract_metadata = _require_choice(
        risk_data.get("contract_metadata", "UNKNOWN"),
        "risk.contract_metadata",
        ("UNKNOWN",),
        "CONTRACT_METADATA_NOT_SUPPORTED",
    )
    numeric_score = _require_bool(
        risk_data.get("live_numeric_score_enabled", False), "risk.live_numeric_score_enabled"
    )
    if numeric_score:
        raise ConfigError(
            "risk.live_numeric_score_enabled",
            "UNCALIBRATED_SCORE_FORBIDDEN",
            "the 100-point score is not calibrated or implemented",
        )
    fidelity = risk_data.get("live_execution_fidelity")
    if fidelity is not None:
        fidelity = _require_choice(
            fidelity, "risk.live_execution_fidelity", ("REFERENCE",), "UNKNOWN_FIDELITY"
        )
    max_account_risk = risk_data.get("max_account_risk")
    if max_account_risk is not None:
        max_account_risk = _require_positive_decimal(max_account_risk, "risk.max_account_risk")
    risk = RiskSettings(contract_metadata, numeric_score, fidelity, max_account_risk)

    live_data = data.get("live", {})
    quote_age = live_data.get("max_quote_age_ms")
    if quote_age is not None:
        quote_age = _require_positive_int(quote_age, "live.max_quote_age_ms")
    postclose = live_data.get("max_first_postclose_delay_ms")
    if postclose is not None:
        postclose = _require_positive_int(postclose, "live.max_first_postclose_delay_ms")
    spread_cost = live_data.get("max_spread_cost_r")
    if spread_cost is not None:
        spread_cost = _require_positive_decimal(spread_cost, "live.max_spread_cost_r")
    live = LiveSettings(quote_age, postclose, spread_cost)

    events_data = data.get("events", {})
    blackout = events_data.get("blackout_window")
    if blackout is not None:
        # Exact event-policy format is OPEN (docs/11 Section 6); only presence is checked.
        blackout = _require_str(blackout, "events.blackout_window")
    events = EventSettings(blackout)

    settings = Settings(
        config_version=version,
        profile=profile,
        mode=mode,
        source=source,
        symbol=symbol,
        timezone_display=tz_name,
        synthetic_tick_size=synthetic_tick_size,
        allow_trade_execution=False,
        ui=ui,
        market_data=market_data,
        risk=risk,
        live=live,
        events=events,
        config_source=config_source,
    )
    _validate_mode_policy(settings)
    return settings


def _validate_mode_policy(settings: Settings) -> None:
    if settings.mode == "REPLAY":
        if settings.source not in REPLAY_SOURCES:
            raise ConfigError(
                "source",
                "SOURCE_NOT_ALLOWED_FOR_MODE",
                f"REPLAY accepts {', '.join(REPLAY_SOURCES)}; got {settings.source!r}",
            )
        return
    if settings.mode == "REFERENCE_LIVE":
        missing = settings.unset_live_policies()
        if missing:
            raise ConfigError(
                missing[0],
                "LIVE_POLICY_UNSET",
                "REFERENCE_LIVE is blocked until all live safety values are configured: "
                + ", ".join(missing),
            )
        if settings.risk.live_execution_fidelity != "REFERENCE":
            raise ConfigError("risk.live_execution_fidelity", "LIVE_POLICY_UNSET")
    # Known but not available in this offline build (M09 needs separate authorization).
    raise ConfigError(
        "mode",
        "MODE_NOT_AVAILABLE",
        f"{settings.mode} is not available in this offline build; use REPLAY",
    )


# --------------------------------------------------------------------------- loading and paths


def _env_dir(env: Mapping[str, str], var: str, fallback: tuple[str, ...]) -> Path:
    value = env.get(var, "")
    # XDG spec: relative paths are invalid and must be ignored.
    if value and Path(value).is_absolute():
        return Path(value)
    home = env.get("HOME") or str(Path.home())
    return Path(home).joinpath(*fallback)


def default_config_path(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return _env_dir(env, "XDG_CONFIG_HOME", (".config",)) / "grog" / CONFIG_FILENAME


def default_state_dir(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return _env_dir(env, "XDG_DATA_HOME", (".local", "share")) / "grog"


def resolve_state_dir(
    explicit: str | os.PathLike[str] | None, env: Mapping[str, str] | None = None
) -> tuple[Path, str]:
    """Return ``(state_dir, origin)``; an explicit ``--state-dir`` always wins. Never creates it."""
    if explicit is not None and str(explicit) != "":
        return Path(explicit).expanduser().absolute(), "--state-dir"
    return default_state_dir(env), "XDG default"


def load_settings(
    path: str | os.PathLike[str] | None = None, env: Mapping[str, str] | None = None
) -> Settings:
    """Load settings read-only: explicit path, else XDG user config if present, else defaults."""
    if path is not None:
        config_path = Path(path).expanduser()
        if not config_path.is_file():
            raise ConfigError("--config", "CONFIG_NOT_FOUND", str(config_path))
    else:
        config_path = default_config_path(env)
        if not config_path.is_file():
            return Settings()
    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(str(config_path), "CONFIG_PARSE_ERROR", str(exc)) from exc
    except OSError as exc:
        raise ConfigError(str(config_path), "CONFIG_UNREADABLE", str(exc)) from exc
    return settings_from_mapping(data, config_source=str(config_path))
