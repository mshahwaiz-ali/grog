"""Confirmed strict left/right pivots on finalized BID bars (docs/04 Section 6).

* Pivot high at k if ``H[k]`` is strictly greater than the ``left`` previous and
  ``right`` following highs; pivot low symmetric on lows. Equal values are not pivots.
* Confirmed only when bar ``k+right`` is finalized; usable from that bar's
  ``available_at_ms``. Same-bar high and low pivots are separate records.
* "Previous/following" means adjacent **finalized** bars in series order; missing
  buckets are never fabricated. A window spanning a gap or a GAPPED bar is
  flagged ``window_irregular`` (not silently treated as clean).
"""

from __future__ import annotations

from decimal import Decimal

from grog.domain.enums import BarQuality, PivotSide, Timeframe
from grog.domain.models import FinalizedBar, Pivot


class PivotDetector:
    def __init__(
        self, source_id: str, timeframe: Timeframe, left: int, right: int, calculation_version: str
    ) -> None:
        if left <= 0 or right <= 0:
            raise ValueError("left and right must be positive")
        self.source_id = source_id
        self.timeframe = timeframe
        self.left = left
        self.right = right
        self.calculation_version = calculation_version
        self.bars: list[FinalizedBar] = []
        self.pivots: list[Pivot] = []

    def on_bar(self, bar: FinalizedBar) -> list[Pivot]:
        """Append a finalized bar; return pivots newly confirmed by it (HIGH before LOW)."""
        if bar.source_id != self.source_id or bar.timeframe is not self.timeframe:
            raise ValueError("bar does not belong to this pivot detector")
        if self.bars and bar.start_ms <= self.bars[-1].start_ms:
            raise ValueError("bars must arrive in increasing start order")
        self.bars.append(bar)
        k = len(self.bars) - 1 - self.right
        if k < self.left:
            return []
        window = self.bars[k - self.left : k + self.right + 1]
        center = self.bars[k]
        others = window[: self.left] + window[self.left + 1 :]
        irregular = any(b.quality is not BarQuality.COMPLETE for b in window) or any(
            window[i + 1].start_ms != window[i].end_ms for i in range(len(window) - 1)
        )
        found: list[Pivot] = []
        if all(center.high_bid > b.high_bid for b in others):
            found.append(self._make(PivotSide.HIGH, k, center.high_bid, bar, irregular))
        if all(center.low_bid < b.low_bid for b in others):
            found.append(self._make(PivotSide.LOW, k, center.low_bid, bar, irregular))
        self.pivots.extend(found)
        return found

    def _make(
        self, side: PivotSide, k: int, price: Decimal, confirming: FinalizedBar, irregular: bool
    ) -> Pivot:
        center = self.bars[k]
        return Pivot(
            source_id=self.source_id,
            timeframe=self.timeframe,
            side=side,
            bar_id=center.bar_id,
            bar_index=k,
            price=price,
            pivot_bar_start_ms=center.start_ms,
            pivot_bar_end_ms=center.end_ms,
            confirming_bar_id=confirming.bar_id,
            confirmed_at_ms=confirming.end_ms,
            available_at_ms=confirming.available_at_ms,
            window_irregular=irregular,
            calculation_version=self.calculation_version,
        )
