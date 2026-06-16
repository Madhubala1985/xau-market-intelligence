#!/usr/bin/env python3
"""Export XAU/USD historical candles from MT5 to CSV for the research lab.

RUN THIS ON THE WINDOWS MT5 TERMINAL (the MetaTrader5 package is Windows-only).
It is DATA-FETCH ONLY: it calls copy_rates_* and never any order/trade function.

It writes one CSV per timeframe into data/raw/, with the columns the research
loader expects:

    time_utc, open, high, low, close, tick_volume, spread, real_volume

Usage (in the project venv on Windows):
    python scripts/export_mt5_history.py --years 3
    python scripts/export_mt5_history.py --start 2022-01-01 --end 2025-12-31 \
        --timeframes 5M,15M,1H,4H,1D

Then copy the project's data/raw/*.csv files over to the research environment
(or just commit-exclude and sync them) and run scripts/research_run.py there.

Login: reuses MT5Settings from .env (TRADING_MODE=DEMO). It connects read-only;
no order permissions are touched. Credentials are never printed.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

RAW_DIR = REPO_ROOT / "data" / "raw"
SYMBOL = "XAUUSD"

# Filename token -> MT5 timeframe constant name (resolved at runtime).
_TF = {
    "1M": "TIMEFRAME_M1",
    "5M": "TIMEFRAME_M5",
    "15M": "TIMEFRAME_M15",
    "1H": "TIMEFRAME_H1",
    "4H": "TIMEFRAME_H4",
    "1D": "TIMEFRAME_D1",
}


def _import_mt5():
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ModuleNotFoundError:
        print(
            "MetaTrader5 module not found. This exporter must run on the Windows "
            "MT5 terminal:  pip install MetaTrader5"
        )
        raise SystemExit(3)
    return mt5


def _resolve_symbol(mt5, requested: str) -> str:
    """Return the broker's actual XAU/USD symbol name (handles suffixes)."""
    if mt5.symbol_info(requested) is not None:
        mt5.symbol_select(requested, True)
        return requested
    for s in mt5.symbols_get() or []:
        if "XAU" in s.name.upper() and "USD" in s.name.upper():
            mt5.symbol_select(s.name, True)
            return s.name
    raise SystemExit(f"could not find a XAU/USD symbol (requested {requested!r})")


def _write_csv(token: str, rates) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{SYMBOL}_{token}.csv"
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time_utc", "open", "high", "low", "close",
                    "tick_volume", "spread", "real_volume"])
        for r in rates:
            ts = datetime.fromtimestamp(int(r["time"]), tz=timezone.utc).isoformat()
            w.writerow([
                ts, f"{r['open']:.5f}", f"{r['high']:.5f}", f"{r['low']:.5f}",
                f"{r['close']:.5f}", int(r["tick_volume"]),
                int(r["spread"]) if "spread" in r.dtype.names else "",
                int(r["real_volume"]) if "real_volume" in r.dtype.names else "",
            ])
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Export MT5 XAU/USD history to CSV.")
    ap.add_argument("--years", type=float, default=3.0,
                    help="lookback in years from today (ignored if --start given)")
    ap.add_argument("--start", type=str, default=None, help="YYYY-MM-DD (UTC)")
    ap.add_argument("--end", type=str, default=None, help="YYYY-MM-DD (UTC)")
    ap.add_argument("--timeframes", type=str, default="5M,15M,1H,4H,1D",
                    help="comma list from: " + ",".join(_TF))
    ap.add_argument("--symbol", type=str, default=SYMBOL)
    args = ap.parse_args()

    mt5 = _import_mt5()

    end = (datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
           if args.end else datetime.now(timezone.utc))
    start = (datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
             if args.start else end - timedelta(days=int(args.years * 365)))

    # Connect read-only using the project's MT5 settings (.env). No order perms.
    from src.broker.mt5_settings import load_dotenv_file, load_mt5_settings  # noqa: E402
    load_dotenv_file()
    settings = load_mt5_settings()
    if not mt5.initialize(login=settings.login, password=settings.password,
                          server=settings.server, path=settings.path or None):
        print(f"mt5.initialize failed: {mt5.last_error()}")
        return 4

    try:
        symbol = _resolve_symbol(mt5, args.symbol)
        print(f"symbol: {symbol}  span: {start.date()} -> {end.date()}")
        tokens = [t.strip() for t in args.timeframes.split(",") if t.strip()]
        for token in tokens:
            if token not in _TF:
                print(f"  skip unknown timeframe {token!r}")
                continue
            tf_const = getattr(mt5, _TF[token])
            rates = mt5.copy_rates_range(symbol, tf_const, start, end)
            if rates is None or len(rates) == 0:
                print(f"  {token}: NO DATA ({mt5.last_error()})")
                continue
            path = _write_csv(token, rates)
            print(f"  {token}: {len(rates)} bars -> {path.relative_to(REPO_ROOT)}")
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
