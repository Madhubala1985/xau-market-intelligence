# 30_RESEARCH_FINDINGS.md — XAU edge search, iteration 1

**Date:** 2026-06-18. **Data:** GC=F (gold futures, an XAUUSD proxy) from Yahoo —
~60 days of M5 (13.5k bars) and ~2 years of H1 (13.8k bars). A first real read;
reconfirm on the broker feed (`scripts/export_mt5_history.py`) when available.

## Method

1. **Edge scan** (`scripts/edge_scan.py`): for a battery of standard, low-DOF
   conditions, measure forward return (in ATR units) at 4/8/24-bar horizons —
   pure SIGNAL edge, decoupled from stops/targets. This isolates "is there
   directional drift?" from "are the exits right?".
2. **Backtest** promising signals as full setups through the causal harness
   (market or limit entry, ATR stops/targets, optional time stop), in R, with a
   spread/slippage stress grid.
3. **Train/test split** (first 70% / last 30%) on any candidate with an edge:
   keep ONLY if positive in BOTH slices (the anti-overfit gate).

## What the edge scan found

- **H1 trend persists; H1 mean-reversion loses.** A 20-bar Donchian breakout had
  positive, horizon-growing forward drift (+0.08 → +0.16 → **+0.60 ATR** at 4/8/24h,
  55.5% directional, n=1478). Fading H1 extremes (Bollinger/RSI) was **negative**.
- **M5 is the opposite (short-horizon mean-reverting):** fading a big M5 bar showed
  positive forward drift (+0.20 ATR/8 bars, ~55%). Breakouts faded intraday.
- This is why the SMC/FVG setups failed: short-horizon, often counter-trend,
  session-boxed reversion — fighting the only persistent edge (H1 trend).

## Setups tested (R, base costs; full reports in reports/research/)

| setup | exec | trades | win | expectancy | verdict |
|---|---|---|---|---|---|
| donchian_breakout_trend | H1 | 551 | 33.4% | −0.044R | No Edge |
| mean_reversion_m5 | M5 | 331 | 47.4% | −0.136R | No Edge |
| momentum_continuation | M5 | 147 | 23.8% | −0.137R | No Edge |
| trend_bos_fvg_retest | M5 | 35 | 25.7% | −0.338R | Insufficient Data |
| ny_london_sweep_reversal | M5 | 9 | 11.1% | −0.732R | Insufficient Data |
| london_sweep_reclaim_long | M5 | 8 | 25.0% | −0.398R | Insufficient Data |
| london_asian_high_short | M5 | 0 | — | — | never fired in 60d |

## The key result: the breakout edge is NON-STATIONARY

Exit calibration on Donchian (`scripts/donchian_tune.py`), train/test split:

- **Train (older ~2024–25): every exit config LOSES** (−0.00 to −0.17R).
- **Test (recent ~2026): every config WINS** (+0.05 to +0.11R, 53–56%).

The breakout edge is **regime-dependent**: real in the recent regime, absent
earlier. Full-period expectancy is ~breakeven-negative. Per the anti-overfit
gate (positive in BOTH), **nothing qualifies. No Proven Edge Candidate exists.**

## Honest conclusion

- **Automation is NOT justified.** Across 7 mechanical setups + a systematic
  signal scan, there is no robust, stationary, tradeable edge in the available
  data. The one real signal (H1 breakout) only works in the recent regime.
- **The lab is working.** It cheaply disproved 7 ideas and one whole signal class
  in a session, with zero capital at risk — exactly its job.

## What to build / do next

1. **Broker-feed, multi-year M5** (`export_mt5_history.py`): Yahoo caps M5 at 60d,
   and the H1 spans a regime shift. Real stationarity testing on the M5 timeframe
   (where the setups trade) needs years of the actual broker feed.
2. **Top live lead: regime-conditioned trend** — the breakout edge is real *in
   regime*. The disciplined next hypothesis is a regime filter (volatility/trend
   state) gating the H1 breakout — but it ADDS degrees of freedom, so it must be
   validated train/test on more data before it means anything.
3. **Do NOT deploy any current setup.** Forward-testing on demo will not create an
   edge that the backtest says isn't there.

## Iteration 3 (2026-06-18): MACRO track — real yields + dollar regime

Pivoted from price patterns to gold's actual drivers. Free, keyless FRED data
(`research/macro_data.py`): 10y TIPS real yield (DFII10, 2003+) and broad dollar
(DTWEXBGS, 2006+), as-of joined to 15y daily gold with a 1-day publication lag.
Tool: `scripts/macro_edge_scan.py`.

