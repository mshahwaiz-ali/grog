"""Lossless GUI formatting contracts; no Qt or broker dependency."""

from __future__ import annotations

from decimal import Decimal

import pytest

from grog.desktop.presentation import (
    price_text,
    trigger_explanation,
    utc_ms_text,
    utc_text,
    view_time_text,
)


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("4119.96", "4,119.96"),
        ("4120.9900", "4,120.9900"),
        ("0.00001", "0.00001"),
        ("1234567.123456789", "1,234,567.123456789"),
        ("0", "0"),
        ("-0.00", "-0.00"),
    ],
)
def test_display_preserves_decimal_scale_and_digits(raw: str, shown: str) -> None:
    assert price_text(Decimal(raw)) == shown


def test_unknown_price_never_becomes_zero() -> None:
    assert price_text(None) == "\u2014"
    assert price_text(Decimal("NaN")) == "UNKNOWN"
    assert price_text(Decimal("Infinity")) == "UNKNOWN"


def test_utc_is_explicit_and_missing_time_is_not_now() -> None:
    assert utc_text(0) == "1970-01-01 00:00:00 UTC"
    assert utc_text(None) == "\u2014"


def test_forming_trigger_is_not_presented_as_ready() -> None:
    buy = trigger_explanation("BUY", Decimal("4120.99"))
    assert "BID close above 4,120.99" in buy
    assert "No confirmed trade signal yet" in buy
    assert "READY" not in buy


def test_sell_trigger_is_causal_and_not_ready() -> None:
    sell = trigger_explanation("SELL", Decimal("4118.55"))
    assert "BID close below 4,118.55" in sell
    assert "No confirmed trade signal yet" in sell


def test_missing_trigger_is_unknown_and_bad_side_rejected() -> None:
    assert "unavailable" in trigger_explanation("BUY", None)
    with pytest.raises(ValueError, match="Unexpected signal side"):
        trigger_explanation("LONG", Decimal("1.00"))

# U1: only the view changes; persisted/replay/audit clocks remain UTC integers.


def test_view_time_has_named_zone_absolute_date_and_role() -> None:
    ms = 1768497845123  # 2026-01-15 17:24:05.123 UTC
    assert view_time_text(ms) == "15 Jan 2026 · 10:24 PM PKT"
    assert view_time_text(ms, "UTC", clock="provider") == ("Provider 15 Jan 2026 · 05:24 PM UTC")
    assert view_time_text(ms, clock="received") == "Received 15 Jan 2026 · 10:24 PM PKT"
    assert view_time_text(ms, clock="available") == "Available 15 Jan 2026 · 10:24 PM PKT"
    assert view_time_text(ms, clock="replay") == "Replay 15 Jan 2026 · 10:24 PM PKT"
    assert view_time_text(ms, clock="event") == "Event 15 Jan 2026 · 10:24 PM PKT"
    assert view_time_text(ms, clock="recorded") == "Recorded 15 Jan 2026 · 10:24 PM PKT"


def test_detailed_view_and_audit_keep_exact_milliseconds() -> None:
    ms = 1768497845123
    assert view_time_text(ms, detailed=True) == "2026-01-15 22:24:05.123 PKT"
    assert view_time_text(ms, "UTC", detailed=True) == "2026-01-15 17:24:05.123 UTC"
    assert utc_ms_text(ms) == "2026-01-15 17:24:05.123 UTC"
    assert utc_text(ms) == "2026-01-15 17:24:05 UTC"


def test_missing_and_negative_epoch_milliseconds_not_reinterpreted() -> None:
    assert view_time_text(None, clock="recorded") == "Recorded —"
    assert view_time_text(-1, "UTC", detailed=True) == "1969-12-31 23:59:59.999 UTC"
    assert view_time_text(-1, "PKT", detailed=True) == "1970-01-01 04:59:59.999 PKT"
    assert utc_ms_text(-1) == "1969-12-31 23:59:59.999 UTC"


def test_unsupported_view_zone_and_clock_are_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported display zone"):
        view_time_text(0, "LOCAL")
    with pytest.raises(ValueError, match="Unsupported clock role"):
        view_time_text(0, clock="wall")


def test_view_only_timezone_does_not_change_decimal_or_audit_precision() -> None:
    value = Decimal("4119.9600")
    ms = 1768497845123
    before = (price_text(value), utc_ms_text(ms))
    _ = (view_time_text(ms, "PKT"), view_time_text(ms, "UTC"))
    assert (price_text(value), utc_ms_text(ms)) == before
    assert before == ("4,119.9600", "2026-01-15 17:24:05.123 UTC")
