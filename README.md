# Grog

**XAUUSD Gold scalping research and manual trading decision-support software.**

**State:** offline release **R0 (M00–M08) implemented and acceptance-audited** ([docs/14](docs/14-r0-acceptance-audit.md)): strict BID/ASK CSV import, causal bars and feed health, no-lookahead analysis, the research-only S1 v0.2 detector, SIMULATED signal eligibility, deterministic replay with evidence reports, and the Textual workstation with a local manual journal (entry, skip, partial/close, stop/target modify, unlinked external fills, restart reconciliation). Grog places **no orders**, has **no live data feed** yet (the M09-A/H read-only MT5 reference adapter is implemented offline but has never connected to MT5 or a broker; M09-B demo connection awaits explicit owner approval and M10 market validation has not started), and **no strategy edge, live-data readiness, broker-verified fill or profitability is claimed**. OPEN thresholds (quote age, first-quote delay, spread, costs, contract) default to unset, so the default config issues no READY.\
**Repository:** private; default branch `main`.  
**Last update:** 2026-11-07.

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

## Desktop GUI — D00–D05 implemented

**Current approved next work (2026-11-07):** [Complete Desktop UI/UX V2](docs/desktop-visual-redesign.md) — owner approved matched charcoal **Dark**, warm-white **Light**, OS-following **System** Settings plus PKT/UTC display-only preferences. Grok owns the U0–U5 implementation handoff in [docs/10 §13](docs/10-roadmap.md). This approval does not change engine, journal, MT5 access or the `gold` alias. Design docs are committed; GUI V2 is **not** implemented yet.

A **native Qt Widgets desktop frontend** is approved; D01–D04 (Overview, Signals, Positions/Journal with local manual records, Diagnostics) are implemented and natively QA'd, D05 (one-command launcher, source chooser, Textual parity) passed native QA on 2026-11-07 (full Tab cycle automated only); the `gold` alias cutover is **not** done or authorized.
The Textual TUI (`grog ui`) is unchanged and stays the fallback. This repository does not modify the
`gold` alias (what it maps to on a given machine is not inspected or asserted here). No MT5 or broker
connection exists in the desktop.

The older preview script still opens the full five-page desktop window on the synthetic
demo state. Run it from a regular GNOME Terminal (Qt initialization may fail inside an
inherited editor environment):

```bash
bash scripts/gold-desktop-preview.sh
```

It opens the synthetic `syn` source at `/tmp/grog-demo` with the fixture config. Manual
records saved there go to that temporary demo journal (`/tmp` is not durable storage); there
are no MT5 or broker operations. Prefer the D05 launcher below for your own source.

**D05 one-command desktop (separate launcher; the `gold` alias still opens the TUI):**

```bash
bash scripts/gold-desktop.sh            # saved source, else the source chooser
bash scripts/gold-desktop.sh --choose   # always show the chooser
bash scripts/gold-desktop.sh --source-id ID --state-dir DIR [--config FILE] [--read-only]
```

The chooser inspects a local state directory read-only, lists its imported sources and shows the
existing `grog import-ticks` command; it never imports, downloads, creates or copies data. Open with
"Remember" saves only `$XDG_CONFIG_HOME/grog/desktop-source.toml` (mode 0600, absolute paths). In the
chooser Return/Enter press only the focused button (Quit has focus first); Esc quits. Textual fallback,
from any directory: `uv run --project /path/to/grog grog ui --mode replay --source-id ID --state-dir DIR`
(inside the repository plain `uv run grog ui ...` works).

