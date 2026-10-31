"""EMA and Wilder ATR recurrences, exactly as docs/04 Sections 4-5 define them.

* EMA: ``alpha = 2/(N+1)``; ``EMA[N-1] = SMA(first N closes)``; then
  ``EMA[t] = alpha*C[t] + (1-alpha)*EMA[t-1]``. Indices ``< N-1`` have no value.
* TR (prior-close convention): ``TR[t] = max(H-L, |H-C[t-1]|, |L-C[t-1]|)`` for
  ``t >= 1``; the first bar has no TR.
* ATR: ``ATR[N] = mean(TR[1..N])`` (first N valid TRs); then
  ``ATR[t] = ((N-1)*ATR[t-1] + TR[t]) / N``.

All arithmetic is Decimal in :data:`CALC_CONTEXT`. Inputs are BID prices of
finalized bars, in series order (missing buckets are skipped, never invented).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from grog.analysis.params import CALC_CONTEXT


def _check_period(period: int) -> None:
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise ValueError("period must be a positive int")


class EmaState:
    """Incremental EMA; ``update`` returns the EMA after this close, or ``None`` before seeding."""

    def __init__(self, period: int) -> None:
        _check_period(period)
        self.period = period
        self.count = 0
        self.value: Decimal | None = None
        self._seed_sum = Decimal(0)
        self._alpha = CALC_CONTEXT.divide(Decimal(2), Decimal(period + 1))
        self._one_minus_alpha = CALC_CONTEXT.subtract(Decimal(1), self._alpha)

    def update(self, close: Decimal) -> Decimal | None:
        c = CALC_CONTEXT
        self.count += 1
        if self.value is None:
            self._seed_sum = c.add(self._seed_sum, close)
            if self.count == self.period:
                self.value = c.divide(self._seed_sum, Decimal(self.period))
            return self.value
        self.value = c.add(
            c.multiply(self._alpha, close), c.multiply(self._one_minus_alpha, self.value)
        )
        return self.value


def true_range(high: Decimal, low: Decimal, prev_close: Decimal) -> Decimal:
    c = CALC_CONTEXT
    return max(
        c.subtract(high, low),
        abs(c.subtract(high, prev_close)),
        abs(c.subtract(low, prev_close)),
    )


class AtrState:
    """Incremental Wilder ATR; ``update`` returns ATR after this bar, or ``None`` before seeding."""

    def __init__(self, period: int) -> None:
        _check_period(period)
        self.period = period
        self.tr_count = 0
        self.value: Decimal | None = None
        self._prev_close: Decimal | None = None
        self._seed_sum = Decimal(0)

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> Decimal | None:
        c = CALC_CONTEXT
        prev, self._prev_close = self._prev_close, close
        if prev is None:
            return None  # first bar: no prior close, no TR
        tr = true_range(high, low, prev)
        self.tr_count += 1
        if self.value is None:
            self._seed_sum = c.add(self._seed_sum, tr)
            if self.tr_count == self.period:
                self.value = c.divide(self._seed_sum, Decimal(self.period))
            return self.value
        n = Decimal(self.period)
        self.value = c.divide(c.add(c.multiply(n - 1, self.value), tr), n)
        return self.value


def ema_series(closes: Sequence[Decimal], period: int) -> list[Decimal | None]:
    state = EmaState(period)
    return [state.update(x) for x in closes]


def atr_series(
    highs: Sequence[Decimal], lows: Sequence[Decimal], closes: Sequence[Decimal], period: int
) -> list[Decimal | None]:
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("high/low/close series must have equal length")
    state = AtrState(period)
    return [state.update(h, lo, c) for h, lo, c in zip(highs, lows, closes, strict=True)]
