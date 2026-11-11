# 42_ALPHA_HUNT.md — ALPHA-HUNT-001: the reopened edge search

**Status: ACTIVE (owner directive 2026-07-05).**
Reopens the project after the 40_CONCLUSION.md negative result. This is NOT a
repudiation of that verdict — it is an attack on the space the conclusion
explicitly listed as **never tested**, with data the old lab never had.

## Owner directive (2026-07-05, verbatim intent)

Make the model profitable. Full authority to change/amend/overwrite anything.
High trade counts are fine (tens/hundreds of trades). "Remove gates and test
and add whatever it takes."

## Standing interpretation of "remove gates" (recorded in 11_DECISION_LOG.md)

- **Removed/removable:** process bureaucracy, retired-profile guards, cadence
  throttles, the "project closed" freeze, scope limits on data sources and
  methods, per-day entry caps for research.
- **Kept (measuring instrument, not throttle):** strictly-causal simulation,
  cost stress, walk-forward, random-entry baseline with multiple-comparison
  correction, out-of-sample holdout. Weakening these does not create profit;
  it removes the ability to detect losses before the account does.
- **Kept (absolute, owner's own standing rules):** demo-only, mandatory SL,
  no martingale, MT5 truth, kill switch.

## Why reopening is legitimate

40_CONCLUSION.md falsified **price patterns on free daily/H1 data + 60 days of
M5**. It explicitly did NOT test:

1. **The intraday space at scale** — the trade timeframe (M1/M5) was tested on
   60 days only, because data/raw was empty. Dukascopy publishes full free M1
   history; we now fetch 7.5 years (2019–2026) — ~50× more intraday sample.
2. **Time-of-day / day-of-week structure** — session-open drifts, fixing-time
   effects (London AM/PM fix), overnight-vs-intraday decomposition. Documented
   anomalies in gold literature; never tested here.
3. **Cross-asset intraday lead-lag** — silver, EURUSD, dollar index at M1
   resolution (fetched alongside gold). Only daily macro was ever tested.
4. **ML feature models** — gradient-boosted / regularized models over many
   engineered features with purged walk-forward CV, IC-first evaluation, then
   full cost-stressed trade simulation. The old lab only tested single
   hand-written rules and one daily Ridge model.
5. **Volatility structure** — vol-of-vol, squeeze/expansion cycles, realized
   vol forecasting for target/stop geometry (the one factor class that showed
   *real* effects even in the old lab).

## Program (phases; each gated by the honest harness)

- **A. DATA (running):** `scripts/fetch_dukascopy.py` → M1 2019–2026 for
  XAUUSD, XAGUSD, EURUSD, DOLLARIDXUSD → convert to the lab schema
  (`data/raw/XAUUSD_1M.csv`, loader aggregates M5/M15/H1). Validate against
  the old Yahoo data on overlap (done for spot-check; automate on convert).
- **B. MAP:** systematic conditional-return scan on 7.5y M1/M5/H1:
  time-of-day × day-of-week grids, session opens/fixes, momentum/reversal
  horizon spectrum, vol-regime conditioning. Output: ranked anomaly table
  with z-scores vs shuffled baselines (Bonferroni across the whole grid).
- **C. MODEL:** purged walk-forward ML (LightGBM/Ridge/logistic) on
  engineered features (returns ladder, vol ladder, session dummies,
  cross-asset lags, spread/liquidity proxies). Judge by OOS IC per fold,
  then trade-sim with the frozen classification gate + cost grid.
- **D. VERIFY:** anything that passes C replicates on the untouched holdout
  (2026 data reserved from B/C entirely) + random-entry baseline z ≥ 2.39.
- **E. DEPLOY (demo):** survivor(s) go through the existing
  ResearchForwardRunner → ExecutionGateway path on the demo account. High
  trade counts are acceptable per the owner; sizing per 03_RISK_POLICY.

## Honest expectancy statement

Nothing here guarantees an edge exists in the untested space. The commitment
is: if it exists at these horizons in this data, this program is strong enough
to find it; if we find nothing, that extends the negative result to the
intraday space and we say so plainly.
