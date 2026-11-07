"""UI-neutral, lossless formatting for the future native workstation.

These functions never round, reinterpret market timing, or decide signal eligibility.
Keep market decisions in the existing engine and journal, not in a frontend.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

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


# A named view zone is never inferred from the machine's local timezone.
PKT_ZONE = ZoneInfo("Asia/Karachi")

CLOCK_ROLES = {
    "provider": "Provider",
    "received": "Received",
    "available": "Available",
    "replay": "Replay",
    "event": "Event",
    "recorded": "Recorded",
}


def _utc_parts(timestamp_ms: int) -> tuple[datetime, int]:
    """Split integer epoch milliseconds without binary floating-point conversion."""
    seconds, milliseconds = divmod(timestamp_ms, 1000)
    return datetime.fromtimestamp(seconds, tz=UTC), milliseconds


def utc_text(timestamp_ms: int | None) -> str:
    """Show source/event time as UTC, never the computer's local clock."""
    if timestamp_ms is None:
        return UNAVAILABLE
    moment, _milliseconds = _utc_parts(timestamp_ms)
    return f"{moment:%Y-%m-%d %H:%M:%S} UTC"


def utc_ms_text(timestamp_ms: int | None) -> str:
    """UTC with the source's exact millisecond (receipt/availability times are ms-precise)."""
    if timestamp_ms is None:
        return UNAVAILABLE
    moment, milliseconds = _utc_parts(timestamp_ms)
    return f"{moment:%Y-%m-%d %H:%M:%S}.{milliseconds:03d} UTC"


def view_time_text(
    timestamp_ms: int | None,
    zone: str = "PKT",
    *,
    detailed: bool = False,
    clock: str | None = None,
) -> str:
    """Format a display-only clock with its explicit role, date and PKT/UTC zone.

    Compact replay history always includes an absolute date; the optional detailed
    form retains milliseconds. This never modifies the UTC integer or audit output.
    """
    if zone not in ("PKT", "UTC"):
        raise ValueError(f"Unsupported display zone: {zone!r}")
    if clock is not None and clock not in CLOCK_ROLES:
        raise ValueError(f"Unsupported clock role: {clock!r}")

    if timestamp_ms is None:
        shown = UNAVAILABLE
    else:
        instant, milliseconds = _utc_parts(timestamp_ms)
        if zone == "PKT":
            instant = instant.astimezone(PKT_ZONE)
        if detailed:
            shown = f"{instant:%Y-%m-%d %H:%M:%S}.{milliseconds:03d} {zone}"
        else:
            shown = f"{instant.day} {instant:%b %Y} · {instant:%I:%M %p} {zone}"
    return f"{CLOCK_ROLES[clock]} {shown}" if clock is not None else shown


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
