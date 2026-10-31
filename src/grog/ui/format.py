"""Pure text formatting for the workstation (docs/02 §11). No Textual import."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

UNKNOWN = "UNKNOWN"
DASH = "—"


def utc(ms: int | None, *, seconds: bool = True) -> str:
    if ms is None:
        return DASH
    fmt = "%Y-%m-%d %H:%M:%S" if seconds else "%Y-%m-%d %H:%M"
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime(fmt) + " UTC"


def hms(ms: int | None) -> str:
    if ms is None:
        return DASH
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%H:%M:%S")


def price(value: Decimal | None) -> str:
    """Source precision, never scientific notation; missing is shown, never as 0."""
    if value is None:
        return DASH
    return format(value, "f")


def r_short(value: Decimal | None) -> str:
    """Signed R with at most 2 decimals for tables (docs/02 §11)."""
    if value is None:
        return UNKNOWN
    return f"{value.quantize(Decimal('0.01')):+}R"


def duration(ms: int | None) -> str:
    if ms is None:
        return DASH
    sign = "-" if ms < 0 else ""
    s = abs(ms) // 1000
    if s >= 3600:
        return f"{sign}{s // 3600}h{s % 3600 // 60:02d}m"
    if s >= 60:
        return f"{sign}{s // 60}m{s % 60:02d}s"
    return f"{sign}{abs(ms) / 1000:.1f}s"


def short_id(full: str | None) -> str:
    """Compact display id (full id is always available in details)."""
    if not full:
        return DASH
    head, _, tail = full.rpartition("-")
    return f"{head}-{tail[:6]}" if head else full[:10]


def pace_label(pace: int | None) -> str:
    return "FAST" if pace is None else f"{pace} ev/s"
