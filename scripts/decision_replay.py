#!/usr/bin/env python3
"""SMC-V2-001 shipping gate: v1 vs v2 head-to-head on real MT5 history.

Fetches real XAU/USD candles (M5/M1/M15/H1/H4/D1) from the MT5 terminal
(read-only) and replays them through the live SMC v1 pipeline and the
SMC v2 day-narrative brain under the conservative fill model of
src/backtest/decision_replay.py. Writes the report + verdict to
reports/runtime/smc_v2_replay.md/.json. NEVER changes live config and
NEVER sends orders.

Usage (Windows MT5 host):
    py -3.12 scripts\\decision_replay.py --days 12
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

from src.backtest.decision_replay import (  # noqa: E402
    DecisionReplay,
    verdict,
)

OUT_DIR = REPO_ROOT / "reports" / "runtime"


def fetch_all(days: int) -> dict:
    try:
        import MetaTrader5  # type: ignore  # noqa: F401
    except Exception as exc:
        raise SystemExit(
            f"ENVIRONMENT_ISSUE: MetaTrader5 not importable "
            f"({exc.__class__.__name__}); run on the Windows MT5 host."
        )
    from src.broker.mt5_data_adapter import MT5DataAdapter
    from src.broker.mt5_settings import load_dotenv_file, load_mt5_settings
    from src.data.enums import Timeframe

    load_dotenv_file(str(REPO_ROOT / ".env"))
    adapter = MT5DataAdapter(load_mt5_settings())
    adapter.connect()
    counts = {
        "m5": days * 288 + 300,
        "m1": days * 1440 + 600,
        "m15": days * 96 + 200,
        "h1": days * 24 + 100,
        "h4": days * 6 + 60,
        "daily": days + 30,
    }
    frames = {
        "m5": Timeframe.M5, "m1": Timeframe.M1, "m15": Timeframe.M15,
        "h1": Timeframe.H1, "h4": Timeframe.H4, "daily": Timeframe.D1,
    }
    out = {}
    try:
        for key, tf in frames.items():
            out[key] = adapter.fetch_candles(tf, counts[key])
            print(f"fetched {key}: {len(out[key])} candles "
                  f"({out[key][0].time_utc} .. {out[key][-1].time_utc})")
    finally:
        adapter.shutdown()
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=12)
    parser.add_argument("--symbol", default=None)
    args = parser.parse_args()

    data = fetch_all(args.days)
    symbol = args.symbol or data["m5"][-1].symbol

    from src.strategy.smc_execution import make_smc_pipeline
    from src.strategy.smc_v2 import make_smc_v2_pipeline

    canonical = symbol.strip().upper()
    pipelines = {
        "v1_smc_challenge": make_smc_pipeline(canonical),
        "v2_day_narrative": make_smc_v2_pipeline(canonical),
    }
    replay = DecisionReplay(
        data["m5"], m1=data["m1"], m15=data["m15"], h1=data["h1"],
        h4=data["h4"], daily=data["daily"], symbol=canonical,
        warmup=290,
    )
    print(f"replaying {len(data['m5']) - 290} M5 steps through "
          f"{len(pipelines)} pipelines ...")
    results = replay.run(pipelines)
    v1 = results["v1_smc_challenge"]
    v2 = results["v2_day_narrative"]
    gate = verdict(v1, v2)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "days_requested": args.days,
        "symbol": canonical,
        "fill_model": "entry next open, spread+0.30 slippage, SL-first, "
                      "BE at 1R",
        "v1": v1.summary(),
        "v2": v2.summary(),
        "verdict": gate,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "smc_v2_replay.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    lines = [
        "# SMC v2 Replay Verdict (SMC-V2-001)",
        "",
        f"- generated: {report['generated_at_utc']}",
        f"- symbol: {canonical}; days: {args.days}; fill model: "
        f"{report['fill_model']}",
        "",
        "| metric | v1 smc_challenge | v2 day_narrative |",
        "|--------|------------------|------------------|",
    ]
    for key in ("trades", "wins", "losses", "breakevens", "net_r",
                "win_rate", "max_drawdown_r"):
        lines.append(
            f"| {key} | {report['v1'][key]} | {report['v2'][key]} |"
        )
    lines += ["", "## Per-day net R", "", "| day | v1 | v2 |", "|---|---|---|"]
    all_days = sorted(set(report["v1"]["by_day"]) | set(report["v2"]["by_day"]))
    for d in all_days:
        lines.append(
            f"| {d} | {report['v1']['by_day'].get(d, 0.0):+.2f} "
            f"| {report['v2']['by_day'].get(d, 0.0):+.2f} |"
        )
    lines += ["", "## Verdict", ""]
    lines += [f"- {r}" for r in gate["reasons"]]
    lines.append(
        f"\n**SHIP: {'YES' if gate['ship'] else 'NO'}** — v2 may "
        + ("now be enabled behind --profile smc_v2."
           if gate["ship"] else
           "NOT trade live; iterate on the brain or stay on v1.")
    )
    (OUT_DIR / "smc_v2_replay.md").write_text("\n".join(lines) + "\n",
                                              encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
