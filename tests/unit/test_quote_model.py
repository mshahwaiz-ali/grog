"""NormalizedQuote invariants (docs/09 Section 3.1)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from grog.domain.enums import SourceOrigin
from grog.domain.ids import batch_id, canonical_json, is_valid_source_id, source_event_key
from grog.domain.models import NormalizedQuote


def make(**overrides: object) -> NormalizedQuote:
    base: dict[str, object] = {
        "source_id": "syn-1",
        "canonical_symbol": "XAUUSD",
        "raw_symbol": "XAUUSD",
        "provider_time_ms": 1793440000000,
        "received_time_ms": 1793440000000,
        "ingest_order": 1,
        "bid": Decimal("4000.00"),
        "ask": Decimal("4000.20"),
        "source_origin": SourceOrigin.SYNTHETIC,
        "source_event_key": "abc#1",
    }
    base.update(overrides)
    return NormalizedQuote(**base)  # type: ignore[arg-type]


def test_valid_quote_is_frozen_and_exact() -> None:
    q = make()
    assert q.spread == Decimal("0.20") and str(q.bid) == "4000.00"
    assert q.flags == frozenset()
    with pytest.raises(FrozenInstanceError):
        q.bid = Decimal("1")  # type: ignore[misc]


def test_zero_spread_allowed_boundary() -> None:
    assert make(ask=Decimal("4000.00")).spread == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"ask": Decimal("3999.99")},
        {"bid": Decimal("0")},
        {"bid": Decimal("-1"), "ask": Decimal("1")},
        {"bid": 4000.0},
        {"ask": Decimal("NaN")},
        {"canonical_symbol": "XAUUSD.m"},
        {"source_id": ""},
        {"source_id": "../escape"},
        {"provider_time_ms": -1},
        {"provider_time_ms": True},
        {"ingest_order": 0},
        {"source_origin": "SYNTHETIC"},
        {"source_event_key": ""},
        {"flags": {"X"}},
    ],
)
def test_invalid_quotes_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        make(**overrides)


def test_identity_is_not_timestamp() -> None:
    a = make()
    b = replace(a, ingest_order=2, source_event_key="abc#2", bid=Decimal("4000.01"))
    assert a.provider_time_ms == b.provider_time_ms and a != b


def test_ids_are_deterministic() -> None:
    assert source_event_key("f" * 64, 7) == "f" * 64 + "#7"
    assert batch_id("a", "f" * 64) == batch_id("a", "f" * 64) != batch_id("b", "f" * 64)
    assert canonical_json({"b": 1, "a": [1, 2]}) == '{"a":[1,2],"b":1}'
    assert is_valid_source_id("Dukascopy_XAUUSD.2026-10")
    for bad in ("", "-x", "a/b", "a b", "x" * 65, None):
        assert not is_valid_source_id(bad)
