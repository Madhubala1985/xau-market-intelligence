#!/usr/bin/env python3
"""Systematic edge scan: does ANY simple condition predict gold's direction?

Decouples SIGNAL from trade management. For each candidate condition we measure
the forward return (normalized by ATR, so it reads in R-like units) at several
horizons, aggregated over the whole sample. If a condition has no directional
forward edge, no stop/target tuning can make it profitable — that directly tests
the "maybe the stops are the problem" hypothesis.

Conditions are STANDARD and low-degrees-of-freedom (Donchian, EMA trend, Bollinger
mean-reversion, RSI extremes, big-bar continuation/reversion) on purpose: the goal
is to find a real edge, not to overfit bespoke thresholds to one sample. Run on
the 2-year H1 dataset (large sample) and the 60-day M5 dataset.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from research.data_loader import load_timeframe  # noqa: E402
from src.data.enums import Timeframe  # noqa: E402


def _frame(tf: Timeframe) -> pd.DataFrame:
    candles, report = load_timeframe(tf)
    print(report.summary())
    return pd.DataFrame({
        "time": [c.time_utc for c in candles],
        "open": [c.open for c in candles],
        "high": [c.high for c in candles],
        "low": [c.low for c in candles],
        "close": [c.close for c in candles],
    })


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _signals(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Each value is +1 (long), -1 (short), or 0 (no signal) per bar."""
    c = df["close"]
    ema20, ema50 = c.ewm(span=20).mean(), c.ewm(span=50).mean()
    hi20, lo20 = df["high"].rolling(20).max(), df["low"].rolling(20).min()
    sma20 = c.rolling(20).mean()
    std20 = c.rolling(20).std()
    rsi = _rsi(c, 14)
    atr = _atr(df, 14)
    ret1 = c.diff()

    sig = {}
    # Trend / momentum
    sig["donchian20_breakout"] = np.sign((c > hi20.shift(1)).astype(int)
                                         - (c < lo20.shift(1)).astype(int))
    sig["ema20_over_50"] = np.sign((ema20 > ema50).astype(int) - (ema20 < ema50).astype(int))
    sig["price_over_ema50"] = np.sign((c > ema50).astype(int) - (c < ema50).astype(int))
    sig["big_bar_continuation"] = np.where(ret1 > 1.5 * atr, 1,
                                   np.where(ret1 < -1.5 * atr, -1, 0))
    # Mean reversion
    sig["bollinger_revert"] = np.where(c < sma20 - 2 * std20, 1,
                                np.where(c > sma20 + 2 * std20, -1, 0))
    sig["rsi_extreme_revert"] = np.where(rsi < 30, 1, np.where(rsi > 70, -1, 0))
    sig["big_bar_reversion"] = np.where(ret1 > 1.5 * atr, -1,
                                np.where(ret1 < -1.5 * atr, 1, 0))
    return {k: pd.Series(v, index=df.index).fillna(0) for k, v in sig.items()}


def _study(df: pd.DataFrame, sig: pd.Series, horizons: list[int]) -> dict:
    atr = _atr(df, 14)
    c = df["close"].values
    atrv = atr.values
    s = sig.values
    out = {}
    for h in horizons:
        rr = []
        for i in range(len(c) - h):
            if s[i] == 0 or not np.isfinite(atrv[i]) or atrv[i] <= 0:
                continue
            fwd = (c[i + h] - c[i]) * s[i] / atrv[i]   # directional, in ATR units
            rr.append(fwd)
        if rr:
            arr = np.array(rr)
            out[h] = (len(arr), float(arr.mean()), float(np.median(arr)),
                      float((arr > 0).mean()))
        else:
            out[h] = (0, 0.0, 0.0, 0.0)
    return out


def main() -> int:
    horizons = [4, 8, 24]
    for tf in (Timeframe.H1, Timeframe.M5):
        print(f"\n===== {tf.value} forward-edge scan (horizons in bars: {horizons}) =====")
        df = _frame(tf)
        sigs = _signals(df)
        hdr = "condition".ljust(24) + "".join(
            f"| h{h}: n / meanATR / win ".ljust(26) for h in horizons)
        print(hdr)
        for name, sig in sigs.items():
            res = _study(df, sig, horizons)
            row = name.ljust(24)
            for h in horizons:
                n, mean, _med, win = res[h]
                row += f"| {n:>5} {mean:+.3f} {win*100:4.1f}% ".ljust(26)
            print(row)
    print("\nmeanATR > 0 with win% > ~50 and large n => a real directional edge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
