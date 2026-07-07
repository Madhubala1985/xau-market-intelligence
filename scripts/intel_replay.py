#!/usr/bin/env python3
"""GOLD-INTEL-001 replay: the gold_intel engine over Dukascopy M1 history.

Runs the SAME DecisionReplay harness the ship gates have always used
(conservative fills: spread+slippage adverse entry, stop-first intrabar
ambiguity, chassis break-even at +1R) — but fed from the validated 7.5y
Dukascopy M1 archive, so the gate runs in this environment instead of
waiting for Windows MT5 history.

Protocol: reports/research/gold_intel_gate_protocol.md (frozen BEFORE the
gate run). The regime dial is applied CAUSALLY per replay day from the
cached FRED store (as-of, 1-day lag).

Usage:
  python scripts/intel_replay.py --start 2024-03-01 --end 2024-03-28   # one window
  python scripts/intel_replay.py --gate            # the full pre-registered gate
  python scripts/intel_replay.py --holdout         # 2026 holdout (only after PASS)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backtest.decision_replay import DecisionReplay, ReplayResult  # noqa: E402
from src.data.schemas import Candle  # noqa: E402
from src.strategy.gold_intel import GoldIntelEngine, make_gold_intel_pipeline  # noqa: E402
from research.macro_data import asof_join, load_series  # noqa: E402
from research.regime import gold_macro_regime  # noqa: E402

DUKA = ROOT / "data" / "raw" / "dukascopy"
OUT_DIR = ROOT / "reports" / "research"
SYMBOL = "XAUUSD"
REPLAY_SPREAD = 0.50       # gate v1 flat spread (USD) — kept for the record
SPREAD_BPS = 2.2           # gate v2: measured Dukascopy entry spread (bps)
SLIPPAGE_BPS = 1.0         # gate v2: slippage per side (bps)
WARMUP_M5 = 300

# Pre-registered gate windows (protocol file): Mar 1-28 + Sep 1-28, 2019-2025.
GATE_WINDOWS = [(date(y, m, 1), date(y, m, 28))
                for y in range(2019, 2026) for m in (3, 9)]
HOLDOUT_WINDOWS = [(date(2026, m, 1), date(2026, m, 28))
                   for m in (2, 4, 6)]


def load_m1(years) -> pd.DataFrame:
    files = [DUKA / f"{SYMBOL}_M1_{y}.csv" for y in sorted(set(years))]
    df = pd.concat([pd.read_csv(f) for f in files if f.exists()],
                   ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df[df["volume"] > 0].drop_duplicates("time").sort_values("time")
    return df.set_index("time")


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = pd.DataFrame({
        "open": df["open"].resample(rule, label="left", closed="left").first(),
        "high": df["high"].resample(rule, label="left", closed="left").max(),
        "low": df["low"].resample(rule, label="left", closed="left").min(),
        "close": df["close"].resample(rule, label="left", closed="left").last(),
        "volume": df["volume"].resample(rule, label="left", closed="left").sum(),
    }).dropna()
    return out[out["volume"] > 0]


def to_candles(df: pd.DataFrame, tf: str) -> list:
    return [
        Candle(symbol=SYMBOL, timeframe=tf, broker_time=t.to_pydatetime(),
               time_utc=t.to_pydatetime(), open=r.open, high=r.high,
               low=r.low, close=r.close, tick_volume=int(r.volume) or 1)
        for t, r in df.iterrows()
    ]


def regime_map(days) -> dict:
    """Causal daily regime dial from the cached FRED store."""
    days = sorted(days)
    ry_s = load_series("real_yield_10y")
    dx_s = load_series("broad_dollar")
    ry = asof_join(days, ry_s, lag_days=1)
    dx = asof_join(days, dx_s, lag_days=1)
    out = {}
    hist_ry, hist_dx = [], []
    for i, d in enumerate(days):
        if ry[i] is None or dx[i] is None:
            out[d] = (None, "")
            continue
        hist_ry.append(ry[i])
        hist_dx.append(dx[i])
        if len(hist_ry) > 61:
            reading = gold_macro_regime(hist_ry, hist_dx)
            out[d] = (reading.exposure, reading.label)
        else:
            out[d] = (None, "")
    return out


class ReplayIntelEngine(GoldIntelEngine):
    """gold_intel with the regime dial fed causally per replay day."""

    regime_by_date: dict = {}

    def decide(self, inp):
        d = inp.exec_candles[-1].time_utc.date()
        exp, label = self.regime_by_date.get(d, (None, ""))
        self.set_regime(exp, label)
        return super().decide(inp)


def run_window(start: date, end: date, m1_all: pd.DataFrame,
               rmap: dict, *, cost_mode: str = "v2") -> ReplayResult:
    lo = pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=45)  # HTF warmup
    hi = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    m1 = m1_all[(m1_all.index >= lo) & (m1_all.index < hi)]
    m5 = resample(m1, "5min")
    window_start = pd.Timestamp(start, tz="UTC")
    m5_replay = m5[m5.index >= window_start - pd.Timedelta(days=2)]
    engine = ReplayIntelEngine.__new__(ReplayIntelEngine)
    base = make_gold_intel_pipeline(SYMBOL, max_staleness=timedelta(days=3650))
    engine.__dict__ = base.__dict__          # adopt built engine state
    engine.__class__ = ReplayIntelEngine
    engine.regime_by_date = rmap
    costs = {
        "v1": dict(spread=REPLAY_SPREAD),
        "v2": dict(spread=REPLAY_SPREAD, spread_bps=SPREAD_BPS,
                   slippage_bps=SLIPPAGE_BPS),
        "gross": dict(spread=0.0, spread_bps=0.0, slippage_bps=0.0),
    }[cost_mode]
    replay = DecisionReplay(
        to_candles(m5_replay, "M5"),
        m15=to_candles(resample(m1, "15min"), "M15"),
        h1=to_candles(resample(m1, "1h"), "H1"),
        h4=to_candles(resample(m1, "4h"), "H4"),
        daily=to_candles(resample(m1, "1D"), "D1"),
        symbol=SYMBOL, warmup=WARMUP_M5, **costs,
    )
    return replay.run({"gold_intel": engine})["gold_intel"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--holdout", action="store_true")
    ap.add_argument("--cost-mode", default="v2",
                    choices=("v1", "v2", "gross"))
    args = ap.parse_args()

    if args.gate:
        windows, tag = GATE_WINDOWS, f"gate_{args.cost_mode}"
    elif args.holdout:
        windows, tag = HOLDOUT_WINDOWS, f"holdout_{args.cost_mode}"
    else:
        windows = [(date.fromisoformat(args.start),
                    date.fromisoformat(args.end))]
        tag = f"window_{args.start}"

    years = sorted({d.year for w in windows for d in w}
                   | {w[0].year - 1 for w in windows if w[0].month == 1})
    print(f"loading M1 for {years} ...")
    m1_all = load_m1(years + [y - 1 for y in years])
    all_days = sorted({d for w in windows
                       for d in pd.date_range(w[0], w[1]).date})
    rmap = regime_map(all_days)

    rows, all_trades = [], []
    t0 = time.time()
    for start, end in windows:
        res = run_window(start, end, m1_all, rmap, cost_mode=args.cost_mode)
        s = res.summary()
        rows.append({"window": f"{start}..{end}", **{
            k: s[k] for k in ("trades", "wins", "losses", "breakevens",
                              "net_r", "win_rate", "max_drawdown_r")}})
        all_trades.extend(res.closed)
        print(f"  {start}..{end}: trades={s['trades']} net_r={s['net_r']:+.2f}"
              f" dd={s['max_drawdown_r']:.2f} win_rate={s['win_rate']:.2f}"
              f"  [{time.time()-t0:.0f}s]")

    total_r = round(sum(t.r_multiple for t in all_trades), 2)
    n = len(all_trades)
    nonneg = sum(1 for r in rows if r["net_r"] >= 0)
    # pooled max drawdown across windows in sequence
    peak = eq = mdd = 0.0
    for t in all_trades:
        eq += t.r_multiple
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
    report = {
        "tag": tag, "cost_mode": args.cost_mode, "windows": rows,
        "total_trades": n, "total_net_r": total_r,
        "windows_nonnegative": f"{nonneg}/{len(rows)}",
        "pooled_max_dd_r": round(mdd, 2),
    }
    out = OUT_DIR / f"gold_intel_replay_{tag}.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nTOTAL: trades={n} net_r={total_r:+.2f} "
          f"windows>=0: {nonneg}/{len(rows)} pooled_dd={mdd:.2f}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
