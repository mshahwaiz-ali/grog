"""Deterministic SYNTHETIC XAUUSD BID/ASK tick generator (canonical CSV v1).

Purpose: a stream **long enough** for complete warm-up (250 finalized H1 bars for
EMA50 = ~10.4 days of continuous data, plus M15/M5 history) so replays exercise the
full S1 path. It is a seeded random walk with alternating drift regimes. It is NOT a
model of real gold prices and makes **no market claim**; import it with
``--origin SYNTHETIC`` only.

Usage (writes one file, nothing else)::

    python -m grog.replay.synthetic --out synthetic.csv [--days 20] [--seed 7]
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from grog.market_data.import_csv import HEADER

DEFAULT_START_MS = 1790812800000  # 2026-10-01T00:00:00Z
DEFAULT_DAYS = 20  # 250 H1 warm-up bars (~10.4 days) + ~9.6 days of decision window
DEFAULT_STEP_MS = 15_000
WARMUP_H1_BARS = 250


def _price(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def generate_csv(
    *,
    days: int = DEFAULT_DAYS,
    seed: int = 7,
    start_ms: int = DEFAULT_START_MS,
    step_ms: int = DEFAULT_STEP_MS,
    start_cents: int = 400_000,
) -> bytes:
    """Canonical CSV v1 bytes; identical for identical arguments (pure LCG, no global RNG)."""
    if days <= 0 or step_ms <= 0:
        raise ValueError("days and step_ms must be positive")
    state = seed & 0x7FFFFFFF
    cents = start_cents
    last_received = 0
    rows = [",".join(HEADER)]
    count = days * 86_400_000 // step_ms
    per_regime = max(1, 36 * 3_600_000 // step_ms)  # drift regime changes every 36 h
    for i in range(count):
        state = (state * 1103515245 + 12345) % 2**31
        drift = 2 if (i // per_regime) % 2 == 0 else -2
        cents = max(10_000, cents + (state >> 16) % 41 - 20 + drift)
        spread = 15 + (state >> 5) % 21
        t = start_ms + i * step_ms
        received = max(t + (state >> 9) % 250, last_received)
        last_received = received
        rows.append(f"{t},{received},{_price(cents)},{_price(cents + spread)}")
    return ("\n".join(rows) + "\n").encode("ascii")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m grog.replay.synthetic",
        description="Write a deterministic SYNTHETIC BID/ASK CSV v1 file (no market claim).",
    )
    parser.add_argument("--out", required=True, help="output CSV path (must not exist)")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        sys.stderr.write(f"refusing to overwrite existing file {out}\n")
        return 2
    out.write_bytes(generate_csv(days=args.days, seed=args.seed))
    sys.stdout.write(f"wrote {out} (SYNTHETIC, {args.days} days, seed {args.seed})\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
