#!/usr/bin/env python3
"""Measure the REAL venue's XAUUSDm spread at the overnight-drift clock times.

Purpose (reports/research/overnight_drift_protocol.md, conditional path):
the overnight-drift candidate v1 failed its gate at Dukascopy-measured costs
(2.29 bps entry). It re-enters evaluation ONLY if the actual execution venue
(Exness demo) shows all-in round-trip cost <= ~1.3 bps at the rule's entry
(16:50 ET) and exit (18:20 ET). This script takes that measurement.

READ-ONLY: connects to MT5 with the .env demo credentials, samples
symbol_info_tick bid/ask once per second during the two 4-minute windows
around 16:50 ET and 18:20 ET, appends one JSON line per window to
reports/runtime/venue_spread.jsonl, prints a running summary, and exits
after the 18:20 window. NO orders, no positions, no account mutation.

Run on the Windows MT5 host once per weekday evening for ~2 weeks
(or leave running with --loop across days):

    py -3.12 scripts\\measure_venue_spread.py [--loop]

Decision rule after >= 8 sampled days:
    median spread(16:50) + median spread(18:20) <= 2.6 bps total
    (~1.3 bps per side) -> v1 re-enters at protocol criterion 2.
    Otherwise v1 stays dead and this file's job is done.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import statistics
import sys
import time
import zoneinfo
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "runtime" / "venue_spread.jsonl"
NY = zoneinfo.ZoneInfo("America/New_York")
SYMBOL = "XAUUSDm"
WINDOWS = ((16, 48, 16, 52), (18, 18, 18, 22))  # ET sampling windows


def die(msg: str, code: int = 2) -> None:
    print(f"ENVIRONMENT_ISSUE: {msg}")
    sys.exit(code)


def connect():
    if platform.system() != "Windows":
        die("MetaTrader5 is Windows-only; run this on the MT5 host")
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError:
        die("MetaTrader5 package not installed")
    import os
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(ROOT / ".env")
    login = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")
    missing = [k for k, v in (("MT5_LOGIN", login), ("MT5_PASSWORD", password),
                              ("MT5_SERVER", server)) if not v]
    if missing:
        die(f"missing env vars: {', '.join(missing)}")
    if not mt5.initialize(login=int(login), password=password, server=server):
        die(f"mt5.initialize failed: {mt5.last_error()}")
    info = mt5.account_info()
    if info is None or getattr(info, "trade_mode", None) == 0:  # 0 = real
        mt5.shutdown()
        die("account type check failed or REAL account — refusing")
    return mt5


def sample_window(mt5, h0: int, m0: int, h1: int, m1: int) -> dict | None:
    now = dt.datetime.now(NY)
    start = now.replace(hour=h0, minute=m0, second=0, microsecond=0)
    end = now.replace(hour=h1, minute=m1, second=0, microsecond=0)
    if now > end:
        return None
    wait = (start - now).total_seconds()
    if wait > 0:
        print(f"waiting {wait/60:.1f} min until {start:%H:%M} ET ...")
        time.sleep(wait)
    spreads = []
    mt5.symbol_select(SYMBOL, True)
    while dt.datetime.now(NY) < end:
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick and tick.bid > 0 and tick.ask >= tick.bid:
            spreads.append((tick.ask - tick.bid) / tick.bid * 1e4)
        time.sleep(1.0)
    if not spreads:
        return None
    rec = {
        "date_et": dt.datetime.now(NY).date().isoformat(),
        "window_et": f"{h0:02d}:{m0:02d}-{h1:02d}:{m1:02d}",
        "n_ticks": len(spreads),
        "median_bps": round(statistics.median(spreads), 3),
        "p90_bps": round(sorted(spreads)[int(0.9 * len(spreads))], 3),
        "symbol": SYMBOL,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec))
    return rec


def summarize() -> None:
    if not OUT.exists():
        return
    rows = [json.loads(l) for l in OUT.read_text().splitlines() if l.strip()]
    by_win: dict[str, list[float]] = {}
    for r in rows:
        by_win.setdefault(r["window_et"], []).append(r["median_bps"])
    total = 0.0
    for win, meds in sorted(by_win.items()):
        m = statistics.median(meds)
        total += m
        print(f"{win}: {len(meds)} days, median-of-medians {m:.2f} bps")
    if len(by_win) == 2:
        verdict = "RE-ENTER v1 at criterion 2" if total <= 2.6 else "v1 stays DEAD"
        print(f"round-trip estimate: {total:.2f} bps -> {verdict} (bar: 2.6)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true", help="keep running across days")
    ap.add_argument("--summary", action="store_true", help="summarize existing samples and exit")
    args = ap.parse_args()
    if args.summary:
        summarize()
        return
    mt5 = connect()
    try:
        while True:
            now = dt.datetime.now(NY)
            if now.weekday() in (0, 1, 2, 3):  # Mon-Thu evenings
                for h0, m0, h1, m1 in WINDOWS:
                    sample_window(mt5, h0, m0, h1, m1)
            summarize()
            if not args.loop:
                break
            nxt = (now + dt.timedelta(days=1)).replace(hour=16, minute=45)
            time.sleep(max(60.0, (nxt - dt.datetime.now(NY)).total_seconds()))
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
