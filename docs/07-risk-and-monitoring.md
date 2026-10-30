# Risk, Trade Economics, Stops, Targets and Live Monitoring

**Owner:** All trade economics, actual manual fills, stop/target benchmark rules and held-position monitoring. Updated 2026-10-30. **Status:** Core manual/no-auto execution APPROVED; all percentages, stop/target multipliers, cost and alert rules below remain PROPOSED research hypotheses, not verified profitability.

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
