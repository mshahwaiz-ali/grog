# Research and technical references
These are **starting points to verify during research**, not proof that a particular scalping system works. Capture access date and relevant sections as implementation proceeds.
- World Gold Council, gold market structure and Goldhub research: https://www.gold.org/goldhub and https://www.gold.org/about-gold/market-structure-and-flows
- CME Group, gold futures market and contract specifications: https://www.cmegroup.com/markets/metals/precious/gold.html
- MQL5, strategy testing and real ticks: https://www.metatrader5.com/en/terminal/help/algotrading/testing and https://www.mql5.com/en/articles/75
- MetaTrader 5 Python integration (OPTIONAL adapter; assess use only for read-only quotes): https://www.mql5.com/en/docs/python_metatrader5
- Federal Reserve monetary policy calendars and statements: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
- Bureau of Labor Statistics release schedules: https://www.bls.gov/schedule/
- StockCharts, Average True Range calculations: https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/average-true-range-atr-and-average-true-range-percent-atrp
- David H. Bailey et al., research on backtest overfitting: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- SEC investor education for short-term trading risk: https://www.investor.gov/
- scikit-learn, probability calibration/reliability diagrams (how to interpret empirical event probabilities, **not** support for Grog confidence claims): https://scikit-learn.org/stable/modules/calibration
- Bailey, Borwein, López de Prado & Zhu, *The Probability of Backtest Overfitting*, peer-reviewed publication abstract: https://scholarworks.wmich.edu/math_pubs/42/
## Verification rules
Source-specific exchange futures volume/order book must not be assumed to measure full OTC XAUUSD spot activity. Do not claim that indicator choices or patterns have verified edge from descriptive sources alone. Cite empirical studies, preserve raw tests and note adverse evidence in strategy research.

## Official market-data and broker-execution research — verified 2026-10-31

- **MetaTrader 5 demo account and selected broker server (MT5 is not a standalone universal feed):** https://www.metatrader5.com/en/terminal/help/startworking/acc_open
- **MetaTrader 5 OTC BID/ASK quote formation and broker counterparties:** https://www.metatrader5.com/en/terminal/help/trading_advanced/price_data
- **World Gold Council, decentralized gold OTC trade and negotiated prices:** https://www.gold.org/about-us/what-we-do/market-infrastructure/gold-trading-wholesale-market


These sources document access mechanisms and limits; **none** proves any trading strategy is profitable.

- **MetaTrader 5 official Linux/Wine installation:** https://www.metatrader5.com/en/terminal/help/start_advanced/install_linux
- **MQL5 historical tick range and `MqlTick` timestamp/flags:** https://www.mql5.com/en/docs/series/copyticksrange
- **MQL5 `OnTick` callback queue coalescing:** https://www.mql5.com/en/docs/event_handlers/ontick
- **MQL5 read-only symbol properties and broker contract fields:** https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants
- **MT5 real versus generated ticks, floating spread and source-limitations:** https://www.metatrader5.com/en/terminal/help/algotrading/tick_generation
- **cTrader official live/historical quotes and history window/pagination:** https://help.ctrader.com/open-api/symbol-data/
- **cTrader authentication and access tokens:** https://help.ctrader.com/open-api/account-authentication/
- **cTrader API usage rate limits and SDK support:** https://help.ctrader.com/open-api/
- **Dukascopy official historical BID/ASK export interface:** https://www.dukascopy.com/api/data/get/historical-data-export

**Implementation caveats:** Quote-event callbacks need not be a reliable count of all market ticks; data quality and catch-up must be tested. The actual tradable broker symbol is not standardized across all spot Gold/CFD brokers. Dukascopy historical XAUUSD, cTrader and MT5 historical/live quotes are **not interchangeable** without explicit spread/time/contract fidelity testing. A real bid/ask entry/exit path already embeds spread; do not subtract the same spread again as a separate charge.

The canonical requirements are in [03 — Market Data](03-market-data.md), [07 — Risk & Monitoring](07-risk-and-monitoring.md), and [08 — Validation](08-validation.md). Source access and current capability should be re-verified at the time of implementation.

## Official developer and terminal UI sources — planning reference 2026-10-31

- Textual Python application widgets/layouts/keyboard integration: https://github.com/Textualize/textual/blob/main/docs/guide/app.md
- Textual DataTable behavior, row focus and dynamic updates: https://github.com/Textualize/textual/blob/main/docs/widgets/data_table.md
- Textual official headless testing: `App.run_test()`, `Pilot` and terminal sizes: https://textual.textualize.io/guide/testing/
- Python package structure and `pyproject.toml`: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
- uv project creation, dependency synchronization, lock file: https://docs.astral.sh/uv/guides/projects/
- Ruff local lint/format commands: https://docs.astral.sh/ruff/
- pytest isolated temporary test paths: https://pytest.org/en/latest/how-to/tmp_path.html
- Python `sqlite3` transaction and connection behavior: https://docs.python.org/3/library/sqlite3.html

These references justify implementation choices, **not** future trading profitability. Prefer officially maintained tool documentation and test installed version-specific APIs. They do not authorize creating a web service, running any GitHub Actions, placing broker orders or adding feature bloat.
