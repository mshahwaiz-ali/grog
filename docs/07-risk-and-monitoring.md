# Risk, Trade Economics, Stops, Targets and Live Monitoring

**Owner:** All trade economics, actual manual fills, stop/target benchmark rules and held-position monitoring. Updated 2026-10-31. **Status:** Core manual/no-auto execution APPROVED; all percentages, stop/target multipliers, cost and alert rules below remain PROPOSED research hypotheses, not verified profitability.

**Cross-references:** Price calculations → [04](04-analysis-engine.md); S1 structure/triggers → [05](05-strategies.md); READY/expiry/entry band → [06](06-signals-and-scoring.md); testing and full-vs-partial exit comparisons → [08](08-validation.md). Historical drafts → [archive](archive/2026-10-30/README.md).

## 1. Immutable signal vs actual trade

An issued signal is a **proposal**, not evidence that a broker filled an order. Preserve an immutable record of:
- Original first-quote entry E0, stop SL0, proposed target(s), source BID/ASK at issuance, quote timestamp, spread, ATR, broker contract metadata, estimated fees/slippage and rule version.
- Whether and when user manually **entered**, **skipped**, **missed** or recorded an **off-plan fill**.
- Actual fill time, direction, **actual executed price**, quantity/lots, instrument specs, paid fees when known, broker identity (optional) and current broker-side stop/target as reported by user.

Do **not** assume trades from price movements. Broker confirmations remain authoritative for executed fills; if no execution link exists, the user must provide actions manually. A touched TP/SL does **not** mean a close happened.

No broker order placement, modification or cancellation from Grog.

## 2. S1 proposed stop-loss reference (one authoritative definition)

For initial **long** BUY:
- Use `P_bid_final = MIN(completed BID lows of post-H pullback bars INCLUDING the completed M5 trigger bar)`, as defined in [05](05-strategies.md).
- Stop hypothesis: `SL_long_raw = P_bid_final − 0.10 * ATR14_M5_at_signal`. Round **down** to the next valid broker price increment; enforce `SL_long < current BID` and `SL_long < E0_long`.
- Long entry reference `E0_long = ASK` on first causally available post-trigger valid quote.
- Gross long price risk `R_long = E0_long − SL_long > 0`.

For initial **short** SELL:
- The chart's BID pullback definition remains in [05](05-strategies.md), but compute stop from **parallel ASK highs** `P_ask_final = MAX(ASK highs over the same post-L bars through the M5 trigger)`.
- Stop hypothesis: `SL_short_raw = P_ask_final + 0.10 * ATR14_M5_at_signal`. Round **up** to broker tick; enforce `SL_short > current ASK` and `SL_short > E0_short`.
- Short entry reference `E0_short = BID` on first causally subsequent quote.
- Gross short price risk `R_short = SL_short − E0_short > 0`.

**The stop buffer 0.10 ATR is experimental.** These equations describe tested reference levels, **not guaranteed broker stop fill prices**. Broker-specific trigger conventions, tick precision and stop level constraints are still OPEN. Stops may slip through gaps.

## 3. Targets and exit-policy alternatives

**Provisional visual plan for both directions:**
- TP1 at **1R** and TP2 at **2R**, where R is the **original frozen gross price risk**.
- Long targets are prices reached using **closeable BID**, e.g. `TP1_long = E0_long + R`, `TP2_long = E0_long + 2R`.
- Short targets use **closeable ASK**, e.g. `TP1_short = E0_short − R`, `TP2_short = E0_short − 2R`.
- Round target prices only with an **approved broker-specific conservative policy**; this rounding policy is OPEN and must be frozen before implementation.
- Log nearby confirmed M15 structural levels as possible congestion **before entry**. A structurally clipped TP is a separate pre-registered experiment, not a post-hoc improvement.
- Show target/R estimations after spread, commissions and modeled slippage where known. **A gross 2R signal need not yield 2R net.**

**Crucial benchmark definition:** S1 base simulation **does not close half the position at TP1**. TP1 is an informational milestone; the **entire position exits at either TP2 or SL**, using real tick order and cost/slippage assumptions. A separate pre-registered exit policy can test **50% at TP1 / 50% at TP2 or SL**; document precisely whether/when remaining stop moves and how commissions apply. Never mix returns from two exit policies in a single performance summary.

Grog may *show* TP1/TP2 even if only TP2 is simulated as the full exit; the UI should identify the active simulated policy unambiguously.

