#!/usr/bin/env python3
"""Fetch free historical M1 candles from Dukascopy's public datafeed.

Dukascopy serves one LZMA-compressed binary file per instrument per day:
  https://datafeed.dukascopy.com/datafeed/{INSTR}/{YYYY}/{MM0}/{DD}/BID_candles_min_1.bi5
(month is 0-indexed). Each record is 24 bytes big-endian:
  uint32 seconds-since-file-start, uint32 open, uint32 close,
  uint32 low, uint32 high, float32 volume
Prices are ints scaled by the instrument's point value (XAUUSD: 1000).

Writes data/raw/dukascopy/{INSTR}_M1_{YYYY}.csv (UTC timestamps) and a
combined data/raw/{INSTR}_M1_dukascopy.csv on --combine.

Usage:
  python3 scripts/fetch_dukascopy.py --instrument XAUUSD --start 2020-01-01 --end 2026-07-04
  python3 scripts/fetch_dukascopy.py --instrument XAUUSD --combine
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import lzma
import struct
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "raw" / "dukascopy"

BASE = "https://datafeed.dukascopy.com/datafeed/{instr}/{y}/{m:02d}/{d:02d}/BID_candles_min_1.bi5"
REC = struct.Struct(">IIIIIf")  # ts_offset, open, close, low, high, volume

POINT = {
    "XAUUSD": 1000.0,
    "XAGUSD": 1000.0,
    "EURUSD": 100000.0,
    "DOLLARIDXUSD": 1000.0,
    "USA500IDXUSD": 1000.0,
}


def fetch_day(instr: str, day: dt.date, retries: int = 3) -> list[tuple]:
    url = BASE.format(instr=instr, y=day.year, m=day.month - 1, d=day.day)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                raw = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    if not raw:
        return []
    data = lzma.decompress(raw)
    point = POINT.get(instr, 1000.0)
    base_ts = dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc)
    rows = []
    for i in range(0, len(data) - REC.size + 1, REC.size):
        off, o, c, lo, hi, vol = REC.unpack_from(data, i)
        if o == 0:
            continue
        ts = base_ts + dt.timedelta(seconds=off)
        rows.append((ts.isoformat(), o / point, hi / point, lo / point, c / point, round(vol, 4)))
    return rows


def daterange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        # Dukascopy has no Saturday data for FX/metals; skip to cut 404 noise.
        if d.weekday() != 5:
            yield d
        d += dt.timedelta(days=1)


def download(instr: str, start: dt.date, end: dt.date, workers: int = 8) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    days = list(daterange(start, end))
    by_year: dict[int, list[tuple]] = {}
    done = 0
    failed: list[str] = []
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_day, instr, d): d for d in days}
        for fut in cf.as_completed(futs):
            d = futs[fut]
            done += 1
            try:
                rows = fut.result()
                if rows:
                    by_year.setdefault(d.year, []).extend(rows)
            except Exception as e:  # noqa: BLE001
                failed.append(f"{d}: {e}")
            if done % 200 == 0:
                rate = done / (time.time() - t0)
                print(f"  {done}/{len(days)} days ({rate:.1f}/s, {len(failed)} failed)", flush=True)
    for year, rows in sorted(by_year.items()):
        rows.sort()
        path = OUT_DIR / f"{instr}_M1_{year}.csv"
        with path.open("w") as f:
            f.write("time,open,high,low,close,volume\n")
            for r in rows:
                f.write(",".join(str(x) for x in r) + "\n")
        print(f"wrote {path} ({len(rows)} bars)", flush=True)
    if failed:
        print(f"FAILED days ({len(failed)}):", *failed[:20], sep="\n  ", flush=True)


def combine(instr: str) -> None:
    files = sorted(OUT_DIR.glob(f"{instr}_M1_*.csv"))
    if not files:
        sys.exit(f"no yearly files for {instr} in {OUT_DIR}")
    out = ROOT / "data" / "raw" / f"{instr}_M1_dukascopy.csv"
    with out.open("w") as fo:
        fo.write("time,open,high,low,close,volume\n")
        for fp in files:
            with fp.open() as fi:
                next(fi)
                for line in fi:
                    fo.write(line)
    print(f"wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instrument", default="XAUUSD")
    ap.add_argument("--start", type=dt.date.fromisoformat, default=dt.date(2020, 1, 1))
    ap.add_argument("--end", type=dt.date.fromisoformat, default=dt.date.today())
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--combine", action="store_true", help="merge yearly CSVs, skip download")
    args = ap.parse_args()
    if args.combine:
        combine(args.instrument)
    else:
        download(args.instrument, args.start, args.end, args.workers)


if __name__ == "__main__":
    main()