Install once (needs [uv](https://docs.astral.sh/uv/); the `desktop` extra is the locked optional
`PySide6-Essentials`), then optionally put a personal command on your PATH. The script works from any
directory and through a symlink; relative `--state-dir`/`--config` paths are relative to where you run
it. This is **not** the `gold` alias, which stays on the TUI until explicit owner sign-off:

```bash
uv sync --locked --extra desktop
ln -s "$PWD/scripts/gold-desktop.sh" ~/.local/bin/gold-desktop   # optional, personal
```

Without uv the script prints install guidance and exits 3; without Qt, or for a missing/unknown source
or invalid config, it exits non-zero with a message and no window, nothing written.

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

### One-word Ubuntu/Bash shortcut

After importing the offline demo source, a shell alias named `gold` can launch the exact
`grog ui --mode replay` command above. Put the alias in `~/.bashrc` to retain it after
closing the terminal. Reserve the installed `grog` command for other CLI operations,
such as `grog doctor`. The sample state in `/tmp/grog-demo` is **temporary** and must
not be treated as durable journal storage; do not silently migrate or overwrite it.

## M09-A — read-only MT5 reference feed (offline parts only)

The broker-neutral adapter for a future read-only MT5 demo/reference feed exists and is tested on recorded-format **FIXTURE** files only ([docs/09 §5.1](docs/09-architecture.md)). `mql5/GrogReferenceExporter.mq5` is authored but **has never been compiled or run in MT5**. No terminal, Wine, broker account, credentials or network connection has been used.

```bash
uv run grog reference-status                       # NOT_CONFIGURED without a [reference] config
uv run grog reference-status --config my.toml      # read-only status of exporter files (never writes)
```

## Working on Grog

Agent/developer entrypoint: [AGENTS.md](AGENTS.md), then [docs/00-index.md](docs/00-index.md), [docs/11-decisions.md](docs/11-decisions.md), [docs/09-architecture.md](docs/09-architecture.md) and [docs/10-roadmap.md](docs/10-roadmap.md). Next milestones (M09 read-only MT5 reference feed, M10 historical-data and forward-paper evaluation) need explicit external permissions listed in [docs/10](docs/10-roadmap.md); nothing beyond R0 is authorized by default.

## Active documentation — single source of truth

Start with [docs/00-index.md](docs/00-index.md) for the full canonical topic map.

- [Product goals](docs/01-product-vision.md)
- [Terminal and native desktop functional UX](docs/02-workflows-and-ux.md)
- [Owner-approved Desktop UI/UX V2 visual system and Grok handoff](docs/desktop-visual-redesign.md)
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


### Complete desktop documentation handoff (2026-11-07)

The implementation specification for **all five native desktop screens** was consolidated into the existing canonical documents (the screens have since been built in D01–D04): [full UX/actions](docs/02-workflows-and-ux.md#16-complete-native-workstation-interaction-specification--d00d05-handoff-2026-11-07), [data flow and thread ownership](docs/09-architecture.md#13-desktop-implementation-ports-concurrency-and-state-ownership--d00d05-handoff-2026-11-07), [functional and visual verification](docs/08-validation.md#20-complete-native-desktop-acceptance-matrix-and-verification-protocol-2026-11-07), [D00–D05 staged implementation](docs/10-roadmap.md#12-desktop-implementation-order-verification-gates-and-grok-handoff--2026-11-07) and [scope/approvals](docs/11-decisions.md#16-desktop-workstation-handoff-scope-and-unresolved-gaps--2026-11-07). Follow [AGENTS.md](AGENTS.md); phase status and evidence are in [docs/10 §11](docs/10-roadmap.md).

**Current state (2026-11-07):** D00–D04 are committed on main (D04 at `3dd0299`): Overview, Signals, Positions/Journal with local manual records, and Diagnostics. D05 (launcher, source chooser, Textual parity) passed native QA on 2026-11-07. Qt is the optional locked `desktop` extra (PySide6-Essentials 6.11.3 in `pyproject.toml`/`uv.lock`); the VS Code-terminal GNOME settings issue remains a known limitation (docs/10 §11). `grog ui` remains the Textual fallback; this repository does not change the `gold` alias, and cutover needs the owner's separate explicit sign-off. No MT5/broker activation (M09-B blocked on owner approval, M10 not started).
