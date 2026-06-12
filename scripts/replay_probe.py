#!/usr/bin/env python3
"""One-off SMC-V2-001 diagnostic: print v2's decision reason at chosen
times on real history (read-only; no orders)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.backtest.decision_replay import DecisionReplay  # noqa: E402
from scripts.decision_replay import fetch_all  # noqa: E402


def main() -> int:
    times = [
        "2026-06-08 06:15", "2026-06-08 07:25", "2026-06-08 08:00",
        "2026-06-08 09:50", "2026-06-11 05:00", "2026-06-11 10:00",
        "2026-06-11 14:40", "2026-06-11 16:00", "2026-06-11 18:00",
        "2026-06-11 22:00",
    ]
    targets = [
        datetime.strptime(t, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        for t in times
    ]
    data = fetch_all(12)
    from src.strategy.smc_v2 import make_smc_v2_pipeline
    pipe = make_smc_v2_pipeline("XAUUSD")
    replay = DecisionReplay(
        data["m5"], m1=data["m1"], m15=data["m15"], h1=data["h1"],
        h4=data["h4"], daily=data["daily"], symbol="XAUUSD", warmup=290,
    )
    m5 = data["m5"]
    index_of = {c.time_utc: i for i, c in enumerate(m5)}
    for target in targets:
        i = index_of.get(target)
        if i is None:
            print(f"{target}: no candle")
            continue
        result = replay._decide(pipe, i, 0, 0)
        ch = (result.context.challenge
              if result and result.context else {}) or {}
        print(f"\n=== {target} approved={getattr(result, 'approved', None)}")
        print(f"  narrative: {ch.get('narrative')}")
        print(f"  reason: {getattr(result, 'reason', None)}")
        print(f"  anchor={ch.get('smc_anchor')} trigger="
              f"{ch.get('entry_trigger')} quality={ch.get('quality')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
