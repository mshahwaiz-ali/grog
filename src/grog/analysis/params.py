"""Versioned research parameter set for analysis (docs/04 Sections 4-8, docs/05 Section 4).

``S1_RESEARCH_V0_2`` freezes the **proposed** values for deterministic offline
experiments only. They are EXPERIMENTAL, not validated or profitable live settings
(docs/04 Section 11, docs/11 Section 12). I0-I8 variants are not defined here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_EVEN, Context

from grog.domain.ids import canonical_json, sha256_hex

CALC_CONTEXT = Context(prec=34, rounding=ROUND_HALF_EVEN)
"""Decimal arithmetic for indicator recurrences: 34 significant digits (decimal128), half-even.
Values are never rounded to a price tick here; rounding happens only at executable prices."""


@dataclass(frozen=True, slots=True)
class AnalysisParams:
    profile: str
    calculation_version: str
    h1_ema_fast: int
    h1_ema_slow: int
    h1_slope_lookback_bars: int
    h1_warmup_bars: int
    h1_atr_period: int
    m15_ema: int
    m15_warmup_bars: int
    m15_pivot_window_bars: int
    m5_atr_period: int
    pivot_left: int
    pivot_right: int

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if isinstance(value, int) and value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.h1_ema_fast >= self.h1_ema_slow:
            raise ValueError("h1_ema_fast must be shorter than h1_ema_slow")

    @property
    def parameter_set_hash(self) -> str:
        return sha256_hex(canonical_json(asdict(self)).encode())


S1_RESEARCH_V0_2 = AnalysisParams(
    profile="S1_RESEARCH_V0_2",
    calculation_version="S1_RESEARCH_V0_2/analysis-1",
    h1_ema_fast=20,  # docs/04 §4 baseline EMA20/EMA50
    h1_ema_slow=50,
    h1_slope_lookback_bars=3,  # docs/04 §7: EMA20[t] > EMA20[t-3]
    h1_warmup_bars=250,  # docs/04 §4: >=250 finalized H1 bars for EMA50 baseline
    h1_atr_period=14,  # descriptive strength features only (docs/04 §5, §7)
    m15_ema=20,  # docs/04 §8
    m15_warmup_bars=50,  # docs/04 §4: >=50 M15 bars for level/context work
    m15_pivot_window_bars=48,  # docs/04 §8: previous 48 completed M15 bars
    m5_atr_period=14,  # docs/04 §5 / docs/05 §4: ATR14 M5 scale
    pivot_left=2,  # docs/04 §6 strict 2/2
    pivot_right=2,
)
