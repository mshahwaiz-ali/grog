"""UI-neutral, lossless formatting for the future native workstation.

These functions never round, reinterpret market timing, or decide signal eligibility.
Keep market decisions in the existing engine and journal, not in a frontend.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

UNAVAILABLE = "\u2014"
UNKNOWN = "UNKNOWN"


def price_text(value: Decimal | None) -> str:
    """Group thousands while preserving the exact Decimal fractional scale.

    The display never guesses a universal XAUUSD tick size or rounds a trading
    price. Later source-specific precision comes from validated source metadata.
    """
    if value is None:
        return UNAVAILABLE
    if not value.is_finite():
        return UNKNOWN
    return format(value, ",f")


def utc_text(timestamp_ms: int | None) -> str:
    """Show source/event time as UTC, never the computer's local clock."""
    if timestamp_ms is None:
        return UNAVAILABLE
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def utc_ms_text(timestamp_ms: int | None) -> str:
    """UTC with the source's exact millisecond (receipt/availability times are ms-precise)."""
    if timestamp_ms is None:
        return UNAVAILABLE
    moment = datetime.fromtimestamp(timestamp_ms // 1000, tz=UTC)
    return f"{moment:%Y-%m-%d %H:%M:%S}.{timestamp_ms % 1000:03d} UTC"


def trigger_explanation(side: str, threshold: Decimal | None) -> str:
    """Describe the *pending* M5 BID close condition, never infer READY.

    Call only for an engine-confirmed FORMING candidate: this is a formatter,
    not a replacement for the strategy/eligibility gates.
    """
    if threshold is None or not threshold.is_finite():
        return "The next 5-minute trigger level is unavailable."
    if side == "BUY":
        return (
            "Waiting for a completed bullish 5-minute candle with a BID close "
            f"above {price_text(threshold)}. No confirmed trade signal yet."
        )
    if side == "SELL":
        return (
            "Waiting for a completed bearish 5-minute candle with a BID close "
            f"below {price_text(threshold)}. No confirmed trade signal yet."
        )
    raise ValueError(f"Unexpected signal side: {side!r}")


from zoneinfo import ZoneInfo

PKT = ZoneInfo("Asia/Karachi")


def human_time(timestamp_ms: int | None, zone: str = "PKT") -> str:
    """Human-facing summary time. Exact UTC remains available via utc_ms_text."""
    if timestamp_ms is None:
        return UNAVAILABLE
    tz = PKT if zone == "PKT" else UTC
    moment = datetime.fromtimestamp(timestamp_ms / 1000, tz=tz)
    return moment.strftime("%H:%M %Z") if zone == "PKT" else moment.strftime("%H:%M UTC")


def human_datetime(timestamp_ms: int | None, zone: str = "PKT") -> str:
    if timestamp_ms is None:
        return UNAVAILABLE
    tz = PKT if zone == "PKT" else UTC
    moment = datetime.fromtimestamp(timestamp_ms / 1000, tz=tz)
    return moment.strftime("%d %b · %H:%M %Z")


def status_label(raw: str) -> str:
    """Human-facing status. Exact codes remain accessible in detail."""
    mapping = {
        "FORMING": "Developing · NOT TRADABLE",
        "READY": "READY · SIMULATED",
        "NO TRADE": "No trade",
    }
    return mapping.get(raw, raw)


def decision_headline(state: str) -> str:
    """Primary decision headline for Overview. Exact state remains in detail."""
    return {
        "NO TRADE": "No trade right now",
        "FORMING": "Developing · not tradable yet",
        "READY": "READY research proposal",
    }.get(state, state)
