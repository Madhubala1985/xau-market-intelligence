# Pre-registered protocol: Phase C2 — daily-horizon ML, joint price + macro features

**Frozen 2026-07-07 BEFORE any result was computed.** (ALPHA-HUNT-001,
decision 2026-07-05-01 honesty gates.)

## Motivation (what is genuinely untested)

- The June 2026 daily macro model (`scripts/macro_model_run.py`) used ONLY
  macro momentum features, ONLY Ridge, and was judged on "beats buy-and-hold"
  (verdict: OOS IC +0.079, long/flat Sharpe 0.64 vs B&H 0.83 → not deployed).
- Phase C (`scripts/ml_walkforward.py`) tested intraday H1 horizons 4/12/24
  bars — all No Edge — and the program lesson is that XAU edges must clear
  ~4.5 bps round-trip, which at DAILY holds is small vs ~100 bps/day vol.
- Never tested: daily horizon, price/vol features AND macro features jointly,
  linear + nonlinear models, judged IC-first on non-overlapping samples with
  a Bonferroni bar and net-of-cost economics (not B&H comparison).

## Data

- `data/raw/XAUUSD_1D.csv` (MT5 daily, 2011-06 .. 2026-06). Train/CV strictly
  `< 2026-01-01`; **2026 is the untouched Phase D holdout**.
- Macro from the cached FRED store `data/raw/macro/` via `research/macro_data.py`
  (as-of join, 1-calendar-day publication lag; COT lagged 4 days).

## Design (all pre-declared)

- Targets: forward log-return over **1, 5, 20 trading days**.
- Models: **Ridge(alpha=10, z-scored features)** and
  **HistGradientBoostingRegressor(default depth, 300 iters, lr 0.05)**.
  2 models × 3 horizons = **6 combos → Bonferroni t ≥ 2.64** (α=0.05/6).
- Features (all causal at the daily close):
  price ladder `ret_{1,5,20,60,120}`; vol `vol_20`, `vol_120`, `vol_ratio`;
  `donchian_pos_252`; real-yield momentum `ry_chg{5,20,60}`; broad-dollar
  momentum `dx_chg{5,20,60}`; `be_chg20`; `ny_chg20`; COT net-spec `cot_z52`
  and 4-week change `cot_chg20`.
- CV: expanding walk-forward. First train end = first bar + 3 years; test
  window and step = 126 trading days; embargo = `horizon` trading days
  between train end and test start (purges label overlap). Folds with
  < 750 train rows or < 40 test rows are skipped.
- Evaluation on OOS predictions only, **non-overlapping samples**
  (every `horizon`-th test day, pooled across all folds):
  - IC = Spearman(pred, realized) on the pooled non-overlapping sample;
    t = IC·√(n−2)/√(1−IC²).
  - Decile economics on the same pooled sample: mean forward return (bps) of
    the top decile of predictions, minus the **4.5 bps round-trip cost bar**.
  - Per-fold IC sign consistency reported (descriptive, not a gate).

## PASS bar (pre-declared)

A combo is a candidate ONLY if **both**:
1. pooled non-overlapping IC > 0 with **t ≥ 2.64**, and
2. top-decile long-only mean forward return **net of 4.5 bps > 0**.

Anything less: **No Edge** — recorded, and the negative result extends to the
daily joint price+macro space. A passing combo goes to Phase D (2026 holdout
replication + random baseline) before anything else happens.

## What this protocol may NOT do after results are seen

No adding/removing features, horizons, models, or thresholds; no switching
IC definitions; no re-running with different fold geometry. Any variation is
a NEW protocol, registered before its run.
