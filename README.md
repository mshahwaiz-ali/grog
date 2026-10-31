# Grog

**XAUUSD Gold scalping research and manual trading decision-support software.**

**State:** offline release **R0 (M00–M08) implemented and acceptance-audited** ([docs/14](docs/14-r0-acceptance-audit.md)): strict BID/ASK CSV import, causal bars and feed health, no-lookahead analysis, the research-only S1 v0.2 detector, SIMULATED signal eligibility, deterministic replay with evidence reports, and the Textual workstation with a local manual journal (entry, skip, partial/close, stop/target modify, unlinked external fills, restart reconciliation). Grog places **no orders**, has **no live data feed** yet (M09 MT5 reference feed is planned, not built), and **no strategy edge, live-data readiness, broker-verified fill or profitability is claimed**. OPEN thresholds (quote age, first-quote delay, spread, costs, contract) default to unset, so the default config issues no READY.  
**Repository:** private; default branch `main`.  
**Last update:** 2026-10-31.

## Product mission

Help a person take **better Gold trades**, not more platform features. Grog will run locally (initially a terminal session), monitor XAUUSD market conditions, separate developing setups from confirmed actionable proposals, present BUY/SELL/WAIT/NO TRADE with explicit entry, SL/TP and conditions, and observe trades after the user manually confirms actual broker execution.

Grog is **rule-based software**, not GPT/Claude/LLM, an AI agent, an auto-trader, a broker wallet or copy-trading service. Grok is a **separate development assistant** that will implement only approved, testable specifications in small modules.

## How trade decisions are proposed to work

1. Validate live BID/ASK source, quotes, closed-bar timing and broker metadata.
2. Calculate H1 trend, M15 market structure and M5 setup/volatility using complementary measurements.
3. Run strategy-specific objective rules (S1 trend pullback first; S2 only if separately researched).
4. Show **DEVELOPING** opportunities until the trigger and eligibility pass.
5. On valid post-trigger executable quote, show **READY** proposal with time-limited entry band, stop/targets, cost/risk evidence and reason codes; never promise a fill.
6. Trader manually enters/skips through broker, then reports actual entry/quantity to Grog.
7. Monitor bid/ask, thesis changes, stop/TP proximity and position status; journal actions/results, with restart reconciliation and no automatic broker execution.
8. Replay realistic historical tick data and validate the smallest strategy/indicator combination that shows robust **net** performance, rather than chasing win-rate claims.

Proposed strategies/indicator periods have **not** been tested; an attractive quality score is **not** a win probability. Phase 18 specifies evidence-first signals and tests. **MT5 is now the preferred reference-price adapter**, regardless of the eventual execution broker. First build broker-neutral offline BID/ASK parsing, causal MTF analysis and replay; then connect an MT5 demo data source when separately approved. The actual broker/server and live feed are not selected or installed. Numerical ranking remains experimental.

## Run it locally (offline demo)

Requires Python 3.11 and [uv](https://docs.astral.sh/uv/). Everything below is offline and uses deterministic **SYNTHETIC** data (no market claim).

```bash
uv sync --locked
uv run grog --help && uv run grog doctor
mkdir -p /tmp/grog-demo
uv run python -m grog.replay.synthetic --out /tmp/grog-demo/syn.csv          # 20 synthetic days, seed 7
uv run grog import-ticks --file /tmp/grog-demo/syn.csv --source-id syn --origin SYNTHETIC --state-dir /tmp/grog-demo
# research replay + evidence report (SIMULATED, gross R only)
uv run grog replay --source-id syn --config config/synthetic-demo.fixture-only.toml --state-dir /tmp/grog-demo
uv run grog report --run-id <RUN-id printed above> --state-dir /tmp/grog-demo
# interactive workstation (best at 120x34; works down to 70x18)
uv run grog ui --mode replay --source-id syn --config config/synthetic-demo.fixture-only.toml --state-dir /tmp/grog-demo
```

`config/synthetic-demo.fixture-only.toml` declares **test/demo-only** freshness thresholds so the synthetic replay can reach READY; they are not broker-derived values. With `config/research.example.toml` (or no config) feed health stays UNKNOWN and no READY is issued — by design.

Workstation keys: `1`–`5` views (Live, Signals, Positions, Journal, Diagnostics), `Space` play/pause, `.` step, `+`/`-` pace, `Enter` details (on Positions: confirm-open reconciliation), `e` record entry, `s` skip, `p` partial, `x` close, `m` modify SL/TP, `n` unlinked external fill, `?` help, `q` quit; the Journal view has a filter field. Every modal opens with **Cancel focused**; typing in a field never triggers a hotkey.

Local checks (no GitHub Actions): `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`. Screenshot evidence: `uv run python scripts/r0_screenshots.py --out /path/outside/repo` (needs headless Chrome for PNG; SVG otherwise).

## Working on Grog

Agent/developer entrypoint: [AGENTS.md](AGENTS.md), then [docs/00-index.md](docs/00-index.md), [docs/11-decisions.md](docs/11-decisions.md), [docs/09-architecture.md](docs/09-architecture.md) and [docs/10-roadmap.md](docs/10-roadmap.md). Next milestones (M09 read-only MT5 reference feed, M10 historical-data and forward-paper evaluation) need explicit external permissions listed in [docs/10](docs/10-roadmap.md); nothing beyond R0 is authorized by default.

## Active documentation — single source of truth

Start with [docs/00-index.md](docs/00-index.md) for the full canonical topic map.

- [Product goals](docs/01-product-vision.md)
- [Terminal workflow](docs/02-workflows-and-ux.md)
- [Market data and closed-bar contract](docs/03-market-data.md)
- [Indicators, MTF analysis and market structure](docs/04-analysis-engine.md)
- [S1 strategy and future strategy candidates](docs/05-strategies.md)
- [Signal states, entry-band and scoring](docs/06-signals-and-scoring.md)
- [SL/TP, manual fills, risk and position monitoring](docs/07-risk-and-monitoring.md)
- [Validation, indicator combinations and adversarial tests](docs/08-validation.md)
- [Proposed architecture](docs/09-architecture.md)
- [Build roadmap](docs/10-roadmap.md)
- [Approved decisions, open blockers and documentation standards](docs/11-decisions.md)
- [Research references](docs/12-references.md)
- [Competitor lessons (research only)](docs/13-competitor-research.md)
- [R0 acceptance audit](docs/14-r0-acceptance-audit.md)

**Historical only:** [Archived S1 draft snapshots](docs/archive/2026-10-30/README.md). These are **not current instructions for Grok**. Exact original Git contents also remain in repository commit history.

## Project safeguards

- Any proposed "upgrade" must demonstrably improve Gold trade selection, realistic execution, risk/TP decisions, monitoring or testing accuracy. Reject unrelated product features.
- **Update existing canonical documents** instead of creating more numbered versions of the same idea.
- Do not guess broker/price data, fees, risk thresholds, scoring formulas or claimed performance.
- Live quotes will eventually come via the preferred read-only **MT5 reference adapter** (a demo broker server provides quotes; MT5 alone is not a universal source). **No execution broker choice is required to start offline engineering**. This does **not** imply an AI API or order-execution API.
- Test realistic bid/ask spreads, latency and out-of-sample/forward outcomes before promoting a strategy.
- Never commit broker secrets or private customer/account data. This is not financial advice and there are no guaranteed trading results.

