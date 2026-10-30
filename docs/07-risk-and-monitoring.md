# Risk management and active position monitoring
## Proposed safeguards
- Use percentage of equity risk as a configurable **research default** (e.g. 0.25%-0.5% per trade; not a universal safe level). Per-day loss cap and exposure cap also configurable and require user approval.
- Position sizing = allowed currency risk / (entry-to-stop movement * instrument value per price unit + estimated fees/slippage); normalize to broker lot step and validate worst-case loss. Reject unknown contract specs.
- No martingale, grid recovery, recovery leverage or automatic order sending. Account for trade correlations and overlapping opposite signals.
- Never recommend moving a protective stop **further away** merely to avoid a losing trade; proposed stop adjustments require explicit risk rationale.
## Fill-aware monitoring
On manual entry capture ID, side, actual fill timestamp/price, size, broker (optional), current SL/TP, realized fees when known. Calculate P/L using closeable bid for long and ask for short, contract details and fees. Show R multiples and drawdown from entry.
## Monitoring transitions
Entered → monitored → partially reduced / adjusted → closed. Position persists across restarts; status needs manual reconciliation after offline periods. Stop/TP touches do not mean a broker fill occurred without confirmation.
## Advisory events
Target approached/touched, stop approached/touched, thesis invalidation, volatility/spread spike, time-in-trade expiry, event-risk proximity, feed outage. Separate **observation** from **recommended action** and record both. No machine-originated broker trade instructions.
## Monitoring cadence
Compute tick-level price observations, but throttle terminal rendering and avoid fluctuating recommendations on each tick. Strategy state only changes when its declared logic changes.
## Failure protections
Missing feed: warn, cease new recommendations, do not imply active position is safe. Missing position details: show incomplete P/L. Unexpected manual broker actions: reconcile explicitly.
## Trading outcomes
Record true realized P/L separately from simulated signal outcome; include partials, commission, slippage and cost assumptions.