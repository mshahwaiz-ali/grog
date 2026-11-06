"""Lossless GUI formatting contracts; no Qt or broker dependency."""

from __future__ import annotations

from decimal import Decimal

import pytest

from grog.desktop.presentation import price_text, trigger_explanation, utc_text


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
