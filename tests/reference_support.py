"""Recorded-format (GROG-MT5-REF/1) fixture writer for the M09 reference adapter tests.

Every file written here declares producer FIXTURE: its quotes are SIMULATED test data and are
displayed as ``FIXTURE · SIMULATED``, never as live reference prices.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from grog.domain.models import DataHealthPolicy
from grog.signals.engine import SignalPolicy

SRC = "syn"
OFFSET_S = 7200  # fixture trade-server offset (server = UTC+2); a test value, not a broker fact
T0 = 1_790_812_800_000  # 2026-10-01 00:00:00 UTC
POLICY = SignalPolicy(  # fixture-only declarations of OPEN thresholds (never broker values)
    health=DataHealthPolicy(max_quote_age_ms=60_000, max_first_postclose_delay_ms=30_000),
    price_step=Decimal("0.01"),
)
HB_AGE = 5_000  # fixture-only heartbeat threshold


class StepClock:
    def __init__(self, now_ms: int) -> None:
        self.now = now_ms

    def now_ms(self) -> int:
        return self.now


def srv(utc_ms: int) -> int:
    """UTC -> fixture trade-server time_msc."""
    return utc_ms + OFFSET_S * 1000


class Writer:
    """Appends exporter-format lines exactly like the MQL5 exporter would (complete lines)."""

    def __init__(
        self,
        directory: Path,
        session: str = "20261001T000000Z",
        part: int = 1,
        source: str = SRC,
        digits: int = 2,
        offset_s: int = OFFSET_S,
        producer: str = "FIXTURE",
    ) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.source, self.digits, self.offset_s, self.producer = source, digits, offset_s, producer
        self.open(session, part)

    def open(self, session: str, part: int) -> None:
        self.name = f"{self.source}__{session}__{part:06d}.grogref"
        self.seq = 0
        self.line(
            f"M,{{seq}},GROG-MT5-REF/1,{self.producer},{self.source},Fixture-Demo-Server,"
            f"XAUUSD.fx,{self.digits},{self.offset_s},fixture-1"
        )

    @property
    def path(self) -> Path:
        return self.directory / self.name

    def raw(self, text: str) -> None:
        with self.path.open("a", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def line(self, template: str) -> int:
        self.seq += 1
        self.raw(template.replace("{seq}", str(self.seq)) + "\n")
        return self.seq

    def tick(self, utc_ms: int, bid: str, ask: str, flags: int = 6, mode: str = "L") -> int:
        return self.line(f"T,{{seq}},{mode},{srv(utc_ms)},{bid},{ask},{flags}")

    def hb(self, utc_ms: int, connected: int = 1, session: str = "OPEN") -> int:
        return self.line(f"H,{{seq}},{srv(utc_ms)},{connected},{session},{self.offset_s}")

    def begin(self, utc_ms: int) -> int:
        return self.line(f"B,{{seq}},{srv(utc_ms)}")

    def end(self, utc_ms: int, count: int) -> int:
        return self.line(f"E,{{seq}},{srv(utc_ms)},{count}")

    def eof(self, next_name: str = "-") -> int:
        return self.line(f"Z,{{seq}},{next_name}")
