"""Shared synthetic S1 M5/H1 fixtures (docs/08 S1 cases). Synthetic only, no market claim."""

from __future__ import annotations

from decimal import Decimal

from grog.domain.enums import Timeframe
from quote_stream import T10, make_bar

H1, M15, M5 = Timeframe.H1, Timeframe.M15, Timeframe.M5

HOUR = 3_600_000

WARM = [("4000.5", "3999.5", "4000", "4000")] * 16  # equal highs/lows: no pivots, ATR ~ 1
PATTERN = [  # (high, low, open, close) indices 16..23: L at 17 (3998), H at 21 (4006)
    ("4000.5", "3999.0", "4000", "3999.5"),
    ("4000.0", "3998.0", "3999.5", "3999.0"),
    ("4001.0", "3999.0", "3999", "4000.5"),
    ("4003.0", "4000.5", "4000.5", "4002.5"),
    ("4005.0", "4002.0", "4002.5", "4004.5"),
    ("4006.0", "4003.5", "4004.5", "4004.0"),
    ("4005.0", "4003.0", "4004.0", "4003.5"),
    ("4004.0", "4002.5", "4003.5", "4003.0"),  # confirms H; P = 4002.5, d = 0.4375
]
TRIGGER = ("4005.8", "4002.8", "4003.0", "4005.5")  # close 4005.5 > max(4005, 4004), bullish
L_PRICE, H_PRICE, IMPULSE = Decimal("3998.0"), Decimal("4006.0"), Decimal("8.0")
H_CONFIRM = 23  # index of the bar that confirms H


def flip(spec: tuple[str, str, str, str]) -> tuple[str, str, str, str]:
    h, lo, o, c = (Decimal(x) for x in spec)
    return tuple(str(8000 - x) for x in (lo, h, o, c))  # type: ignore[return-value]


def m5(specs, base_ms: int = T10, mirror: bool = False, ask_offset: str = "0.20"):
    out = []
    for i, spec in enumerate(specs):
        h, lo, o, c = flip(spec) if mirror else spec
        out.append(make_bar(M5, i, h, lo, c, o, base_ms=base_ms, ask_offset=ask_offset))
    return out


def h1_trend(up: bool = True, n: int = 260, end_ms: int = T10, mirror: bool = False):
    step = 1 if up else -1
    bars = []
    for i in range(n):
        c = Decimal(4000 + step * i) if up else Decimal(4300 + step * i)
        if mirror:
            c = 8000 - c
        bars.append(make_bar(H1, i, str(c + 1), str(c - 1), str(c), base_ms=end_ms - n * HOUR))
    return bars
