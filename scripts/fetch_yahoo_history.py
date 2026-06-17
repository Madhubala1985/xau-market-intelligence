#!/usr/bin/env python3
"""Fetch real gold history from Yahoo (GC=F) into data/raw/ for the lab.

A PUBLIC-DATA FALLBACK so we can backtest without the Windows MT5 export.
GC=F is COMEX gold futures — a close proxy for XAUUSD spot, NOT identical
(slightly different price/level, session edges, no broker spread, futures roll).
Results here are a first real read; reconfirm on the broker feed via
scripts/export_mt5_history.py when available.

Writes data/raw/XAUUSD_<TF>.csv in the loader's column format. Runs anywhere
with internet (no MetaTrader5 needed).
"""

from __future__ import annotations

import csv
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
SYMBOL = "XAUUSD"
YF_SYMBOL = "GC=F"

# (yahoo interval, yahoo range, our filename token). Yahoo caps: 5m<=60d, 1h<=730d.
PULLS = [
    ("5m", "60d", "5M"),
    ("15m", "60d", "15M"),
    ("1h", "730d", "1H"),
    ("1d", "5y", "1D"),
]


def _fetch(interval: str, rng: str) -> dict:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{YF_SYMBOL}"
           f"?interval={interval}&range={rng}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _write(token: str, ts, q) -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{SYMBOL}_{token}.csv"
    rows = 0
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time_utc", "open", "high", "low", "close",
                    "tick_volume", "spread", "real_volume"])
        for i, t in enumerate(ts):
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            if None in (o, h, l, c):
                continue                       # gap / partial bar -> skip (no fabrication)
            vol = q.get("volume", [None] * len(ts))[i] or 0
            iso = datetime.fromtimestamp(int(t), tz=timezone.utc).isoformat()
            w.writerow([iso, f"{o:.4f}", f"{h:.4f}", f"{l:.4f}", f"{c:.4f}",
                        int(vol), "", ""])
            rows += 1
    print(f"  {token}: {rows} bars -> {path.relative_to(REPO_ROOT)}")
    return rows


def main() -> int:
    print(f"Fetching {YF_SYMBOL} (gold futures proxy for XAUUSD) from Yahoo...")
    for interval, rng, token in PULLS:
        try:
            data = _fetch(interval, rng)
            r = data["chart"]["result"][0]
            _write(token, r["timestamp"], r["indicators"]["quote"][0])
        except Exception as exc:               # noqa: BLE001
            print(f"  {token}: FAILED ({exc.__class__.__name__}: {exc})")
    print("done. NOTE: GC=F is a proxy; reconfirm on the broker feed later.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
