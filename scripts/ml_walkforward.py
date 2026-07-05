#!/usr/bin/env python3
"""ALPHA-HUNT-001 Phase C: purged walk-forward ML on XAUUSD H1.

Pre-declared design (before any result is seen):
- Bars: H1 aggregated from Dukascopy M1 (filler-filtered). 2019..2025 only;
  2026 is the untouched Phase D holdout.
- Targets: forward log-return over 4 / 12 / 24 H1 bars.
- Models: Ridge (linear control) + HistGradientBoostingRegressor.
  6 model x horizon combos total -> Bonferroni over 6 on the IC t-stat.
- CV: expanding walk-forward. First train window 2 years, test the next
  13 weeks, step 13 weeks; an embargo gap of `horizon` bars between train
  end and test start (purge label overlap).
- Features (all causal at bar close): return ladder, vol ladder + ratio,
  range/ATR, Donchian position, ET-clock encodings + session dummies,
  volume anomaly, cross-asset return ladders (XAG, EUR, DXY) + gold/silver
  ratio z-score. Cross-asset features are lagged one bar to kill any
  timestamp-boundary ambiguity.
- Verdict metrics per combo, OOS only:
    IC        = Spearman(pred, realized) on NON-OVERLAPPING samples
                (every `horizon`-th test bar), t-stat across folds;
    decile    = mean fwd ret (bps) top decile minus bottom decile of pred,
                non-overlapping samples;
    economic  = decile spread per trade vs the 4.5 bps round-trip cost
                bar (2.2 bps spread each side, stressed).
- PASS bar (pre-declared): mean fold IC > 0 with Bonferroni-corrected
  t >= 2.64 (alpha=0.05/6) AND top-decile long-only net > 0 at 4.5 bps
  round-trip. Anything less: No Edge.

Output: reports/research/ml_walkforward.md
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
DUKA = ROOT / "data" / "raw" / "dukascopy"
OUT = ROOT / "reports" / "research" / "ml_walkforward.md"
HOLDOUT_START = pd.Timestamp("2026-01-01", tz="UTC")
HORIZONS = (4, 12, 24)
COST_RT_BPS = 4.5  # 2.2 bps spread each side, rounded up
N_COMBOS = 6
T_BAR = 2.64  # Bonferroni alpha=0.05/6, two-sided


def load_h1(instr: str) -> pd.DataFrame:
    files = sorted(DUKA.glob(f"{instr}_M1_*.csv"))
    if not files:
        sys.exit(f"missing {instr} M1 files")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df[df["volume"] > 0].drop_duplicates("time").sort_values("time").set_index("time")
    df = df[df.index < HOLDOUT_START]
    o = df["open"].resample("1h").first()
    h = df["high"].resample("1h").max()
    lo = df["low"].resample("1h").min()
    c = df["close"].resample("1h").last()
    v = df["volume"].resample("1h").sum()
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "vol": v}).dropna()


def build_features(x: pd.DataFrame, xag: pd.DataFrame, eur: pd.DataFrame,
                   dxy: pd.DataFrame) -> pd.DataFrame:
    c = np.log(x["close"])
    f = pd.DataFrame(index=x.index)
    for k in (1, 2, 4, 8, 24, 48, 120):
        f[f"ret_{k}"] = c.diff(k)
    r1 = c.diff()
    f["vol_24"] = r1.rolling(24).std()
    f["vol_120"] = r1.rolling(120).std()
    f["vol_ratio"] = f["vol_24"] / f["vol_120"]
    tr = (x["high"] - x["low"]) / x["close"]
    f["range_24"] = tr.rolling(24).mean()
    dc_hi = x["close"].rolling(480).max()
    dc_lo = x["close"].rolling(480).min()
    f["donchian_pos"] = (x["close"] - dc_lo) / (dc_hi - dc_lo)
    et = x.index.tz_convert("America/New_York")
    f["hod_sin"] = np.sin(2 * np.pi * et.hour / 24)
    f["hod_cos"] = np.cos(2 * np.pi * et.hour / 24)
    f["dow"] = et.dayofweek
    f["sess_asia"] = ((et.hour >= 19) | (et.hour < 3)).astype(int)
    f["sess_london"] = ((et.hour >= 3) & (et.hour < 11)).astype(int)
    hour_avg_vol = x["vol"].groupby(et.hour).transform(lambda s: s.rolling(30, min_periods=5).mean())
    f["vol_anom"] = x["vol"] / hour_avg_vol
    for name, other in (("xag", xag), ("eur", eur), ("dxy", dxy)):
        oc = np.log(other["close"])
        aligned = oc.reindex(x.index, method="ffill")
        for k in (1, 4, 24):
            f[f"{name}_ret_{k}"] = aligned.diff(k).shift(1)  # extra 1-bar lag
    gs = c - np.log(xag["close"]).reindex(x.index, method="ffill")
    f["gs_ratio_z"] = (gs - gs.rolling(480).mean()) / gs.rolling(480).std()
    return f


def walk_forward(f: pd.DataFrame, target: pd.Series, horizon: int, model_name: str):
    idx = f.index
    start_train_end = idx[0] + pd.DateOffset(years=2)
    step = pd.Timedelta(weeks=13)
    fold_stats = []
    t0 = start_train_end
    while t0 + step <= idx[-1]:
        train_mask = idx < t0 - pd.Timedelta(hours=horizon)  # embargo
        test_mask = (idx >= t0) & (idx < t0 + step)
        Xtr, ytr = f[train_mask], target[train_mask]
        Xte, yte = f[test_mask], target[test_mask]
        ok_tr = ytr.notna() & Xtr.notna().all(axis=1)
        ok_te = yte.notna() & Xte.notna().all(axis=1)
        Xtr, ytr, Xte, yte = Xtr[ok_tr], ytr[ok_tr], Xte[ok_te], yte[ok_te]
        if len(ytr) < 2000 or len(yte) < 200:
            t0 += step
            continue
        if model_name == "ridge":
            mu, sd = Xtr.mean(), Xtr.std().replace(0, 1)
            model = Ridge(alpha=10.0)
            model.fit((Xtr - mu) / sd, ytr)
            pred = model.predict((Xte - mu) / sd)
        else:
            model = HistGradientBoostingRegressor(
                max_depth=3, max_iter=200, learning_rate=0.05,
                l2_regularization=1.0, random_state=0)
            model.fit(Xtr, ytr)
            pred = model.predict(Xte)
        pred = pd.Series(pred, index=yte.index)
        # non-overlapping evaluation samples
        no = pred.iloc[::horizon]
        yno = yte.iloc[::horizon]
        if len(no) < 20:
            t0 += step
            continue
        ic = spearmanr(no, yno).statistic
        q_hi = no.quantile(0.9)
        q_lo = no.quantile(0.1)
        top = yno[no >= q_hi].mean() * 1e4
        bot = yno[no <= q_lo].mean() * 1e4
        fold_stats.append({"fold_end": (t0 + step).date(), "n": len(no), "ic": ic,
                           "top_bps": top, "bot_bps": bot})
        t0 += step
    return pd.DataFrame(fold_stats)


def main() -> None:
    xau = load_h1("XAUUSD")
    xag = load_h1("XAGUSD")
    eur = load_h1("EURUSD")
    dxy = load_h1("DOLLARIDXUSD")
    print(f"H1 bars: xau={len(xau)} xag={len(xag)} eur={len(eur)} dxy={len(dxy)}")
    f = build_features(xau, xag, eur, dxy)
    c = np.log(xau["close"])
    lines = ["# Phase C: purged walk-forward ML (XAUUSD H1, 2019-2025)\n",
             f"Cost bar: {COST_RT_BPS} bps round trip. Bonferroni t >= {T_BAR} over "
             f"{N_COMBOS} combos. 2026 untouched.\n"]
    results = []
    for horizon in HORIZONS:
        target = (c.shift(-horizon) - c)
        for model_name in ("ridge", "hgb"):
            fs = walk_forward(f, target, horizon, model_name)
            if fs.empty:
                continue
            ics = fs["ic"].to_numpy()
            t_ic = ics.mean() / (ics.std(ddof=1) / np.sqrt(len(ics)))
            top_net = fs["top_bps"].mean() - COST_RT_BPS
            spread = (fs["top_bps"] - fs["bot_bps"]).mean()
            verdict = "PASS" if (ics.mean() > 0 and t_ic >= T_BAR and top_net > 0) else "no edge"
            row = (f"{model_name} h={horizon}: folds={len(fs)} mean IC={ics.mean():+.4f} "
                   f"t={t_ic:+.2f} | top-decile {fs['top_bps'].mean():+.2f} bps "
                   f"(net {top_net:+.2f}) | decile spread {spread:+.2f} bps -> **{verdict}**")
            print(row)
            lines.append("- " + row)
            results.append((model_name, horizon, fs))
    lines.append("\n## Per-fold detail\n")
    for model_name, horizon, fs in results:
        lines.append(f"\n### {model_name} h={horizon}\n")
        lines.append(fs.to_string(index=False))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(str(x) for x in lines) + "\n")
    print(f"\nreport: {OUT}")


if __name__ == "__main__":
    main()
