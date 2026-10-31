"""BID/ASK price-side S1 risk plans and touch/economics math (docs/07 Sections 1-6, docs/06 §4-5).

Research defaults only (docs/06 §4-5, docs/07 §2-3): 0.10 ATR stop buffer, TP1=1R,
TP2=2R, 0.20 ATR first-quote no-chase, entry band [-0.10, +0.20] ATR (long ASK) /
[-0.20, +0.10] ATR (short BID), 0.10 ATR confirmation retention. Prices are rounded
only with an explicitly declared synthetic ``price_step`` (SIMULATED); there is no
lot sizing, no account P/L and no broker order here.

Conventions: long enters at ASK and exits / stops on BID; short enters at BID and
exits / stops on ASK. Spread is therefore already inside the entry and exit prices
and is never subtracted a second time (MD-16).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from grog.analysis.params import CALC_CONTEXT
from grog.domain.enums import ExitOutcome, ReasonCode, Side
from grog.domain.models import FinalizedBar, NormalizedQuote

R = ReasonCode
EXIT_POLICY_FULL_TP2_OR_SL = "FULL_AT_TP2_OR_SL"


@dataclass(frozen=True, slots=True)
class RiskParams:
    """docs/06 §4-5 and docs/07 §2-3 proposed research values (not validated)."""

    stop_buffer_atr: Decimal = Decimal("0.10")
    tp1_r: Decimal = Decimal("1")
    tp2_r: Decimal = Decimal("2")
    no_chase_atr: Decimal = Decimal("0.20")
    band_adverse_atr: Decimal = Decimal("0.10")  # long below E0 / short above E0
    band_chase_atr: Decimal = Decimal("0.20")  # long above E0 / short below E0
    retention_atr: Decimal = Decimal("0.10")
    exit_policy: str = EXIT_POLICY_FULL_TP2_OR_SL


RESEARCH_RISK_V0_2 = RiskParams()


def _mul(a: Decimal, b: Decimal) -> Decimal:
    return CALC_CONTEXT.multiply(a, b)


def round_to_step(price: Decimal, step: Decimal, *, up: bool) -> Decimal:
    """Directional rounding to a declared price increment (ST-10)."""
    if step <= 0:
        raise ValueError("price step must be positive")
    units = CALC_CONTEXT.divide(price, step).to_integral_value(
        rounding=ROUND_CEILING if up else ROUND_FLOOR
    )
    return _mul(units, step)


@dataclass(frozen=True, slots=True)
class TradePlan:
    """Original frozen price plan. Never mutated (docs/09 §3.5 immutability)."""

    side: Side
    e0: Decimal
    sl0: Decimal
    tp1: Decimal
    tp2: Decimal
    risk: Decimal  # original gross price risk R
    atr0: Decimal
    stop_reference: Decimal  # long P_bid_final / short P_ask_final
    entry_low: Decimal
    entry_high: Decimal
    retention_threshold: Decimal
    price_step: Decimal
    exit_policy: str


@dataclass(frozen=True, slots=True)
class PlanCheck:
    plan: TradePlan | None
    reasons: tuple[ReasonCode, ...]


def no_chase_ok(
    side: Side, e0: Decimal, trigger_close_bid: Decimal, atr0: Decimal, params: RiskParams
) -> bool:
    """docs/06 §4: long E0 <= close + 0.20 ATR; short E0 >= close - 0.20 ATR."""
    limit = _mul(params.no_chase_atr, atr0)
    return e0 <= trigger_close_bid + limit if side is Side.BUY else e0 >= trigger_close_bid - limit


def build_plan(
    side: Side,
    quote: NormalizedQuote,
    stop_reference: Decimal,
    two_bar_threshold: Decimal,
    atr0: Decimal,
    price_step: Decimal,
    params: RiskParams = RESEARCH_RISK_V0_2,
) -> PlanCheck:
    """Original E0/SL0/TP1/TP2 from the first executable quote (docs/07 §2-3)."""
    if atr0 <= 0:
        return PlanCheck(None, (R.M5_ATR_ZERO,))
    buffer = _mul(params.stop_buffer_atr, atr0)
    if side is Side.BUY:
        e0 = quote.ask
        sl = round_to_step(stop_reference - buffer, price_step, up=False)
        valid = sl < quote.bid and sl < e0
        risk = e0 - sl
        tp1 = round_to_step(e0 + _mul(params.tp1_r, risk), price_step, up=True)
        tp2 = round_to_step(e0 + _mul(params.tp2_r, risk), price_step, up=True)
        low, high = e0 - _mul(params.band_adverse_atr, atr0), e0 + _mul(params.band_chase_atr, atr0)
        retention = two_bar_threshold - _mul(params.retention_atr, atr0)
    else:
        e0 = quote.bid
        sl = round_to_step(stop_reference + buffer, price_step, up=True)
        valid = sl > quote.ask and sl > e0
        risk = sl - e0
        tp1 = round_to_step(e0 - _mul(params.tp1_r, risk), price_step, up=False)
        tp2 = round_to_step(e0 - _mul(params.tp2_r, risk), price_step, up=False)
        low, high = e0 - _mul(params.band_chase_atr, atr0), e0 + _mul(params.band_adverse_atr, atr0)
        retention = two_bar_threshold + _mul(params.retention_atr, atr0)
    if not valid or risk <= 0:
        return PlanCheck(None, (R.PRE_ENTRY_STOP_TOUCH,))
    return PlanCheck(
        TradePlan(
            side,
            e0,
            sl,
            tp1,
            tp2,
            risk,
            atr0,
            stop_reference,
            low,
            high,
            retention,
            price_step,
            params.exit_policy,
        ),
        (),
    )


# ------------------------------------------------------------------ price-side touches


def execution_price(side: Side, quote: NormalizedQuote) -> Decimal:
    """Entry side: long buys at ASK, short sells at BID."""
    return quote.ask if side is Side.BUY else quote.bid


def stop_touched(side: Side, quote: NormalizedQuote, stop: Decimal) -> bool:
    """Long stop on BID <= SL; short stop on ASK >= SL. Never the midpoint (MD-17)."""
    return quote.bid <= stop if side is Side.BUY else quote.ask >= stop


def target_touched(side: Side, quote: NormalizedQuote, target: Decimal) -> bool:
    """Long closes on BID >= TP; short closes on ASK <= TP."""
    return quote.bid >= target if side is Side.BUY else quote.ask <= target


def in_entry_band(plan: TradePlan, quote: NormalizedQuote) -> bool:
    price = execution_price(plan.side, quote)
    return plan.entry_low <= price <= plan.entry_high


def confirmation_retained(plan: TradePlan, quote: NormalizedQuote) -> bool:
    """docs/06 §5: long BID >= threshold - 0.10 ATR; short BID <= threshold + 0.10 ATR."""
    if plan.side is Side.BUY:
        return quote.bid >= plan.retention_threshold
    return quote.bid <= plan.retention_threshold


# ------------------------------------------------------------------ exits (full TP2 or SL)


@dataclass(frozen=True, slots=True)
class ExitEvaluation:
    outcome: ExitOutcome
    exit_price: Decimal | None
    exit_time_ms: int | None
    tp1_touched: bool  # informational milestone only; never a partial win
    gross_r: Decimal | None  # in units of the original R, before costs


def _gross_r(plan: TradePlan, exit_price: Decimal) -> Decimal:
    move = exit_price - plan.e0 if plan.side is Side.BUY else plan.e0 - exit_price
    return CALC_CONTEXT.divide(move, plan.risk)


def evaluate_exit_ticks(plan: TradePlan, quotes: Iterable[NormalizedQuote]) -> ExitEvaluation:
    """Ordered ticks after entry: the whole position exits at TP2 or SL, whichever first.

    The target fills at TP2 (never better). A stop fills at SL, or at the actual worse
    closeable price when a tick gaps through it (docs/07 §2: stops may slip)."""
    tp1 = False
    for q in quotes:
        if stop_touched(plan.side, q, plan.sl0):
            price = min(plan.sl0, q.bid) if plan.side is Side.BUY else max(plan.sl0, q.ask)
            return ExitEvaluation(
                ExitOutcome.STOP, price, q.provider_time_ms, tp1, _gross_r(plan, price)
            )
        if target_touched(plan.side, q, plan.tp2):
            return ExitEvaluation(
                ExitOutcome.TARGET, plan.tp2, q.provider_time_ms, True, _gross_r(plan, plan.tp2)
            )
        tp1 = tp1 or target_touched(plan.side, q, plan.tp1)
    return ExitEvaluation(ExitOutcome.OPEN, None, None, tp1, None)


def evaluate_exit_bar(plan: TradePlan, bar: FinalizedBar) -> ExitOutcome:
    """Unsequenced OHLC: both SL and TP2 inside one bar is INDETERMINATE (S1-16, MD-18)."""
    if plan.side is Side.BUY:
        stop, target = bar.low_bid <= plan.sl0, bar.high_bid >= plan.tp2
    else:
        stop, target = bar.high_ask >= plan.sl0, bar.low_ask <= plan.tp2
    if stop and target:
        return ExitOutcome.INDETERMINATE
    if stop:
        return ExitOutcome.STOP
    if target:
        return ExitOutcome.TARGET
    return ExitOutcome.OPEN


# ------------------------------------------------------------------ actual fills and costs


@dataclass(frozen=True, slots=True)
class ActualEconomics:
    """Recomputed for an operator-reported fill; the original plan is untouched (ADV-05)."""

    fill_price: Decimal
    actual_risk: Decimal
    actual_reward_tp2: Decimal
    actual_r_multiple_tp2: Decimal | None
    off_plan: bool
    reasons: tuple[ReasonCode, ...]


def actual_fill_economics(plan: TradePlan, fill_price: Decimal) -> ActualEconomics:
    if plan.side is Side.BUY:
        risk, reward = fill_price - plan.sl0, plan.tp2 - fill_price
    else:
        risk, reward = plan.sl0 - fill_price, fill_price - plan.tp2
    reasons: list[ReasonCode] = []
    outside = not (plan.entry_low <= fill_price <= plan.entry_high)
    if outside:
        reasons.append(R.OUTSIDE_ENTRY_BAND)
    if risk <= 0:
        reasons.append(R.PRE_ENTRY_STOP_TOUCH)
    multiple = CALC_CONTEXT.divide(reward, risk) if risk > 0 else None
    return ActualEconomics(fill_price, risk, reward, multiple, outside or risk <= 0, tuple(reasons))


@dataclass(frozen=True, slots=True)
class CostModel:
    """Declared per-trade costs in price units (never assumed). Spread is NOT a cost here:
    it is already inside ASK entry / BID exit prices."""

    cost_model_id: str
    round_trip_commission: Decimal
    slippage: Decimal = Decimal(0)


def net_price_move(
    side: Side, entry_price: Decimal, exit_price: Decimal, cost: CostModel | None
) -> tuple[Decimal, Decimal | None]:
    """(gross, net) price result; net is UNKNOWN (None) without a declared cost model."""
    gross = exit_price - entry_price if side is Side.BUY else entry_price - exit_price
    if cost is None:
        return gross, None
    return gross, gross - cost.round_trip_commission - cost.slippage


@dataclass(frozen=True, slots=True)
class ContractSpec:
    contract_value_per_price_unit: Decimal
    profit_currency: str


@dataclass(frozen=True, slots=True)
class MoneyAmount:
    native_amount: Decimal | None
    native_currency: str | None
    reporting_amount: Decimal | None
    reporting_currency: str
    reasons: tuple[ReasonCode, ...]


def price_to_money(
    price_amount: Decimal,
    quantity: Decimal,
    contract: ContractSpec | None,
    reporting_currency: str,
    fx_native_to_reporting: Decimal | None = None,
) -> MoneyAmount:
    """Currency value of a price result for a given quantity. UNKNOWN without a contract
    (ST-09); no guessed exchange rate (MD-15). Not a sizing function."""
    if contract is None or contract.contract_value_per_price_unit <= 0:
        return MoneyAmount(None, None, None, reporting_currency, (R.CONTRACT_UNDEFINED,))
    native = _mul(_mul(price_amount, contract.contract_value_per_price_unit), quantity)
    if contract.profit_currency == reporting_currency:
        return MoneyAmount(native, contract.profit_currency, native, reporting_currency, ())
    if fx_native_to_reporting is None:
        return MoneyAmount(
            native, contract.profit_currency, None, reporting_currency, (R.FX_RATE_UNAVAILABLE,)
        )
    return MoneyAmount(
        native,
        contract.profit_currency,
        _mul(native, fx_native_to_reporting),
        reporting_currency,
        (),
    )
