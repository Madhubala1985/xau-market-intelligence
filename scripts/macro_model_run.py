#!/usr/bin/env python3
"""Multi-factor macro model for gold — walk-forward, out-of-sample.

Fixes the fragility of the single-lookback binary regime by using a CONTINUOUS,
multi-factor model with WALK-FORWARD cross-validation (expanding window, refit
quarterly, predictions are always out-of-sample). Judged on OOS information
coefficient and OOS Sharpe vs buy & hold — never in-sample fit.

Factors (all point-in-time / lagged, free data):
  real yield (DFII10) momentum 20d & 60d   -- falling real yields bullish gold
  broad dollar (DTWEXBGS) momentum 20d & 60d -- weak dollar bullish gold
  breakeven inflation (T10YIE) momentum 20d  -- rising inflation expectations bullish
  nominal 10y (DGS10) momentum 20d
  COT gold net-spec positioning (level + 52w z-score), lagged 4d for publication

Target: forward gold return over HORIZON trading days. Strategy: hold long/flat
(or long/short) by the sign of the OOS prediction; daily P&L = position * next-day
gold return, net of a turnover cost.
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sklearn.linear_model import Ridge  # noqa: E402

from research.data_loader import load_timeframe  # noqa: E402
from research.macro_data import asof_join, load_cot_net_spec, load_series  # noqa: E402
from src.data.enums import Timeframe  # noqa: E402

HORIZON = 20          # forward-return target horizon (trading days)
INITIAL_TRAIN = 750   # ~3y before first OOS prediction
REFIT_EVERY = 63      # refit quarterly
ALPHA = 10.0          # Ridge regularization (conservative; resists overffit)
COST = 0.0002         # per-unit-turnover daily cost


def _mom(series, i, n):
    if i < n or series[i] is None or series[i - n] is None:
        return None
    return series[i] - series[i - n]


def _sharpe(x):
    if len(x) < 2:
        return 0.0
    sd = statistics.pstdev(x)
    return statistics.fmean(x) / sd * (252 ** 0.5) if sd > 0 else 0.0


def _max_dd(x):
    peak = cum = mdd = 0.0
    for r in x:
        cum += r; peak = max(peak, cum); mdd = max(mdd, peak - cum)
    return mdd


def main() -> int:
    d1, rep = load_timeframe(Timeframe.D1)
    print(rep.summary())
    dates = [c.time_utc.date() for c in d1]
    closes = [c.close for c in d1]
    n = len(closes)

    ry = asof_join(dates, load_series("real_yield_10y"), lag_days=1)
    dx = asof_join(dates, load_series("broad_dollar"), lag_days=1)
    be = asof_join(dates, load_series("breakeven_10y"), lag_days=1)
    ny = asof_join(dates, load_series("nominal_10y"), lag_days=1)
    cot = asof_join(dates, load_cot_net_spec(), lag_days=4)
    cot_z = _rolling_z(cot, 252)

    feat_names = ["ry_chg20", "ry_chg60", "dx_chg20", "dx_chg60",
                  "be_chg20", "ny_chg20", "cot_level", "cot_z52"]
    X, y, idx = [], [], []
    for i in range(252, n - HORIZON):
        row = [_mom(ry, i, 20), _mom(ry, i, 60), _mom(dx, i, 20), _mom(dx, i, 60),
               _mom(be, i, 20), _mom(ny, i, 20), cot[i], cot_z[i]]
        if any(v is None for v in row):
            continue
        X.append(row)
        y.append(closes[i + HORIZON] / closes[i] - 1.0)   # forward return
        idx.append(i)
    X, y = np.array(X), np.array(y)
    print(f"samples: {len(X)}  features: {feat_names}")

    # Walk-forward expanding window, refit quarterly, OOS predictions only.
    preds = np.full(len(X), np.nan)
    start = INITIAL_TRAIN
    while start < len(X):
        end = min(start + REFIT_EVERY, len(X))
        Xtr, ytr = X[:start], y[:start]
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        model = Ridge(alpha=ALPHA).fit((Xtr - mu) / sd, ytr)
        preds[start:end] = model.predict((X[start:end] - mu) / sd)
        start = end

    mask = ~np.isnan(preds)
    oos_pred, oos_y = preds[mask], y[mask]
    oos_idx = [idx[k] for k in range(len(idx)) if mask[k]]
    ic = float(np.corrcoef(oos_pred, oos_y)[0, 1])
    print(f"\nOOS samples: {mask.sum()}  Information Coefficient (pred vs fwd-return): {ic:+.3f}")

    # Daily strategy: position from sign of latest OOS prediction.
    def run(longshort: bool):
        daily, bh, prev = [], [], 0.0
        for k in range(len(oos_idx) - 1):
            i = oos_idx[k]
            sig = oos_pred[k]
            pos = (1.0 if sig > 0 else -1.0) if longshort else (1.0 if sig > 0 else 0.0)
            r_next = closes[i + 1] / closes[i] - 1.0
            daily.append(pos * r_next - COST * abs(pos - prev)); bh.append(r_next); prev = pos
        return daily, bh

    for label, ls in (("long/flat", False), ("long/short", True)):
        daily, bh = run(ls)
        print(f"\n=== {label} strategy (OOS) ===")
        print(f"  strategy: ann={statistics.fmean(daily)*252*100:+.1f}%  Sharpe={_sharpe(daily):.2f}  maxDD={_max_dd(daily)*100:.1f}%")
        print(f"  buy&hold: ann={statistics.fmean(bh)*252*100:+.1f}%  Sharpe={_sharpe(bh):.2f}  maxDD={_max_dd(bh)*100:.1f}%")
        F = 5; m = len(daily)
        for f in range(F):
            lo, hi = m * f // F, m * (f + 1) // F
            seg, bseg = daily[lo:hi], bh[lo:hi]
            print(f"    fold{f+1} {dates[oos_idx[lo]]}..{dates[oos_idx[hi-1]]}: "
                  f"strat Sh={_sharpe(seg):+.2f} ann={statistics.fmean(seg)*252*100:+6.1f}% | "
                  f"B&H Sh={_sharpe(bseg):+.2f}")

    # Final model coefficients + current call.
    mu, sd = X.mean(0), X.std(0) + 1e-9
    final = Ridge(alpha=ALPHA).fit((X - mu) / sd, y)
    print("\nfinal standardized coefficients (sign/size sanity):")
    for nm, c in sorted(zip(feat_names, final.coef_), key=lambda t: -abs(t[1])):
        print(f"  {nm:<10} {c:+.4f}")
    latest = (X[-1] - mu) / sd
    print(f"\nCURRENT model call ({dates[oos_idx[-1] if oos_idx else -1]}): "
          f"predicted fwd {HORIZON}d gold return = {final.predict([latest])[0]*100:+.2f}% "
          f"-> {'LONG' if final.predict([latest])[0] > 0 else 'FLAT/SHORT'}")
    print("\nEdge only if OOS IC>0 AND strategy Sharpe beats B&H across folds.")
    return 0


def _rolling_z(series, win):
    out = [None] * len(series)
    for i in range(len(series)):
        if series[i] is None:
            continue
        lo = max(0, i - win)
        hist = [v for v in series[lo:i + 1] if v is not None]
        if len(hist) >= win // 2:
            m, s = statistics.fmean(hist), (statistics.pstdev(hist) or 1e-9)
            out[i] = (series[i] - m) / s
    return out


if __name__ == "__main__":
    raise SystemExit(main())
