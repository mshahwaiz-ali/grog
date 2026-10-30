"""Injected clocks. Domain code never reads the wall clock directly."""

from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def now_ms(self) -> int:
        """Current UTC epoch milliseconds."""
        ...


class SystemClock:
    """Wall clock, used only for local bookkeeping timestamps (e.g. ``imported_at_ms``)."""

    def now_ms(self) -> int:
        return time.time_ns() // 1_000_000


class FixedClock:
    """Deterministic clock for tests and reproducible runs."""

    def __init__(self, now_ms: int) -> None:
        self._now_ms = now_ms

    def now_ms(self) -> int:
        return self._now_ms