## 4. Risk sizing and exposure (open broker-dependent policy)

Proposed conservative research example: **0.25–0.5% of equity at risk per trade**, with configurable daily-loss and overlapping-exposure caps. These are not universal safe values and require deliberate operator approval; no real-account positions are sized until contract metadata is trustworthy.

For valid product contract:
- `price_risk = abs(actual_or_planned_entry_price − SL)`.
- `gross_loss_currency = price_risk × contract_value_per_one_price_unit × traded_quantity`.
- `estimated_total_loss = gross_loss_currency + modeled_two_way_commissions + modeled_entry/stop_slippage`.
- Proposed max size = largest broker-valid lot step whose estimated total loss stays **within** approved currency risk cap; reject zero/invalid contract value, price increment, lot constraints, required margin or uncertain execution mechanics.

Risk caps cannot guarantee the worst-case realized loss because stops can gap/slip, spreads change, platforms may disconnect and leverage can amplify losses. Never martingale, add to losers to recover losses, or automatically widen stops.

If current spread/cost makes net reward/risk unacceptable, warn/block only with a tested explicit policy. The exact spread/R threshold, total-cost limit, balance source and max simultaneous open trades remain OPEN in [11](11-decisions.md).

## 5. Why late manual entries matter — numerical illustration

**Not a live quote or recommendation.**
- At READY, BID 4000.00 and ASK 4000.20. Proposed BUY E0=4000.20, SL=3998.00, TP2 BID=4004.60.
- Original risk = `4000.20 − 3998.00 = 2.20`; original gross TP2 reward = `4004.60−4000.20 = 4.40` = **2.0R**.
- Trader enters late at ASK 4001.10 with original SL and TP2 unchanged.
- Actual risk = `4001.10−3998.00=3.10`; actual possible reward = `4004.60−4001.10=3.50`; **3.50/3.10 ≈ 1.13R before fees**.

Grog must preserve E0 and original recommendation, compute the new real entry economics, show **OFF_PLAN / REVALIDATE**, and never secretly enlarge TP to restore a 2R presentation.

## 6. Closeable price, unrealized P/L and R

For confirmed **long** position, mark exit using current **BID**; short uses current **ASK**. Gross unrealized P/L in currency:
- Long: `(BID_now - actual_entry_ask) × contract_value_per_price_unit × quantity`.
- Short: `(actual_entry_bid - ASK_now) × contract_value_per_price_unit × quantity`.
- Subtract *known* paid commissions and estimated outstanding close costs for labeled **net-estimate**; display clearly when estimated or metadata missing.
- Report `R_multiple = net_PnL / initial_planned_risk_currency`, when denominator and fees valid. Preserve original risk snapshot so stop modifications do not retroactively rewrite initial R.
- For multiple partial fills, track lots with quantity-weighted actual price, realized P/L per close, remaining size, current stop/TP and fee attribution. Do not mix original signal return with actual trade return.

If current quote stale: do not display fresh-looking P/L; mark prices stale with timestamp and monitoring degraded.

## 7. Live monitoring: observations vs advice

After `ENTERED` user confirmation:
1. Persist actual position and current quote-side mark, fees, and risk.
2. Monitor every valid tick internally (terminal redraw may be throttled) for distance to TP1/TP2, stop proximity/touch, spread anomaly, and adverse price move.
3. When a new **confirmed** M5/M15/H1 bar arrives, update causal setup observations: M5 continuation weakening, M15 structural opposition, confirmed H1 bias flip. Incomplete bars must be labeled provisional.
4. Check **known-ahead-of-time** major event proximity, session closure, feed health and latency.
5. Present observations such as `TP1 APPROACHING`, `SPREAD WIDENED`, `M15 STRUCTURE BROKEN`, `H1 BIAS CHANGED`, `STOP PRICE TOUCHED`. Do not convert every flicker into a conflicting EXIT recommendation.
6. **Hold / partial / tighten / exit** recommendations require a separately specified, backtested and accepted rule. Until then display factual conditions and original stop/targets, **not ungrounded instruction**.
7. Only explicit operator confirmation moves broker fill state. Terminal may ask the operator to confirm whether a touch resulted in execution.

The program continues market analysis while tracking manually entered trades; new overlap/conflict policy remains OPEN and must prevent duplicate risk being represented as independent profitable signals.

## 8. Position lifecycle, journal and recovery

