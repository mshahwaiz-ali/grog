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