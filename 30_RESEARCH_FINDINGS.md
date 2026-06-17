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
