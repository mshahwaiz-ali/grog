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


class ReplayClock:
    """Virtual deterministic UTC clock for REPLAY: it is the time of the latest processed event.

    It only moves forward and never reads the wall clock.
    """

    def __init__(self, start_ms: int | None = None) -> None:
        self._now_ms = start_ms

    @property
    def started(self) -> bool:
        return self._now_ms is not None

    def advance_to(self, event_ms: int) -> None:
        if self._now_ms is not None and event_ms < self._now_ms:
            raise ValueError(f"replay clock cannot move backwards ({event_ms} < {self._now_ms})")
        self._now_ms = event_ms

    def now_ms(self) -> int:
        if self._now_ms is None:
            raise RuntimeError("replay clock has not processed any event yet")
        return self._now_ms
