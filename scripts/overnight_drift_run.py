#!/usr/bin/env python3
"""Evaluate the frozen overnight-drift rule (ALPHA-HUNT-001 candidate v1).

Rule (frozen in reports/research/overnight_drift_protocol.md BEFORE any
validation/holdout look): Mon-Thu, long XAUUSD 16:50 ET -> 18:20 ET.

Periods:
  --period train       2019-01-01 .. 2024-12-31 (rule was chosen here)
  --period validation  2025-01-01 .. 2025-12-31 (criterion 2)
  --period holdout     2026-01-01 ..            (criterion 3 — final)

Cost model: entry pays the tick-measured 16:50 ET median ask/bid spread
(2.21 bps, 2026-07-05 measurement, n=230-day study); exit is bid-referenced
(candles are bid), so bid-to-bid return minus entry spread = net. Stress
grid multiplies the spread by 1.0 / 1.5 / 2.0.

Random baseline (criterion 4): 1000 random same-length (90-min) long
windows with uniform random start times in the same period, same cost —
the rule's GROSS mean must beat the 99.9th percentile of random means.

Usage: python3 scripts/overnight_drift_run.py --period validation
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
M1_CSV = ROOT / "data" / "raw" / "XAUUSD_1M.csv"

ENTRY_SPREAD_BPS = 2.21  # tick-measured median at 16:50 ET (2026-07-05)
STRESS = (1.0, 1.5, 2.0)
PERIODS = {
    "train": ("2019-01-01", "2025-01-01"),
    "validation": ("2025-01-01", "2026-01-01"),
    "holdout": ("2026-01-01", "2099-01-01"),
}


def load(period: str) -> pd.DataFrame:
    lo, hi = PERIODS[period]
    df = pd.read_csv(M1_CSV, usecols=["time_utc", "open", "close"])
    df["time"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.set_index("time").drop(columns=["time_utc"]).sort_index()
    df = df[(df.index >= lo) & (df.index < hi)]
    if df.empty:
        sys.exit(f"no data in period {period}")
    et = df.index.tz_convert("America/New_York")
    return df.assign(et_hour=et.hour, et_min=et.minute, et_date=et.date, et_dow=et.dayofweek)


def rule_returns(df: pd.DataFrame) -> pd.Series:
    """Bid-to-bid gross log-return (bps) per trade of the frozen rule."""
    wd = df[df["et_dow"].isin([0, 1, 2, 3])]
    entry = wd[(wd["et_hour"] == 16) & (wd["et_min"] >= 45)].groupby("et_date")["close"].last()
    after = wd[(wd["et_hour"] > 18) | ((wd["et_hour"] == 18) & (wd["et_min"] >= 20))]
    exit_px = after[after["et_hour"] >= 18].groupby("et_date")["open"].first()
    r = (np.log(exit_px / entry) * 1e4).dropna()
    r.index = pd.to_datetime(r.index)
    return r


def random_baseline(df: pd.DataFrame, n_windows: int, hold_min: int, rng) -> np.ndarray:
    """Mean gross return of `n_windows` sets of daily long trades at a random
    fixed start time each (uniform over the 24h clock), 90-min hold."""
    c = df["close"]
    means = []
    minutes = df.index.floor("min")
    px = c.groupby(minutes).last()
    full_idx = pd.date_range(px.index[0], px.index[-1], freq="min", tz="UTC")
    px = px.reindex(full_idx).ffill()
    dates = pd.DatetimeIndex(px.index.date).unique()
    for _ in range(n_windows):
        start_min = int(rng.integers(0, 24 * 60))
        entries = pd.DatetimeIndex(dates) + pd.Timedelta(minutes=start_min)
        entries = entries.tz_localize("UTC")
        exits = entries + pd.Timedelta(minutes=hold_min)
        pe = px.reindex(entries).to_numpy()
        pxit = px.reindex(exits).to_numpy()
        r = np.log(pxit / pe) * 1e4
        r = r[np.isfinite(r)]
        # keep only windows with real movement (market open)
        r = r[r != 0.0]
        if len(r) > 50:
            means.append(np.nanmean(r))
    return np.array(means)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", choices=list(PERIODS), default="train")
    ap.add_argument("--baseline", action="store_true", help="run the 1000-window random baseline")
    args = ap.parse_args()

    df = load(args.period)
    r = rule_returns(df)
    n, mean, std = len(r), r.mean(), r.std(ddof=1)
    t = mean / (std / np.sqrt(n))
    print(f"=== overnight-drift v1 | period={args.period} ===")
    print(f"trades={n}  GROSS mean={mean:+.2f} bps  median={r.median():+.2f}  "
          f"std={std:.1f}  t={t:+.2f}  ann.Sharpe(gross)={mean / std * np.sqrt(252):.2f}")
    for m in STRESS:
        cost = ENTRY_SPREAD_BPS * m
        net = mean - cost
        t_net = net / (std / np.sqrt(n))
        print(f"  cost x{m}: spread={cost:.2f} bps -> NET {net:+.2f} bps/trade  "
              f"t={t_net:+.2f}  ann.return~{net * 252 / 1e4:+.1%} (1x notional)")
    by_year = r.groupby(r.index.year).agg(["count", "mean"])
    by_year["net@1x"] = by_year["mean"] - ENTRY_SPREAD_BPS
    print(by_year.round(2))

    if args.baseline:
        rng = np.random.default_rng(3)
        means = random_baseline(df, 1000, 90, rng)
        pct = (means < mean).mean() * 100
        p999 = np.percentile(means, 99.9)
        print(f"\nrandom baseline: {len(means)} windows, mean of means "
              f"{means.mean():+.2f}, p99.9={p999:+.2f}; rule gross {mean:+.2f} "
              f"-> percentile {pct:.2f}%  {'PASS' if mean > p999 else 'FAIL'}")


if __name__ == "__main__":
    main()
