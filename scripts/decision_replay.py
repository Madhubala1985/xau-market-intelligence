#!/usr/bin/env python3
"""LIQUIDITY-INTEL-001 shipping gate: replay the single liquidity_intel engine
on real MT5 history.

Fetches real XAU/USD candles (M5/M1/M15/H1/H4/D1) from the MT5 terminal
(read-only) and replays them through the ONE decision engine under the
conservative fill model of src/backtest/decision_replay.py (entry at the next
candle open, spread + 0.30 slippage charged, intrabar SL-first when both SL
and TP are touched, break-even armed at +1R). Writes the report + ship verdict
to reports/runtime/liquidity_intel_replay.md/.json. NEVER changes live config
and NEVER sends orders.

SHIP BAR (self-imposed, non-negotiable): the engine trades live demo only if
its replay net R is POSITIVE with a contained drawdown. Otherwise it stays
flat live — protecting capital is the position.

Usage (Windows MT5 host):
    py -3.12 scripts\\decision_replay.py --days 25
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

from src.backtest.decision_replay import DecisionReplay  # noqa: E402

OUT_DIR = REPO_ROOT / "reports" / "runtime"

# Ship bar: positive net R and a drawdown that does not exceed this many R.
MAX_SHIP_DRAWDOWN_R = 12.0


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


def ship_verdict(result) -> dict:
    """Single-engine ship bar: positive net R + contained drawdown."""
    reasons = []
    n_trades = len(result.trades)
    net_ok = result.net_r > 0.0
    reasons.append(
        f"net R {result.net_r:+.2f} over {n_trades} trades "
        f"({'PASS' if net_ok else 'FAIL'} — must be positive)")
    dd_ok = result.max_drawdown_r <= MAX_SHIP_DRAWDOWN_R
    reasons.append(
        f"max drawdown {result.max_drawdown_r:.2f}R "
        f"({'PASS' if dd_ok else 'FAIL'} — must be <= "
        f"{MAX_SHIP_DRAWDOWN_R:.0f}R)")
    enough = n_trades >= 10
    reasons.append(
        f"sample size {n_trades} trades "
        f"({'PASS' if enough else 'FAIL'} — need >= 10 for a read)")
    return {"ship": net_ok and dd_ok and enough, "reasons": reasons}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=25)
    parser.add_argument("--symbol", default=None)
    args = parser.parse_args()

    data = fetch_all(args.days)
    symbol = args.symbol or data["m5"][-1].symbol
    canonical = symbol.strip().upper()

    from src.strategy.liquidity_intel import make_liquidity_intel_pipeline

    pipelines = {"liquidity_intel": make_liquidity_intel_pipeline(canonical)}
    replay = DecisionReplay(
        data["m5"], m1=data["m1"], m15=data["m15"], h1=data["h1"],
        h4=data["h4"], daily=data["daily"], symbol=canonical, warmup=290,
    )
    print(f"replaying {len(data['m5']) - 290} M5 steps through the "
          "liquidity_intel engine ...")
    results = replay.run(pipelines)
    res = results["liquidity_intel"]
    gate = ship_verdict(res)

    def dump(trades):
        return [
            {"day": str(t.day), "time": str(t.entry_time),
             "dir": t.direction.value, "entry": t.entry, "stop": t.stop,
             "target": t.target, "setup": t.setup,
             "outcome": t.outcome, "r": t.r_multiple}
            for t in trades
        ]

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "trades": dump(res.trades),
        "days_requested": args.days,
        "symbol": canonical,
        "fill_model": "entry next open, spread+0.30 slippage, SL-first, "
                      "BE at 1R",
        "summary": res.summary(),
        "verdict": gate,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "liquidity_intel_replay.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# Liquidity Intelligence Replay Verdict (LIQUIDITY-INTEL-001)",
        "",
        f"- generated: {report['generated_at_utc']}",
        f"- symbol: {canonical}; days: {args.days}; fill model: "
        f"{report['fill_model']}",
        "",
        "| metric | liquidity_intel |",
        "|--------|-----------------|",
    ]
    for key in ("trades", "wins", "losses", "breakevens", "net_r",
                "win_rate", "max_drawdown_r"):
        lines.append(f"| {key} | {report['summary'][key]} |")
    lines += ["", "## Per-day net R", "", "| day | net R |", "|---|---|"]
    for d in sorted(report["summary"]["by_day"]):
        lines.append(f"| {d} | {report['summary']['by_day'][d]:+.2f} |")
    lines += ["", "## Verdict", ""]
    lines += [f"- {r}" for r in gate["reasons"]]
    lines.append(
        f"\n**SHIP: {'YES' if gate['ship'] else 'NO'}** — "
        + ("the engine may trade live demo (--profile liquidity_intel)."
           if gate["ship"] else
           "the engine stays FLAT live; iterate before trading."))
    (OUT_DIR / "liquidity_intel_replay.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
