#!/usr/bin/env python3
"""Calibrate Donchian-breakout EXITS on H1, with a train/test split.

The breakout SIGNAL edge is already established (scripts/edge_scan.py, 2y H1).
Here we only calibrate exits (stop/target/time-stop) over a SMALL standard grid,
fit on the first 70% of H1 history (in-sample) and confirmed on the last 30%
(out-of-sample). A config is only worth keeping if it is positive on BOTH —
that is the guard against curve-fitting to one slice.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from research.data_loader import load_timeframe  # noqa: E402
from research.harness import CostModel, run_setup  # noqa: E402
from research.setups.base import MarketData  # noqa: E402
from research.setups.donchian_breakout_trend import DonchianBreakoutTrend  # noqa: E402
from src.data.enums import Timeframe  # noqa: E402

# Each variant: label + kwargs for DonchianBreakoutTrend. Small, standard grid.
# Tests the bare breakout vs regime-filtered variants (trend-EMA align, ATR
# high-vol state). The question: does a regime gate make the edge STATIONARY
# (positive in BOTH train and test)?
GRID = [
    ("bare 2/2",          dict(stop_atr=2.0, tp_atr=2.0)),
    ("bare 2/2 hold24",   dict(stop_atr=2.0, tp_atr=2.0, max_hold_bars=24)),
    ("ema100 2/2",        dict(stop_atr=2.0, tp_atr=2.0, trend_filter_ema=100)),
    ("ema100 2/4",        dict(stop_atr=2.0, tp_atr=4.0, trend_filter_ema=100)),
    ("atrvol50 2/2",      dict(stop_atr=2.0, tp_atr=2.0, atr_regime_lookback=200,
                               atr_regime_min_pctile=0.5)),
    ("ema100+atrvol 2/4", dict(stop_atr=2.0, tp_atr=4.0, trend_filter_ema=100,
                               atr_regime_lookback=200, atr_regime_min_pctile=0.5)),
    ("ema200 2/4 hold24", dict(stop_atr=2.0, tp_atr=4.0, trend_filter_ema=200,
                               max_hold_bars=24)),
]


def _slice_md(h1, lo, hi) -> MarketData:
    return MarketData(by_tf={Timeframe.H1: h1[lo:hi]})


def main() -> int:
    h1, report = load_timeframe(Timeframe.H1)
    print(report.summary())
    n = len(h1)
    split = int(n * 0.70)
    train, test = _slice_md(h1, 0, split), _slice_md(h1, split, n)
    cost = CostModel()

    print(f"\nH1 bars: {n}  train: 0..{split}  test: {split}..{n}")
    print(f"{'variant':<20} | TRAIN: n exp win PF | TEST: n exp win PF | verdict")
    print("-" * 80)
    for label, kw in GRID:
        setup = DonchianBreakoutTrend(**kw)
        rtr = run_setup(setup, train, base_cost=cost, cost_grid=())
        rte = run_setup(setup, test, base_cost=cost, cost_grid=())
        mtr, mte = rtr.metrics, rte.metrics
        ok = "KEEP" if (mtr.expectancy > 0 and mte.expectancy > 0) else "drop"
        print(f"{label:<20} | {mtr.trades:>4} {mtr.expectancy:+.3f} {mtr.win_rate*100:4.1f}% "
              f"{mtr.profit_factor:4.2f} | "
              f"{mte.trades:>4} {mte.expectancy:+.3f} {mte.win_rate*100:4.1f}% "
              f"{mte.profit_factor:4.2f} | {ok}")
    print("\nKEEP = positive expectancy in BOTH train and test (survives OOS).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
