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

# (stop_atr, tp_atr, max_hold_bars). Small, standard grid — low overfit surface.
GRID = [
    (1.5, 1.5, None),
    (2.0, 2.0, None),
    (1.5, 3.0, None),
    (2.0, 2.0, 24),
    (1.5, 6.0, 24),     # wide target + time stop: harvest the measured drift
    (2.0, 6.0, 48),
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
    print("stop tp  hold | TRAIN: n exp win  PF | TEST: n exp win  PF | verdict")
    print("-" * 78)
    for stop_atr, tp_atr, hold in GRID:
        setup = DonchianBreakoutTrend(stop_atr=stop_atr, tp_atr=tp_atr, max_hold_bars=hold)
        rtr = run_setup(setup, train, base_cost=cost, cost_grid=())
        rte = run_setup(setup, test, base_cost=cost, cost_grid=())
        mtr, mte = rtr.metrics, rte.metrics
        ok = "KEEP" if (mtr.expectancy > 0 and mte.expectancy > 0) else "drop"
        print(f"{stop_atr:<4} {tp_atr:<3} {str(hold):<4} | "
              f"{mtr.trades:>4} {mtr.expectancy:+.3f} {mtr.win_rate*100:4.1f}% "
              f"{mtr.profit_factor:4.2f} | "
              f"{mte.trades:>4} {mte.expectancy:+.3f} {mte.win_rate*100:4.1f}% "
              f"{mte.profit_factor:4.2f} | {ok}")
    print("\nKEEP = positive expectancy in BOTH train and test (survives OOS).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