**Robust descriptive finding (large sample, economically sound):** gold's forward
1-day return by regime (20d trend of yields & dollar) —
- EASING (both falling): +13.7%/yr, n=1122
- MIXED: +14.1%/yr, n=1406
- **TIGHTENING (both rising): −0.3%/yr, n=1139** — tightening flattens gold's drift.

**Strategy ("hold gold unless tightening"), 15y, 5-fold:** Sharpe 0.66 vs B&H
0.56, maxDD 37% vs 50.5%, positive Sharpe in all 5 folds (beats B&H in bear/chop
2011-17 & 2020-23; lags in raging bulls). Looked like a real risk-overlay edge —
**BUT it is lookback-fragile:** the Sharpe improvement appears only at N=20;
N=10/40/60 match or underperform B&H. So the *descriptive* regime effect is real
and robust, but a naive binary overlay does NOT yield a parameter-robust edge
over buy-and-hold. Current regime (2026-06-17): TIGHTENING (yields & dollar both
rising) — the overlay would reduce gold here.

**Verdict:** the macro thesis is confirmed (real yields + dollar genuinely drive
gold; tightening is the bad state), but extracting robust tradeable alpha from a
2-variable binary regime is fragile. Right next step: a CONTINUOUS multi-factor
macro model (real yield level+change, dollar, breakevens, term premium, COT
positioning) with proper walk-forward cross-validation and a held-out test —
judged on out-of-sample Sharpe, not in-sample fit. This is the most promising
direction found; it is NOT yet deployable.

## Iteration 4 (2026-06-18): multi-factor walk-forward macro model

Built the continuous, cross-validated model (`scripts/macro_model_run.py`,
`research/macro_data.py`) the fragility result called for. 8 factors (real-yield
/ dollar / breakeven / nominal-yield momentum + COT gold net-spec level & 52w
z-score), all point-in-time/lagged; Ridge, expanding-window walk-forward, refit
quarterly, OOS-only predictions. 15y daily gold, ~2,700 OOS days (2015-2026).

Results: **OOS IC = +0.079** (weak but real predictive signal). As a strategy it
**does NOT beat buy & hold**: long/flat Sharpe 0.64 vs B&H 0.83 (underperforms in
all 5 folds; only lower drawdown, 18.5% vs 22.3%); long/short Sharpe 0.07
(disastrous — no short edge in a secular bull). Final coefficients are tiny and
several economically wrong-signed -> mostly noise + a slight long tilt.

**Converged conclusion (price-pattern + macro tracks):** at the daily horizon
with free public data, there is NO tradeable edge that beats simply holding gold.
Macro factors relate to gold but the relationship is largely contemporaneous, not
predictive enough to beat B&H after costs. The only defensible practical output
is a RISK overlay: hold gold (positive drift), scale exposure down in real-yield+
dollar tightening regimes to cut drawdown (drawdown-positive, ~Sharpe-neutral) —
NOT alpha. Genuine edges would require different resources (intraday/broker tick
data + latency, options/vol, cross-asset RV, alternative data) — bigger projects
with uncertain payoff. Run: `python scripts/macro_model_run.py`.

## Iteration 2 (2026-06-18): regime filter + multi-year, multi-timeframe

Pursued the one lead (H1 breakout) with regime filters (slow-EMA trend
alignment, ATR high-volatility state), validated by train/test and k-fold.

- **H1, vol-filtered breakout:** train/test both positive, but a 3-fold split
  showed one fold negative for each variant -> **Weak Edge, not stationary.**
- **Daily, vol+trend-filtered breakout (5y):** looked excellent — positive in all
  3 folds, PF 2.35, +0.62R — but only 55 trades (Insufficient Data).
- **Daily, same strategy, 15y (3.7k bars, 2011–2026), 5-fold:** the decisive
  test. **Lost in 2011–2017, breakeven 2017–2023, +0.75R only in 2023–2026.**
  Full 15y: 129 trades, +0.096R, PF 1.15 -> **Weak Edge**, entirely recency-driven.

**Verdict for the whole search:** no robust, stationary, mechanically-tradeable
edge exists in gold price action on the timeframes/data tested. Every positive
result is a regime artifact — extending the window to cover gold's 2011–2019
bear/range markets turns it negative. The recent breakout profitability is a BET
that gold keeps trending, not an edge. **No Proven Edge Candidate. Nothing is
fit to deploy, on demo or otherwise.** Loader now skips malformed vendor rows;
DonchianBreakoutTrend gained optional regime filters + a configurable exec
timeframe. Tooling: scripts/edge_scan.py, scripts/donchian_tune.py.
