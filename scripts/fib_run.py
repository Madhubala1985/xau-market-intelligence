#!/usr/bin/env python3
"""Run the mechanical Fibonacci-retracement setup through the frozen gate.

Same standard as the other setups: causal harness, spread/slippage cost-stress
grid, frozen classification gate, plus 5-fold walk-forward across all available
regimes on the GC=F data we already have (H1 and M5).

CRITICAL CONTROL: a random-entry Monte-Carlo baseline with IDENTICAL stop/target
geometry (each random trade reuses a Fib trade's stop distance, R-multiple and the
Fib long/short mix, placed at a random bar). If the Fib setup's expectancy is not
clearly outside the random distribution, the Fib LEVELS add nothing over noise.
"""

from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from research.data_loader import load_timeframe                       # noqa: E402
from research.harness import CostModel, run_setup, simulate           # noqa: E402
from research.metrics import compute_metrics                          # noqa: E402
from research.setups._common import day_midnight, utc_day             # noqa: E402
from research.setups.base import EntryIntent, MarketData              # noqa: E402
from research.setups.fibonacci_retracement import FibonacciRetracement  # noqa: E402
from src.data.enums import Direction, Timeframe                       # noqa: E402

SEEDS = 300


def _md(candles, tf):
    return MarketData(by_tf={tf: candles})


def _random_baseline(candles, fib_trades, tf, cost):
    """Monte-Carlo: same count + stop-distance + RR + direction-mix, random bars."""
    if not fib_trades:
        return None
    dists = [abs(t.entry_price - t.stop) for t in fib_trades]
    rrs = [abs(t.target - t.entry_price) / max(abs(t.entry_price - t.stop), 1e-9)
           for t in fib_trades]
    dirs = [t.direction for t in fib_trades]
    n = len(fib_trades)
    lo, hi = 50, len(candles) - 2
    exps = []
    rng = random.Random(12345)
    for _ in range(SEEDS):
        intents = []
        for _k in range(n):
            j = rng.randint(lo, hi)
            d = dirs[rng.randrange(n)]
            dist = dists[rng.randrange(n)]
            rr = rrs[rng.randrange(n)]
            ref = candles[j + 1].open
            if d == Direction.SHORT:
                stop, target = ref + dist, ref - rr * dist
            else:
                stop, target = ref - dist, ref + rr * dist
            intents.append(EntryIntent(
                setup="random", version="v1", day=day_midnight(utc_day(candles[j + 1])),
                direction=d, session="ANY", arm_index=j, arm_time=candles[j].time_utc,
                entry_price=ref, stop=stop, target=target, invalidation_price=stop,
                expiry_index=j + 1, entry_type="MARKET"))
        exps.append(compute_metrics(simulate(intents, candles, cost)).expectancy)
    mu, sd = statistics.fmean(exps), statistics.pstdev(exps)
    return mu, sd, sorted(exps)


def _run_tf(tf: Timeframe):
    candles, rep = load_timeframe(tf)
    print(f"\n{'='*72}\n{tf.value}  {rep.summary()}")
    setup = FibonacciRetracement(exec_timeframe=tf,
                                 swing_strength=3 if tf == Timeframe.H1 else 5)
    res = run_setup(setup, _md(candles, tf))
    m = res.metrics
    print(f"  rules: {setup.rules()}")
    print(f"  TRADES={m.trades}  expectancy={m.expectancy:+.3f}R  PF={m.profit_factor:.2f}  "
          f"win={m.win_rate*100:.1f}%  maxDD={m.max_drawdown_r:.1f}R  "
          f"maxConsecL={m.max_consecutive_losses}")
    print(f"  CLASSIFICATION: {res.classification.value}")
    print(f"  cost-stress expectancy: "
          f"{[f'{s.cost.label}:{s.expectancy:+.3f}' for s in res.sensitivity]}")

    # Walk-forward 5-fold across regimes.
    n = len(candles)
    print("  5-fold walk-forward:")
    for k in range(5):
        seg = candles[n * k // 5: n * (k + 1) // 5]
        fm = run_setup(FibonacciRetracement(exec_timeframe=tf,
                       swing_strength=3 if tf == Timeframe.H1 else 5),
                       _md(seg, tf), cost_grid=()).metrics
        print(f"    fold{k+1} {seg[0].time_utc.date()}..{seg[-1].time_utc.date()}: "
              f"n={fm.trades:>3} exp={fm.expectancy:+.3f}R PF={fm.profit_factor:.2f}")

    # Random-entry baseline (the noise control).
    filled = [t for t in res.results if t.filled]
    base = _random_baseline(candles, filled, tf, CostModel())
    if base:
        mu, sd, dist = base
        worse = sum(1 for x in dist if x >= m.expectancy) / len(dist)
        z = (m.expectancy - mu) / sd if sd > 0 else 0.0
        print(f"  RANDOM baseline ({SEEDS} seeds, matched stop/RR/dir): "
              f"expectancy {mu:+.3f}R ± {sd:.3f}")
        print(f"    Fib z-score vs random = {z:+.2f}  "
              f"(p={worse:.2f} of random runs beat Fib)  -> "
              f"{'DISTINGUISHABLE from noise' if z > 2 else 'INDISTINGUISHABLE from noise'}")


def main() -> int:
    for tf in (Timeframe.H1, Timeframe.M5):
        _run_tf(tf)
    print("\nGate: Proven needs >=100 trades, exp>=+0.10R, PF>=1.30, holds under cost "
          "stress. Fib must ALSO clearly beat the random baseline (z>2).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
