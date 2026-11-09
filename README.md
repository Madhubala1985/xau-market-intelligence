# XAU/USD Gold Quant Research Platform

**A rigorous, falsification-first research and trading platform for spot gold (XAU/USD).**
~35,000 lines of Python · 850+ unit tests · 113 commits · MetaTrader 5 integration · 7.5 years of M1 tick-derived data

> **Outcome: a documented, statistically sound *negative result*.** Every Smart Money Concepts (SMC)
> pattern retail traders rely on was tested, both alone and in combination, against a random-entry baseline
> with out-of-sample replication. None survived. This project builds the machinery that tells the truth
> about an edge *before* money is risked, then reports that truth honestly. See [`40_CONCLUSION.md`](40_CONCLUSION.md).

---

## Why this project is interesting

Most retail trading bots get backtested once, look great, and lose money live. This project set out to do
the opposite: **prove the edge exists before automating anything**, using a pre-registered statistical gate
that a strategy has to pass, not one that gets tuned to pass.

### The standard of proof ([`41_METHODOLOGY.md`](41_METHODOLOGY.md))
A strategy only counts as an edge if it survives every stage, in order:

1. **Strictly causal backtest** (no look-ahead; bars finalized before decisions)
2. **Frozen classification gate**: ≥100 trades, expectancy ≥ +0.10R, profit factor ≥ 1.30, keeps ≥50% of its edge under a spread/slippage cost-stress grid
3. **Walk-forward / multi-regime k-fold**: positive across periods, not only recently
4. **Random-entry baseline** with identical stop/target geometry, Bonferroni-corrected (z ≥ 2.39)
5. **Out-of-sample holdout replication**: the 2026 holdout stayed unexamined until a final test

## What was built

| Layer | Components |
|---|---|
| **Data** | Dukascopy M1 fetcher (XAU, XAG, EURUSD, DXY; validated at 0.9997 correlation vs GLD), Yahoo GC=F, FRED macro (real yields, breakevens, dollar), CFTC COT positioning |
| **Market structure** | Swing detection, BOS/CHOCH, fair-value gaps, order blocks, supply/demand, liquidity sweeps, session/killzone levels |
| **Research lab** | Causal harness, setup library, edge scanner, factor-isolation battery, macro walk-forward Ridge model, ML walk-forward |
| **Risk** | Per-trade/daily/weekly circuit breakers, kill switch, mandatory stop-loss, no martingale, leverage and pyramiding policy |
| **Execution** | MT5 gateway (credential-masking, demo-only interlock), demo session planner, live shadow runner |
| **Governance** | 40+ policy/design documents, a decision log, and pre-registered test protocols committed *before* each run |

## Results: the full evidence chain

| Phase | Hypothesis | Verdict |
|---|---|---|
| SMC day-narrative brain | Replay-tuned to +10.7R over 12 days | Curve-fit; failed validation |
| Gold-Alpha EV scorer | Expected-value setup ranking | −15.93R / 10 days, 17% win rate → **not shipped** |
| 5 mechanical SMC setups on real data | London sweep, NY reversal, BOS+FVG retest, momentum… | **All No Edge / Insufficient** |
| Donchian H1 breakout + regime filters | Trend continuation | Real drift, but **non-stationary**: lost 2011–17, all profit in 2023–26 |
| Macro multi-factor model | Real yields + dollar + COT | OOS IC +0.079, but **Sharpe 0.64 < buy-and-hold 0.83** |
| Single-factor isolation (6 SMC factors) | FVG, sweep, displacement, CHOCH, OB, S/D | **0 of 6 beat random**; liquidity sweep was *significantly worse* than random (z = −5.77) |
| Gold-Intel three-brain rebuild | Narrative + macro dial + cost brain, multi-year gate | Gross **−1.56R over 596 trades** (a coin flip before costs) → **model stays flat** |

**Conclusion:** at daily/H1 horizons with free public data, gold is efficiently priced with respect to
the patterns retail SMC trading relies on. The only real effects (volatility regime, real-yield/dollar
regime) work as a **risk overlay** that reduces drawdown, not as alpha.

**Shipped artifact:** `research/regime.py` + `scripts/gold_regime.py`, an advisory macro regime risk dial.

## Skills demonstrated
- Quantitative research design: hypothesis pre-registration, multiple-comparison correction, walk-forward and k-fold validation, random baselines
- Avoiding backtest overfitting and look-ahead bias, plus cost modelling (spread, slippage, price-proportional bps)
- Production-style Python: typed domain models, ~850 tests, layered architecture, fail-closed safety interlocks
- Broker integration (MetaTrader 5) with demo-only enforcement and secret masking
- Scientific honesty: knowing when to stop and report a negative result

## Repository layout
```
src/          market structure, liquidity, regime, risk, execution, broker (MT5), backtest
research/     causal research harness, setups, macro data, metrics, regime dial
scripts/      data fetchers, edge scans, factor isolation, replay gates, demo tooling
tests/        unit and integration tests
reports/      research reports and gate results
00–44_*.md    charter, policies, designs, research findings, conclusion
```

## Running
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # demo credentials only
pytest -q                         # run the test suite
python scripts/fetch_dukascopy.py # fetch data (not included: ~2 GB)
python scripts/intel_replay.py --gate   # run the multi-year ship gate
python scripts/gold_regime.py     # macro regime risk dial
```
Raw market data and broker credentials are not included in this repository.

## Part of a three-project series
| Project | Market | Focus |
|---|---|---|
| **XAU/USD Gold Quant Research** (this repo) | Spot gold, MT5 | Edge discovery and statistical falsification |
| [Indian F&O Algo Trading v1](https://github.com/Madhubala1985/indian-fno-algo-trading-v1) | NSE BankNifty | First platform: event-driven architecture, paper trading |
| [Indian F&O Algo Trading v2](https://github.com/Madhubala1985/indian-fno-algo-trading-v2) | NSE/BSE index options | Live real-data dry-run on a cloud VM, options analytics, fail-closed execution |

---
*Built with AI-pair-programming (Claude Code) under a written engineering workflow (`09_CLAUDE_WORKFLOW.md`).
For research and education only. Not financial advice. No real-money trading was performed.*
