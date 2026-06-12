#!/usr/bin/env python3
"""SMC-V2-001 selectivity sweep with walk-forward validation.

Runs the v2 brain variants head-to-head over real MT5 history in ONE
replay pass, scores each on the TRAIN days (first 15 trading days) and
reports the VALIDATE days (the rest) only for the train winner(s) —
guarding against exactly the per-day overfitting that six manual
iterations demonstrated. Read-only; no orders; never mutates live
config.

Usage (Windows MT5 host):
    py -3.12 scripts\\v2_sweep.py --days 25
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.backtest.decision_replay import DecisionReplay  # noqa: E402
from scripts.decision_replay import fetch_all  # noqa: E402

OUT_DIR = REPO_ROOT / "reports" / "runtime"

VARIANTS = {
    # name: brain kwargs (max_entries_per_day=3 everywhere — the
    # institutional-cadence premise is the point, not a tunable)
    "bar62_t2": dict(quality_bar=0.62, trend_target_r=2.0),
    "bar62_t3": dict(quality_bar=0.62, trend_target_r=3.0),
    "bar70_t2": dict(quality_bar=0.70, trend_target_r=2.0),
    "bar70_t3": dict(quality_bar=0.70, trend_target_r=3.0),
    "bar62_t2_struct": dict(quality_bar=0.62, trend_target_r=2.0,
                            structural_stops_only=True),
    "bar62_t3_struct": dict(quality_bar=0.62, trend_target_r=3.0,
                            structural_stops_only=True),
    "bar70_t3_struct": dict(quality_bar=0.70, trend_target_r=3.0,
                            structural_stops_only=True),
    "bar75_t3": dict(quality_bar=0.75, trend_target_r=3.0),
    "cap2_bar62_t3": dict(quality_bar=0.62, trend_target_r=3.0,
                          max_entries_per_day=2),
    "cap2_bar70_t3": dict(quality_bar=0.70, trend_target_r=3.0,
                          max_entries_per_day=2),
}


def split_score(result, train_days):
    train = sum(r for d, r in result.by_day.items() if d in train_days)
    val = sum(r for d, r in result.by_day.items() if d not in train_days)
    n_train = sum(1 for t in result.closed if t.day in train_days)
    n_val = len(result.closed) - n_train
    return round(train, 2), round(val, 2), n_train, n_val


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=25)
    parser.add_argument("--train", type=int, default=15)
    args = parser.parse_args()

    data = fetch_all(args.days)
    from src.strategy.smc_v2 import make_smc_v2_pipeline

    pipelines = {
        name: make_smc_v2_pipeline("XAUUSD", **kwargs)
        for name, kwargs in VARIANTS.items()
    }
    replay = DecisionReplay(
        data["m5"], m1=data["m1"], m15=data["m15"], h1=data["h1"],
        h4=data["h4"], daily=data["daily"], symbol="XAUUSD", warmup=290,
    )
    print(f"sweeping {len(pipelines)} variants over "
          f"{len(data['m5']) - 290} steps ...")
    results = replay.run(pipelines)

    all_days = sorted({t.day for r in results.values() for t in r.closed}
                      | {c.time_utc.date() for c in data["m5"][290:]})
    train_days = set(all_days[:args.train])
    val_days = [d for d in all_days if d not in train_days]

    rows = []
    for name, result in results.items():
        train_r, val_r, n_train, n_val = split_score(result, train_days)
        rows.append({
            "variant": name, "kwargs": VARIANTS[name],
            "train_r": train_r, "val_r": val_r,
            "train_trades": n_train, "val_trades": n_val,
            "total_r": result.net_r, "max_dd": result.max_drawdown_r,
            "by_day": {d.isoformat(): r for d, r in
                       sorted(result.by_day.items())},
        })
    rows.sort(key=lambda r: r["train_r"], reverse=True)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "days": args.days,
        "train_days": [d.isoformat() for d in sorted(train_days)],
        "validate_days": [d.isoformat() for d in val_days],
        "rows": rows,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "v2_sweep.json").write_text(json.dumps(report, indent=2),
                                           encoding="utf-8")
    lines = [
        "# SMC v2 selectivity sweep (walk-forward)",
        "",
        f"- generated {report['generated_at_utc']}; train="
        f"{len(train_days)} days, validate={len(val_days)} days",
        "",
        "| variant | train R | train trades | VALIDATE R | val trades "
        "| total R | max DD |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['variant']} | {r['train_r']:+.2f} | "
            f"{r['train_trades']} | **{r['val_r']:+.2f}** | "
            f"{r['val_trades']} | {r['total_r']:+.2f} | {r['max_dd']} |"
        )
    winner = rows[0]
    lines += [
        "",
        f"Train winner: **{winner['variant']}** "
        f"(train {winner['train_r']:+.2f}R) — validation verdict: "
        f"**{winner['val_r']:+.2f}R on unseen days** "
        f"({'POSITIVE — candidate to ship' if winner['val_r'] > 0 else 'NOT positive — do not ship'}).",
    ]
    (OUT_DIR / "v2_sweep.md").write_text("\n".join(lines) + "\n",
                                         encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
