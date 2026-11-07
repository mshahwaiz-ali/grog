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


def quote_metric(bid: str, ask: str, side: str = "") -> str:
    """Prominent sourced quote display. Exact values preserved."""
    if side == "BUY":
        return f"ASK {ask}"
    if side == "SELL":
        return f"BID {bid}"
    return f"BID {bid} / ASK {ask}"


def reason_summary(codes: list[str]) -> str:
    """Human-readable reason summary. Full codes available in detail."""
    if not codes:
        return "No additional reasons"
    return "; ".join(codes[:3]) + ("..." if len(codes) > 3 else "")


def empty_state(page: str) -> str:
    """Human empty state for pages."""
    return {
        "signals": "No developing or ready signals right now",
        "positions": "No open manual positions",
        "journal": "No journal events yet",
    }.get(page, "Nothing to show")


def provenance_line(source_id: str, mode: str) -> str:
    """Source provenance for summaries. Full details in audit."""
    return f"Source {source_id} · {mode}"


def alert_banner(severity: str, message: str) -> str:
    """Human alert for fault/warning states."""
    return f"{severity.upper()}: {message}"


def confirmation_footer(action: str) -> str:
    """Confirmation text for manual forms. No broker order."""
    return f"Confirm {action} (local record only · no broker order)"


def exact_value_row(label: str, value: str) -> str:
    """Exact value for audit/detail rows."""
    return f"{label}: {value}"


def market_context(h1: str, m15: str, m5: str) -> str:
    """Market context row for Overview."""
    return f"H1 {h1} · M15 {m15} · M5 {m5}"


def timeline_entry(time: str, event: str) -> str:
    """Timeline entry for Journal."""
    return f"{time} · {event}"


def filter_bar(active: int, total: int) -> str:
    """Filter bar summary for Signals/Journal."""
    return f"Showing {active} of {total}"


def dialog_section(title: str) -> str:
    """Section title for forms and dialogs."""
    return title


def key_value_list(pairs: list[tuple[str, str]]) -> str:
    """Key-value list for detail panels."""
    return "\n".join(f"{k}: {v}" for k, v in pairs)


def page_heading(title: str, purpose: str = "") -> str:
    """Page heading with optional purpose."""
    return title if not purpose else f"{title}\n{purpose}"


def compact_table_header(*columns: str) -> str:
    """Compact table header for Signals/Positions."""
    return " | ".join(columns)


def detail_panel(title: str, body: str) -> str:
    """Detail panel content."""
    return f"{title}\n{body}"


def status_pill(text: str, tone: str = "info") -> str:
    """Status pill text. Color comes from theme."""
    return text