`ENTERED -> MONITORING -> [PARTIAL, MODIFIED]* -> CLOSED`; `RECONCILIATION_REQUIRED` can interrupt after restart, missed feed, or unknown broker-side actions. Store current state and immutable append-only events.

Every operator action includes `signal_id`, position ID, actual event time (when available), recording time, direction, quantity, fill, stop/TP, costs and modification reason. Invalid or duplicate operator actions must not silently mutate exposure. If partial quantity exceeds current open size or missing fill price prevents accurate realized P/L, reject or request correction.

At startup restore saved positions as **UNVERIFIED/RECONCILIATION_REQUIRED** until user confirms whether positions are open, partially closed, stopped or manually modified. Never assume local program shutdown closed the brokerage trade. Without a live quote connection, monitoring is **UNAVAILABLE**, not safe.

## 9. Testing/approval boundary

[08 — Validation](08-validation.md) owns exact positive/negative fixtures for bid/ask stop/target, same-bar ambiguity, slippage, late entry, partials and restart. Real historical broker-specific ticks, position metadata, latency and fees are necessary to evaluate whether a scalping plan has a positive **net** expectancy.

The strategy/risk plan is exploratory. Grog does not place, modify, close or sync broker orders by itself; no trading profit or safety guarantee is made.

## 10. Broker-matched execution and cost model — 2026-10-31

**Research specification, not a confirmed broker rule.** First read [03 — Market Data](03-market-data.md). Actual tradable symbol specifications/permissions **must** be collected from the chosen broker. Never guess whether 1.00 lot of its Gold product equals a fixed number of ounces, a fixed tick value or a standardized pip. Price *digits* and **tick increment** are different concepts.

### 10.1 Required symbol and account-neutral metadata

| Variable | Meaning | Why it matters |
| --- | --- | --- |
| `symbol`, `source_id`, account environment | Exact broker XAUUSD alias (e.g. suffix), DEMO/LIVE metadata context | Prevent trade calculations based on another provider |
| `price_digits`, `point_size`, `trade_tick_size` | Decimal presentation, displayed point and **minimum valid price increment** | Round SL/TP to executable increments; these values need not be identical |
| `contract_size`, `profit_calc_mode`, `tick_value_profit/loss`, `profit_currency` | Broker's P/L/contract convention | Correct per-lot move value and currency |
| `lot_min`, `lot_max`, `lot_step`, `volume_limit` | Valid position sizing | Avoid fabricated position sizes |
| `trade_mode`, `session_times`, `stop_level`, `freeze_level` | Whether trading is allowed, stop/freeze restrictions | A technically valid price need not be order-valid |
| `commission_schedule`, `overnight_costs`, `conversion_source` | Fee/currency rules, with as-of timestamps | Net P/L and net reward/risk |
| `stop/target_trigger_price_side`, `execution_policy` | Broker-specific trigger & market/limit fill rules | Distinguish quote touch from executed order |

Official MT5 symbol property API names such as `SYMBOL_TRADE_TICK_SIZE`, `SYMBOL_TRADE_CONTRACT_SIZE`, `SYMBOL_TRADE_TICK_VALUE_PROFIT/LOSS`, `SYMBOL_VOLUME_MIN/MAX/STEP`, `SYMBOL_TRADE_STOPS_LEVEL` and `SYMBOL_TRADE_FREEZE_LEVEL` can be inspected read-only, **if MT5 is eventually selected**: https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants

**Metadata versioning:** Snapshot the contract metadata used for *each issued signal*. If symbol specs change during live operation, invalidate pending signal economics requiring recalculation rather than silently retaining stale stop/position-size results.

### 10.2 Price-side P/L, with no spread double-count

The fundamental execution convention for a typical OTC Gold CFD (verify with broker):
- Long hypothetical market entry = ASK at entry; long mark/exit = BID at exit.
- Short hypothetical market entry = BID; short mark/exit = ASK.
- `spread = ASK − BID` (in XAUUSD price units); compute `spread_in_R = spread / initial_price_risk` when denominator positive.

If the historical model **already uses ASK for a BUY and BID for its sale/exit** (and vice versa for SHORT), the spread is **already embedded in the entry-to-exit price difference**. **Do not subtract it again** as an additional fee. Commission, financing, extra slippage and conversion charges are distinct costs.

For a linear one-price-unit value `V` in profit currency per **1.00 lot**, position `q` lots and observed fill prices:

