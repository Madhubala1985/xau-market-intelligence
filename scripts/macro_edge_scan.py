#!/usr/bin/env python3
"""Does the real-yield / dollar REGIME predict forward gold returns?

The textbook gold thesis: gold rises when real yields fall and/or the dollar
falls. We test it honestly:
  1. Forward-return study by regime (is gold's forward return higher in the
     "easing" regime than the "tightening" one?), reported per multi-year fold.
  2. A long/flat regime strategy vs buy-and-hold (Sharpe, total return, maxDD),
     per fold and full — the tradeable question, net of a switch cost.

Causality: regimes use macro known STRICTLY BEFORE the gold bar (as-of join with
a publication lag). Daily horizon.
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from research.data_loader import load_timeframe          # noqa: E402
from research.macro_data import build_panel               # noqa: E402
from src.data.enums import Timeframe                       # noqa: E402


def _trend_sign(vals, i, n):
    """+1 if series rose over the last n steps, -1 if fell, 0 if flat/unknown."""
    if i < n or vals[i] is None or vals[i - n] is None:
        return 0
    d = vals[i] - vals[i - n]
    return 1 if d > 0 else (-1 if d < 0 else 0)


def _sharpe(daily):
    if len(daily) < 2:
        return 0.0
    sd = statistics.pstdev(daily)
    return (statistics.fmean(daily) / sd * (252 ** 0.5)) if sd > 0 else 0.0


def _max_dd(daily):
    peak = cum = mdd = 0.0
    for r in daily:
        cum += r
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return mdd


def main() -> int:
    d1, rep = load_timeframe(Timeframe.D1)
    print(rep.summary())
    dates = [c.time_utc.date() for c in d1]
    closes = [c.close for c in d1]
    panel, names = build_panel(dates, lag_days=1)
    ry, dx = panel["real_yield_10y"], panel["broad_dollar"]

    # Daily log-ish returns (close-to-close, in %).
    ret = [0.0] + [(closes[i] / closes[i - 1] - 1.0) for i in range(1, len(closes))]

    N = 20  # regime lookback (trend of yields/dollar over ~1 month)
    # "easing" (gold-bullish) when BOTH real yield and dollar are falling.
    easing, tightening, mixed = [], [], []   # collect NEXT-day returns by regime
    long_flat = []        # strategy daily return: long gold only in easing regime
    bh = []               # buy & hold
    switch_cost = 0.0002  # 2 bps per regime switch (round-trip-ish, conservative)
    prev_pos = 0
    valid_idx = []
    for i in range(N, len(closes) - 1):
        ys, ds = _trend_sign(ry, i, N), _trend_sign(dx, i, N)
        if ys == 0 or ds == 0:
            continue
        fwd = ret[i + 1]                      # tomorrow's gold return (causal)
        valid_idx.append(i)
        if ys < 0 and ds < 0:
            easing.append(fwd)
        elif ys > 0 and ds > 0:
            tightening.append(fwd)
        else:
            mixed.append(fwd)
        # Strategy: hold gold UNLESS both yields and dollar are rising
        # (tightening is the only regime that kills gold's drift).
        pos = 0 if (ys > 0 and ds > 0) else 1
        r = pos * fwd - (switch_cost if pos != prev_pos else 0.0)
        long_flat.append(r); bh.append(fwd); prev_pos = pos

    def stat(name, xs):
        if not xs:
            print(f"  {name:<12} n=0"); return
        wr = sum(1 for x in xs if x > 0) / len(xs)
        print(f"  {name:<12} n={len(xs):>4}  mean={statistics.fmean(xs)*100:+.4f}%/day  "
              f"win={wr*100:4.1f}%  ann={statistics.fmean(xs)*252*100:+.1f}%")

    print(f"\n=== Forward 1-day gold return by macro regime (N={N}, lag=1d) ===")
    stat("EASING", easing)        # yields & dollar both falling -> expect best
    stat("MIXED", mixed)
    stat("TIGHTENING", tightening)

    print(f"\n=== Long-in-easing-regime strategy vs buy&hold ===")
    print(f"  strategy: ann={statistics.fmean(long_flat)*252*100:+.1f}%  "
          f"Sharpe={_sharpe(long_flat):.2f}  maxDD={_max_dd(long_flat)*100:.1f}%  "
          f"days_long={sum(1 for x,b in zip(long_flat,bh) if x!=0 or x==b)}")
    print(f"  buy&hold: ann={statistics.fmean(bh)*252*100:+.1f}%  "
          f"Sharpe={_sharpe(bh):.2f}  maxDD={_max_dd(bh)*100:.1f}%")

    # Multi-fold robustness (the gate that killed the price setups).
    print(f"\n=== 5-fold robustness (strategy Sharpe & ann return) ===")
    F = 5
    n = len(long_flat)
    for k in range(F):
        lo, hi = n * k // F, n * (k + 1) // F
        seg, bseg = long_flat[lo:hi], bh[lo:hi]
        di = valid_idx[lo]
        print(f"  fold{k+1} {dates[di]}..{dates[valid_idx[hi-1]]}: "
              f"strat ann={statistics.fmean(seg)*252*100:+6.1f}% Sh={_sharpe(seg):4.2f} | "
              f"B&H ann={statistics.fmean(bseg)*252*100:+6.1f}% Sh={_sharpe(bseg):4.2f}")
    print("\nEdge exists only if EASING >> TIGHTENING consistently AND the "
          "strategy beats buy&hold on Sharpe across folds (not just recently).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
