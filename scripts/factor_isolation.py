#!/usr/bin/env python3
"""Single-factor isolation battery — does any SMC factor beat noise on its own?

Runs each factor (FVG, liquidity sweep, displacement, CHOCH, order block,
supply/demand) through the frozen RESEARCH-LAB gate on GC=F H1, walk-forward
(5 folds) + cost-stress, against a random-entry baseline with identical
stop/target/RR/direction mix.

Multiple-comparisons discipline: 6 factors tested -> Bonferroni alpha = 0.05/6 =
0.0083 -> one-sided z threshold ~ 2.39. A factor is a HIT only if it (a) clears
the gate as a Proven Edge Candidate, (b) beats the random baseline at the
corrected z>=2.39, AND (c) REPLICATES: positive expectancy in an untouched
holdout fold (the most recent fold). Anything less is reported but is NOT a hit.
"""

from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from research.data_loader import load_timeframe                  # noqa: E402
from research.harness import CostModel, run_setup, simulate      # noqa: E402
from research.metrics import Classification, compute_metrics     # noqa: E402
from research.setups._common import day_midnight, utc_day        # noqa: E402
from research.setups.base import EntryIntent, MarketData         # noqa: E402
from research.setups.single_factor import FACTORS, SingleFactorSetup  # noqa: E402
from src.data.enums import Direction, Timeframe                  # noqa: E402

SEEDS = 300
N_TESTS = len(FACTORS)
Z_BONFERRONI = 2.39   # one-sided, alpha = 0.05 / 6


def _md(candles, tf):
    return MarketData(by_tf={tf: candles})


def _random_baseline(candles, trades, tf, cost):
    if not trades:
        return 0.0, 0.0
    dists = [abs(t.entry_price - t.stop) for t in trades]
    rrs = [abs(t.target - t.entry_price) / max(abs(t.entry_price - t.stop), 1e-9) for t in trades]
    dirs = [t.direction for t in trades]
    n, lo, hi = len(trades), 50, len(candles) - 2
    rng = random.Random(2026)
    exps = []
    for _ in range(SEEDS):
        intents = []
        for _k in range(n):
            j = rng.randint(lo, hi)
            d = dirs[rng.randrange(n)]
            dist = dists[rng.randrange(n)]
            rr = rrs[rng.randrange(n)]
            ref = candles[j + 1].open
            stop = ref + dist if d == Direction.SHORT else ref - dist
            target = ref - rr * dist if d == Direction.SHORT else ref + rr * dist
            intents.append(EntryIntent(
                setup="rand", version="v1", day=day_midnight(utc_day(candles[j + 1])),
                direction=d, session="ANY", arm_index=j, arm_time=candles[j].time_utc,
                entry_price=ref, stop=stop, target=target, invalidation_price=stop,
                expiry_index=j + 1, entry_type="MARKET"))
        exps.append(compute_metrics(simulate(intents, candles, cost)).expectancy)
    return statistics.fmean(exps), statistics.pstdev(exps)


def main() -> int:
    tf = Timeframe.H1
    candles, rep = load_timeframe(tf)
    print(rep.summary())
    n = len(candles)
    holdout_lo = 4 * n // 5            # last fold = untouched replication holdout

    print(f"\nSingle-factor isolation on {tf.value}  (Bonferroni z>={Z_BONFERRONI}, "
          f"holdout = last fold {candles[holdout_lo].time_utc.date()}..{candles[-1].time_utc.date()})\n")
    hdr = (f"{'factor':<16} {'n':>5} {'exp':>8} {'PF':>6} {'maxDD':>7} "
           f"{'z_rand':>7} {'holdout_exp':>11} {'gate':<20} HIT")
    print(hdr); print("-" * len(hdr))

    for factor in FACTORS:
        res = run_setup(SingleFactorSetup(factor, exec_timeframe=tf), _md(candles, tf))
        m = res.metrics
        filled = [t for t in res.results if t.filled]
        mu, sd = _random_baseline(candles, filled, tf, CostModel())
        z = (m.expectancy - mu) / sd if sd > 0 else 0.0
        hold = run_setup(SingleFactorSetup(factor, exec_timeframe=tf),
                         _md(candles[holdout_lo:], tf), cost_grid=()).metrics
        proven = res.classification is Classification.PROVEN_EDGE_CANDIDATE
        hit = proven and z >= Z_BONFERRONI and hold.expectancy > 0
        print(f"{factor:<16} {m.trades:>5} {m.expectancy:>+8.3f} {m.profit_factor:>6.2f} "
              f"{m.max_drawdown_r:>6.1f}R {z:>+7.2f} {hold.expectancy:>+11.3f} "
              f"{res.classification.value:<20} {'YES' if hit else 'no'}")

    print(f"\nHIT requires: gate=Proven Edge Candidate AND z>={Z_BONFERRONI} (Bonferroni "
          f"for {N_TESTS} tests) AND positive expectancy in the untouched holdout fold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
