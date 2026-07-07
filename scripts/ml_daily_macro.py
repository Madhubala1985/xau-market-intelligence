#!/usr/bin/env python3
"""ALPHA-HUNT-001 Phase C2: daily-horizon walk-forward ML, price + macro jointly.

Protocol frozen BEFORE any result in reports/research/daily_ml_protocol.md —
read it first; nothing here may deviate from it.

- Data: data/raw/XAUUSD_1D.csv (< 2026-01-01; 2026 = untouched holdout),
  macro from the cached FRED store via research.macro_data (as-of join,
  1-day lag; COT 4-day lag).
- Targets: forward log-return over 1 / 5 / 20 trading days.
- Models: Ridge (z-scored) + HistGradientBoostingRegressor -> 6 combos,
  Bonferroni t >= 2.64.
- CV: expanding walk-forward, first train = 3y, test window/step = 126
  trading days, embargo = horizon days.
- Eval: pooled NON-OVERLAPPING OOS samples; IC = Spearman, t from n;
  top-decile mean fwd ret vs the 4.5 bps round-trip cost bar.

Output: reports/research/ml_daily_macro.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from research.macro_data import asof_join, load_cot_net_spec, load_series  # noqa: E402

CSV = ROOT / "data" / "raw" / "XAUUSD_1D.csv"
OUT = ROOT / "reports" / "research" / "ml_daily_macro.md"
HOLDOUT_START = pd.Timestamp("2026-01-01", tz="UTC")
HORIZONS = (1, 5, 20)
COST_RT_BPS = 4.5
T_BAR = 2.64  # Bonferroni alpha=0.05/6
TRAIN_YEARS = 3
TEST_DAYS = 126          # test window and step, trading days
MIN_TRAIN, MIN_TEST = 750, 40


def load_daily() -> pd.DataFrame:
    df = pd.read_csv(CSV)
    df["time"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time").drop_duplicates("time").set_index("time")
    df = df[df.index < HOLDOUT_START]
    return df[["open", "high", "low", "close"]].dropna()


def build_features(x: pd.DataFrame) -> pd.DataFrame:
    c = np.log(x["close"])
    f = pd.DataFrame(index=x.index)
    for k in (1, 5, 20, 60, 120):
        f[f"ret_{k}"] = c.diff(k)
    r1 = c.diff()
    f["vol_20"] = r1.rolling(20).std()
    f["vol_120"] = r1.rolling(120).std()
    f["vol_ratio"] = f["vol_20"] / f["vol_120"]
    dc_hi = x["close"].rolling(252).max()
    dc_lo = x["close"].rolling(252).min()
    f["donchian_pos_252"] = (x["close"] - dc_lo) / (dc_hi - dc_lo)

    dates = [t.date() for t in x.index]
    ry = pd.Series(asof_join(dates, load_series("real_yield_10y"), lag_days=1),
                   index=x.index, dtype=float)
    dx = pd.Series(asof_join(dates, load_series("broad_dollar"), lag_days=1),
                   index=x.index, dtype=float)
    be = pd.Series(asof_join(dates, load_series("breakeven_10y"), lag_days=1),
                   index=x.index, dtype=float)
    ny = pd.Series(asof_join(dates, load_series("nominal_10y"), lag_days=1),
                   index=x.index, dtype=float)
    cot = pd.Series(asof_join(dates, load_cot_net_spec(), lag_days=4),
                    index=x.index, dtype=float)
    for k in (5, 20, 60):
        f[f"ry_chg{k}"] = ry.diff(k)
        f[f"dx_chg{k}"] = dx.diff(k)
    f["be_chg20"] = be.diff(20)
    f["ny_chg20"] = ny.diff(20)
    f["cot_z52"] = (cot - cot.rolling(252).mean()) / cot.rolling(252).std()
    f["cot_chg20"] = cot.diff(20)
    return f


def walk_forward(f: pd.DataFrame, target: pd.Series, horizon: int, model_name: str):
    """Expanding walk-forward; returns pooled OOS predictions + per-fold ICs."""
    idx = f.index
    t0 = idx[0] + pd.DateOffset(years=TRAIN_YEARS)
    preds, reals, times = [], [], []
    fold_ics = []
    pos = int(np.searchsorted(idx, t0))
    while pos + MIN_TEST <= len(idx):
        test_pos = np.arange(pos, min(pos + TEST_DAYS, len(idx)))
        train_pos = np.arange(0, max(0, pos - horizon))  # embargo
        Xtr, ytr = f.iloc[train_pos], target.iloc[train_pos]
        Xte, yte = f.iloc[test_pos], target.iloc[test_pos]
        ok_tr = ytr.notna() & Xtr.notna().all(axis=1)
        ok_te = yte.notna() & Xte.notna().all(axis=1)
        Xtr, ytr, Xte, yte = Xtr[ok_tr], ytr[ok_tr], Xte[ok_te], yte[ok_te]
        if len(ytr) < MIN_TRAIN or len(yte) < MIN_TEST:
            pos += TEST_DAYS
            continue
        if model_name == "ridge":
            mu, sd = Xtr.mean(), Xtr.std().replace(0, 1)
            model = Ridge(alpha=10.0)
            model.fit((Xtr - mu) / sd, ytr)
            p = model.predict((Xte - mu) / sd)
        else:
            model = HistGradientBoostingRegressor(
                max_iter=300, learning_rate=0.05, random_state=7)
            model.fit(Xtr, ytr)
            p = model.predict(Xte)
        preds.append(pd.Series(p, index=Xte.index))
        reals.append(yte)
        if len(yte) >= 10:
            ic, _ = spearmanr(p, yte)
            fold_ics.append((Xte.index[-1].date(), len(yte), float(ic)))
        pos += TEST_DAYS
    if not preds:
        return None
    pred = pd.concat(preds)
    real = pd.concat(reals)
    # non-overlapping subsample: every horizon-th pooled OOS day
    keep = np.arange(0, len(pred), horizon)
    return pred.iloc[keep], real.iloc[keep], fold_ics


def main() -> int:
    x = load_daily()
    print(f"daily bars (train/CV, <2026): {len(x)}  "
          f"{x.index[0].date()} .. {x.index[-1].date()}")
    f = build_features(x)
    c = np.log(x["close"])
    lines = [
        "# Phase C2: daily-horizon walk-forward ML — price + macro jointly "
        "(XAUUSD D1, 2011-2025)",
        "",
        "Protocol: reports/research/daily_ml_protocol.md (frozen before this run).",
        f"Cost bar: {COST_RT_BPS} bps round trip. Bonferroni t >= {T_BAR} "
        "over 6 combos. 2026 untouched.",
        "",
    ]
    verdicts = []
    for horizon in HORIZONS:
        target = c.shift(-horizon) - c
        for model_name in ("ridge", "hgb"):
            res = walk_forward(f, target, horizon, model_name)
            if res is None:
                lines.append(f"- {model_name} h={horizon}: no usable folds")
                continue
            pred, real, fold_ics = res
            n = len(pred)
            ic, _ = spearmanr(pred, real)
            t = ic * np.sqrt(n - 2) / np.sqrt(max(1e-12, 1 - ic * ic))
            dec = max(1, n // 10)
            order = np.argsort(pred.values)
            top = real.values[order[-dec:]]
            top_bps = float(np.mean(top)) * 1e4
            net = top_bps - COST_RT_BPS
            pos_folds = sum(1 for _, _, fic in fold_ics if fic > 0)
            passed = (ic > 0 and t >= T_BAR and net > 0)
            verdict = "**CANDIDATE -> Phase D**" if passed else "**no edge**"
            verdicts.append(passed)
            lines.append(
                f"- {model_name} h={horizon}: pooled non-overlap n={n} "
                f"IC={ic:+.4f} t={t:+.2f} | top-decile {top_bps:+.2f} bps "
                f"(net {net:+.2f}) | folds IC>0: {pos_folds}/{len(fold_ics)} "
                f"-> {verdict}")
            print(lines[-1])
    lines += ["", "## Per-fold ICs (descriptive)", ""]
    for horizon in HORIZONS:
        target = c.shift(-horizon) - c
        for model_name in ("ridge", "hgb"):
            res = walk_forward(f, target, horizon, model_name)
            if res is None:
                continue
            _, _, fold_ics = res
            lines.append(f"### {model_name} h={horizon}")
            lines += [f"  {d}  n={nn:4d}  ic={fic:+.4f}"
                      for d, nn, fic in fold_ics]
            lines.append("")
    OUT.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {OUT}")
    print("RESULT:", "candidate(s) found" if any(verdicts)
          else "ALL no edge — negative result extends to daily joint price+macro")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
