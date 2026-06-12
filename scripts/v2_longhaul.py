#!/usr/bin/env python3
"""SMC-V2-001 long-horizon edge hunt: months of real history, monthly
expectancy breakdown. The question this answers: does ANY v2 doctrine
configuration hold a persistent edge across regimes — the only kind of
edge that can compound $2k toward the campaign goal. Read-only.

Usage (Windows MT5 host):
    py -3.12 scripts\\v2_longhaul.py --m5 50000
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.backtest.decision_replay import DecisionReplay  # noqa: E402

OUT_DIR = REPO_ROOT / "reports" / "runtime"

CANDIDATES = {
    "defaults": dict(),
    "cap2_bar70_t3": dict(quality_bar=0.70, trend_target_r=3.0,
                          max_entries_per_day=2),
    "bar62_t3_struct": dict(quality_bar=0.62, trend_target_r=3.0,
                            structural_stops_only=True),
}


def fetch(m5_count: int) -> dict:
    try:
        import MetaTrader5  # type: ignore  # noqa: F401
    except Exception as exc:
        raise SystemExit(f"ENVIRONMENT_ISSUE: {exc.__class__.__name__}")
    from src.broker.mt5_data_adapter import MT5DataAdapter
    from src.broker.mt5_settings import load_dotenv_file, load_mt5_settings
    from src.data.enums import Timeframe

    load_dotenv_file(str(REPO_ROOT / ".env"))
    adapter = MT5DataAdapter(load_mt5_settings())
    adapter.connect()
    plan = {
        "m5": (Timeframe.M5, m5_count),
        "m15": (Timeframe.M15, m5_count // 3 + 200),
        "h1": (Timeframe.H1, m5_count // 12 + 100),
        "h4": (Timeframe.H4, m5_count // 48 + 60),
        "daily": (Timeframe.D1, m5_count // 288 + 40),
    }
    out = {}
    try:
        for key, (tf, count) in plan.items():
            try:
                out[key] = adapter.fetch_candles(tf, count)
            except Exception:
                # broker history limit: take what exists, never fabricate
                out[key] = adapter.fetch_candles(tf, count // 2)
            print(f"fetched {key}: {len(out[key])} "
                  f"({out[key][0].time_utc:%Y-%m-%d} .. "
                  f"{out[key][-1].time_utc:%Y-%m-%d})")
    finally:
        adapter.shutdown()
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--m5", type=int, default=50000)
    args = parser.parse_args()

    data = fetch(args.m5)
    from src.strategy.smc_v2 import make_smc_v2_pipeline

    pipelines = {
        name: make_smc_v2_pipeline("XAUUSD", **kwargs)
        for name, kwargs in CANDIDATES.items()
    }
    replay = DecisionReplay(
        data["m5"], m15=data["m15"], h1=data["h1"], h4=data["h4"],
        daily=data["daily"], symbol="XAUUSD", warmup=290,
        # M1 omitted at this horizon (volume); the brain degrades
        # honestly (M5 swings for tactical stops).
    )
    steps = len(data["m5"]) - 290
    print(f"replaying {steps} M5 steps x {len(pipelines)} variants ...")
    results = replay.run(pipelines)

    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "m5_candles": len(data["m5"]), "variants": {}}
    lines = [
        "# SMC v2 long-horizon edge report",
        "",
        f"- generated {report['generated_at_utc']}; "
        f"{len(data['m5'])} M5 candles "
        f"({data['m5'][0].time_utc:%Y-%m-%d} .. "
        f"{data['m5'][-1].time_utc:%Y-%m-%d}); fills conservative "
        "(0.30 slippage + spread charged)",
        "",
    ]
    for name, result in results.items():
        s = result.summary()
        months = defaultdict(float)
        month_trades = defaultdict(int)
        for t in result.closed:
            mk = t.day.strftime("%Y-%m")
            months[mk] += t.r_multiple
            month_trades[mk] += 1
        trading_days = len({t.day for t in result.closed}) or 1
        s["r_per_day"] = round(s["net_r"] / trading_days, 3)
        s["months"] = {m: round(r, 2) for m, r in sorted(months.items())}
        pos_months = sum(1 for r in months.values() if r > 0)
        report["variants"][name] = s
        lines += [
            f"## {name}  {CANDIDATES[name]}",
            "",
            f"- trades {s['trades']} | win rate {s['win_rate']} | "
            f"net **{s['net_r']:+.1f}R** | R/day {s['r_per_day']:+.3f} | "
            f"max DD {s['max_drawdown_r']}R | months positive "
            f"{pos_months}/{len(months)}",
            "- monthly: " + ", ".join(
                f"{m} {r:+.1f}R({month_trades[m]}t)"
                for m, r in sorted(months.items())
            ),
            "",
        ]
    best = max(report["variants"].items(), key=lambda kv: kv[1]["net_r"])
    lines += [
        "## Verdict",
        "",
        f"Best: **{best[0]}** net {best[1]['net_r']:+.1f}R, "
        f"{best[1]['r_per_day']:+.3f} R/day. The campaign goal needs a "
        "persistent >= +0.15 R/day across regimes — judge against that "
        "bar, not against hope.",
    ]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "v2_longhaul.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    (OUT_DIR / "v2_longhaul.md").write_text("\n".join(lines) + "\n",
                                            encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
