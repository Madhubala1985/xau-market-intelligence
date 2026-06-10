#!/usr/bin/env python3
"""DEMO-EVAL: post-session demo evaluation report.

Reads ONE completed supervised demo session (its JSON report) plus the demo
trade journal and writes the serious performance evaluation:

- decision totals, trades taken / simulated / skipped, no-trade reasons,
- regime / session / HTF-bias / confidence / spread distributions,
- news blocks, risk blocks, kill-switch / violation status,
- realized P&L, max drawdown, win/loss over CLOSED real demo trades,
- mistakes (reflection engine),
- findings classified as PROVEN_DEFECT / HIGH_CONFIDENCE_DEFECT /
  HYPOTHESIS / OBSERVATION / DESIGN_IMPROVEMENT.

Offline and read-only: no MT5, no orders, no credentials, no policy mutation.
Runs anywhere (Windows host or WSL) — it only reads files.

Usage:
    python scripts/demo_eval_report.py
    python scripts/demo_eval_report.py --session reports/runtime/demo_session.json --out demo_evaluation
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

from src.journal.journal import TradeJournal  # noqa: E402
from src.reflection.demo_evaluation import (  # noqa: E402
    SessionEvaluator,
    render_evaluation_markdown,
)

OUT_DIR = REPO_ROOT / "reports" / "runtime"
DEFAULT_SESSION = OUT_DIR / "demo_session.json"
DEFAULT_JOURNAL = REPO_ROOT / "logs" / "demo_trade_journal.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, default=DEFAULT_SESSION,
                        help="session report JSON (from demo_session_run.py)")
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL,
                        help="demo trade journal (JSONL)")
    parser.add_argument("--out", default="demo_evaluation",
                        help="output report name (md + json)")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    if not args.session.is_file():
        print(f"FAIL: session report not found: {args.session}")
        return 2
    payload = json.loads(args.session.read_text(encoding="utf-8"))
    journal = TradeJournal(args.journal)

    evaluation = SessionEvaluator().evaluate(
        payload, journal.records(), journal.decisions()
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = evaluation.to_dict()
    out["generated_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    out["source_session"] = str(args.session.name)
    md = render_evaluation_markdown(evaluation)
    md_path = OUT_DIR / f"{args.out}.md"
    json_path = OUT_DIR / f"{args.out}.json"
    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    print(f"Mode: {evaluation.mode or 'n/a'}  Verdict: {evaluation.verdict or 'n/a'}")
    print(f"Real demo trades: {evaluation.trades_real}  "
          f"Simulated: {evaluation.trades_simulated}  "
          f"Closed: {evaluation.performance.trades_closed}  "
          f"PnL: {evaluation.performance.pnl_total:.2f}")
    print(f"Wrote {md_path.relative_to(REPO_ROOT)}")
    print(f"Wrote {json_path.relative_to(REPO_ROOT)}")
    if args.stdout:
        print()
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
