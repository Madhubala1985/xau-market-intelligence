#!/usr/bin/env python3
"""Run a research-lab setup over stored history and emit the evidence report.

Usage:
    python scripts/research_run.py                       # run all registered setups
    python scripts/research_run.py london_sweep_reclaim_long

Reads candles from data/raw/ (see scripts/export_mt5_history.py to populate it).
Writes a markdown report to reports/research/<setup>_<version>.md and prints a
one-line verdict per setup. NEVER connects to a broker; NEVER sends orders.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from research.data_loader import has_data, load_dataset  # noqa: E402
from research.harness import run_setup  # noqa: E402
from research.report import render  # noqa: E402
from research.setups import REGISTRY  # noqa: E402
from research.setups.base import MarketData  # noqa: E402


def main(argv: list[str]) -> int:
    if not has_data():
        print("NO DATA in data/raw/. Export history first:")
        print("  (on the Windows MT5 terminal) python scripts/export_mt5_history.py")
        return 2

    names = argv[1:] or list(REGISTRY)
    unknown = [n for n in names if n not in REGISTRY]
    if unknown:
        print(f"unknown setup(s): {unknown}. available: {list(REGISTRY)}")
        return 2

    data_by_tf, reports = load_dataset()
    for r in reports:
        print(r.summary())
    data = MarketData(by_tf=data_by_tf)

    out_dir = REPO_ROOT / "reports" / "research"
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in names:
        setup = REGISTRY[name]()
        result = run_setup(setup, data)
        report_md = render(result)
        out_path = out_dir / f"{setup.name}_{setup.version}.md"
        out_path.write_text(report_md)
        print(
            f"[{setup.name} {setup.version}] {result.classification.value} — "
            f"{result.metrics.trades} trades, expectancy {result.metrics.expectancy:+.3f}R "
            f"-> {out_path.relative_to(REPO_ROOT)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