```text
gross_long_PnL   = (exit_bid_fill − entry_ask_fill) × V × q
gross_short_PnL  = (entry_bid_fill − exit_ask_fill) × V × q
net_PnL          = gross_PnL − entry_commission − exit_commission − other_actual_costs
net_reward_to_TP = modeled_net_winning_currency / modeled_net_stop_loss_currency
```

**Caution:** `V` is **not** universally equal to a fixed ounce value. Some instrument calculation modes, tick-value currencies and conversion rates differ. If linear valuation is not validated from broker specs, use a verified symbol-specific **read-only** calculation or mark monetary P/L UNAVAILABLE. No trade-order API is authorized. If user's reporting currency differs from the broker profit currency, convert using a traceable contemporaneous quote/fee or display in profit currency only.

**Gross R** on original entry and stop:
- `R_price_long = original_ask_entry − SL_bid`.
- `R_price_short = SL_ask − original_bid_entry`.
- Gross TP2 target based on 2R is **not** guaranteed to deliver 2R net after fees/slippage. Stop fills may be worse than the requested stop.

### 10.3 Execution assumptions must be explicit

For every backtest or live **advisory**:
1. **Order type assumed:** market on the first eligible actual quote, versus explicit separate limit-order scenario. A limit touch is **not proof of a fill**; queue/partial fill uncertainty must be declared.
2. **Operator delay:** test at multiple recorded or measured delays from first READY to a possible actual market fill, *taking the quote at that later time*. Do not backfill a favorable earlier price.
3. **Spread path:** do not use a constant midpoint spread in a "real ticks" test; record contemporaneous BID and ASK. Stress wider spreads, bad ticks, reconnection and thin periods.
4. **Commission and stop slippage:** include per-lot/per-side fee schedule, potentially variable commission, currency conversion and stop slippage; distinguish estimated from observed. A stop is **not** a guaranteed worst-case exit.
5. **TP/SL event order:** use actual ordered ticks and broker trigger conventions. An OHLC minute touching both is indeterminate. A touched level alone is not an actual manual/broker fill.
6. **Signal validity:** at time of **actual** user-reported fill, compare against original band, TTL, structural invalidation and current executable quote; show OFF_PLAN when applicable and recalculate actual net R/R. The historical original record never changes.
7. **Clock and session status:** if terminal/feed offline, warn user monitoring is not live. Do not imply Grog can close or protect the broker position remotely.

Avoid any user-facing "profit guarantee", "safe stop" or unsupported probability.

### 10.4 Proposed cost-risk diagnostics (not additional hard gates yet)

- `spread_fraction_of_R = spread / gross_initial_risk_price`; log current and historical percentile by session.
- `fee_fraction_of_R = commissions_and_other_known_fees / original_risk_currency` if broker valuation/currency known.
- `net_target_reward_R` and `modeled_stop_loss_R`, with spread included through BID/ASK prices **once**.
- `manual_chase_distance_R = max(0, adverse_move_from_issued_executable_entry) / original_risk_price`.
- `latency_ms = user_fill_time − first_READY_time` if actual timestamps provided; unknown if user confirms late without an accurate fill time.
- `stop_distance_vs_ATR = gross_initial_risk_price / ATR_M5` when valid.

**Do not set universal cutoffs** such as spread < a given dollar value, minimum 2R net, maximum two-second latency or one Gold lot equals a specific contract value. Any executable gate or sizing policy needs empirical broker-specific calibration and explicit user approval, with its impact on rejected winners/losses measured in [08](08-validation.md).

## 11. Execution-source evaluation before real-money use

A hypothetical 2R gross target must be backtested with:
- Broker-matched XAUUSD spread samples by UTC session/rollover and around major release times.
- Correct ASK/BID side of entry and stop/target trigger.
- Commission/minimum fees and any conversion to account currency.
- Delayed manual fills, missed/partial fills, rejected price bands, stop gaps and late entries.
- Adverse price movement during terminal downtime and delayed post-disconnect first quote.
- Risk-in-currency for **the chosen broker contract**, including min lot rounding and inability to size below minimum.

**Required output:** explicit net R and modeled realized currency figures *only when sufficient inputs exist*; otherwise keep the numeric account P/L unavailable. Report sensitivity to slippage/spread rather than falsely precise estimates.

**Approval boundaries:** provider/contract/fee model OPEN in [11 — Decisions](11-decisions.md). The calculation framework may be researched offline but no sizing/signals using invented broker values, no wallet or account-management system, and no broker order placement.
