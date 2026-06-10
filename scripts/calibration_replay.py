#!/usr/bin/env python3
"""BACKTEST-001 readiness: replay threshold variants on XAUUSDm history.

Measures how the graded-gate thresholds (chop-override confluence,
continuation confluence, continuation displacement) would have behaved on
real historical M5 candles, and writes a comparison report with a
recommendation. It NEVER changes live configuration.

Data sources (choose one):
  --fetch          fetch M5 candles from the MT5 terminal (Windows host;
                   uses the .env account read-only; default 4000 candles)
  --file PATH      read candles from a JSONL file with lines like
                   {"time_utc": "...", "open": .., "high": .., "low": ..,
                    "close": .., "tick_volume": ..}

Output: reports/runtime/calibration.md + .json

Usage (Windows MT5 host, PowerShell):
    py -3.12 scripts\\calibration_replay.py --fetch
    py -3.12 scripts\\calibration_replay.py --file data\\processed\\xauusd_m5.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.backtest.calibration import (  # noqa: E402
    DEFAULT_VARIANTS,
    ThresholdCalibrator,
)
from src.data.schemas import Candle  # noqa: E402

OUT_DIR = REPO_ROOT / "reports" / "runtime"


def load_file(path: Path) -> list:
    candles = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        t = datetime.fromisoformat(row["time_utc"])
        candles.append(Candle(
            symbol=str(row.get("symbol", "XAUUSD")), timeframe="5M",
            broker_time=t, time_utc=t,
            open=row["open"], high=row["high"], low=row["low"],
            close=row["close"], tick_volume=int(row.get("tick_volume", 0)),
        ))
    return candles


def fetch_mt5(count: int) -> list:
    try:
        import MetaTrader5  # type: ignore  # noqa: F401
    except Exception as exc:
        raise SystemExit(
            f"ENVIRONMENT_ISSUE: MetaTrader5 not importable "
            f"({exc.__class__.__name__}); use --file off-Windows."
        )
    from src.broker.mt5_data_adapter import MT5DataAdapter
    from src.broker.mt5_settings import load_mt5_settings, load_dotenv_file
    from src.data.enums import Timeframe

    load_dotenv_file(str(REPO_ROOT / ".env"))
    adapter = MT5DataAdapter(load_mt5_settings())
    adapter.connect()
    try:
        return adapter.fetch_candles(Timeframe.M5, count)
    finally:
        adapter.shutdown()


def render(report) -> str:
    lines = ["# Threshold Calibration Replay (BACKTEST-001 readiness)", ""]
    lines.append(f"- Recommended: **{report.recommended or 'n/a'}**")
    lines.append(f"- Detail: {report.detail}")
    lines.append("")
    lines.append("| variant | windows | actionable | approved | W/L/T | "
                 "win rate | expectancy (R) | near misses |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in report.results:
        lines.append(
            f"| {r.variant.name} | {r.windows} | {r.actionable} | "
            f"{r.approved} | {r.wins}/{r.losses}/{r.timeouts} | "
            f"{r.win_rate:.0%} | {r.expectancy_r:.2f} | {r.near_misses} |"
        )
    lines += [
        "",
        "Recommendation only: live thresholds are never mutated by this tool;",
        "apply changes via a reviewed task with walk-forward validation.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true",
                        help="fetch M5 candles from MT5 (Windows host)")
    parser.add_argument("--count", type=int, default=4000)
    parser.add_argument("--file", type=Path, default=None,
                        help="JSONL candle file (off-host replay)")
    parser.add_argument("--out", default="calibration")
    args = parser.parse_args()

    if args.fetch:
        candles = fetch_mt5(args.count)
    elif args.file is not None:
        if not args.file.is_file():
            print(f"FAIL: file not found: {args.file}")
            return 2
        candles = load_file(args.file)
    else:
        print("FAIL: choose a data source: --fetch (Windows) or --file PATH")
        return 2

    report = ThresholdCalibrator().run(candles, DEFAULT_VARIANTS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["generated_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    payload["candles"] = len(candles)
    (OUT_DIR / f"{args.out}.md").write_text(render(report), encoding="utf-8")
    (OUT_DIR / f"{args.out}.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Candles: {len(candles)}  Recommended: {report.recommended or 'n/a'}")
    print(f"Wrote reports/runtime/{args.out}.md and .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
