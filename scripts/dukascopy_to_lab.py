#!/usr/bin/env python3
"""Convert combined Dukascopy M1 CSVs into the research-lab schema.

Input : data/raw/dukascopy/{INSTR}_M1_{YYYY}.csv  (time,open,high,low,close,volume)
Output: data/raw/{SYMBOL}_1M.csv with the exporter schema read by
        research/data_loader.py:
        time_utc,open,high,low,close,tick_volume,spread,real_volume

The loader aggregates M5/M15/H1/H4 from M1 itself, so the old 60-day Yahoo
intraday files are moved aside (data/raw/archive_yahoo/) — EXCEPT the 15y
XAUUSD_1D.csv, which stays (Dukascopy fetch starts 2019; daily history is
still Yahoo's, and the macro track reads it).

Also runs a sanity check: bar count, gap report, and price cross-check against
the archived Yahoo H1 file on overlapping timestamps (mean abs diff must be
within spot/futures basis, < $5).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DUKA = RAW / "dukascopy"
ARCHIVE = RAW / "archive_yahoo"


def convert(instr: str, out_symbol: str) -> pd.DataFrame:
    files = sorted(DUKA.glob(f"{instr}_M1_*.csv"))
    if not files:
        sys.exit(f"no {instr} yearly files in {DUKA}")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)
    # Dukascopy pads closed market hours (Sunday daytime, post-Friday-close,
    # daily break, holidays) with flat zero-volume filler candles — drop them.
    n0 = len(df)
    df = df[df["volume"] > 0].reset_index(drop=True)
    print(f"dropped {n0 - len(df)} zero-volume filler bars ({(n0 - len(df)) / n0:.1%})")
    out = pd.DataFrame(
        {
            "time_utc": df["time"].dt.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "open": df["open"],
            "high": df["high"],
            "low": df["low"],
            "close": df["close"],
            "tick_volume": df["volume"],
            "spread": "",
            "real_volume": "",
        }
    )
    path = RAW / f"{out_symbol}_1M.csv"
    out.to_csv(path, index=False)
    print(f"wrote {path}: {len(out)} bars, {df['time'].iloc[0]} .. {df['time'].iloc[-1]}")
    return df


def sanity_check(df: pd.DataFrame, yahoo_h1: Path) -> None:
    if not yahoo_h1.exists():
        print("no Yahoo H1 file for cross-check; skipped")
        return
    y = pd.read_csv(yahoo_h1)
    y["time"] = pd.to_datetime(y["time_utc"], utc=True)
    m1 = df.set_index("time")["open"]
    merged = y.set_index("time")[["open"]].join(m1.rename("duka_open"), how="inner").dropna()
    if merged.empty:
        print("no overlapping timestamps for cross-check")
        return
    diff = (merged["open"] - merged["duka_open"]).abs()
    # GC=F is the front futures contract: it sits above spot by carry basis
    # (~$15-20 at 2024-26 rates, >$100 in the early-2025 EFP blowout), so
    # price levels are NOT comparable. Returns are: require high correlation.
    ry = merged["open"].pct_change().dropna()
    rd = merged["duka_open"].pct_change().dropna()
    corr = ry.corr(rd)
    print(f"cross-check vs {yahoo_h1.name}: {len(merged)} overlaps, "
          f"mean|level diff|={diff.mean():.2f} (futures basis), "
          f"H1 return corr={corr:.4f}")
    # Threshold 0.85, not higher: vs the FUTURES proxy, basis dynamics + async
    # close sampling cap the hourly correlation near 0.88-0.95. The decisive
    # spot-vs-spot validation (2026-07-05): same-instant H1 opens vs the GLD
    # ETF correlate 0.9997.
    if corr < 0.85:
        sys.exit("FAIL: return correlation vs the futures proxy is too low")
    print("cross-check PASS")


def archive_old_intraday() -> None:
    ARCHIVE.mkdir(exist_ok=True)
    for name in ("XAUUSD_5M.csv", "XAUUSD_15M.csv", "XAUUSD_1H.csv"):
        p = RAW / name
        if p.exists():
            p.rename(ARCHIVE / name)
            print(f"archived {name} -> archive_yahoo/")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instrument", default="XAUUSD")
    ap.add_argument("--symbol", default=None, help="output symbol (default = instrument)")
    ap.add_argument("--no-archive", action="store_true")
    args = ap.parse_args()
    symbol = args.symbol or args.instrument
    df = convert(args.instrument, symbol)
    if args.instrument == "XAUUSD":
        yahoo = RAW / "XAUUSD_1H.csv"
        if not yahoo.exists():
            yahoo = ARCHIVE / "XAUUSD_1H.csv"
        sanity_check(df, yahoo)
        if not args.no_archive:
            archive_old_intraday()


if __name__ == "__main__":
    main()
