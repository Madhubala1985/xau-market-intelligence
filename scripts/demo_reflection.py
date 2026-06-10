#!/usr/bin/env python3
"""DEMO-EVAL: post-session reflection report.

Reads the demo session report and trade journal, builds the evaluation, and
derives the reflection:

- what the model did well,
- where it was too strict / too loose,
- possibly missed opportunities (honestly marked unproven),
- bad conditions it avoided correctly,
- what must be backtested before changing,
- what can be fixed immediately.

NO live self-mutation: this output is evidence for human-approved changes via
the normal task/test/commit workflow (04_ADAPTATION_POLICY.md). Offline and
read-only; runs anywhere (Windows host or WSL).

Usage:
    python scripts/demo_reflection.py
    python scripts/demo_reflection.py --session reports/runtime/demo_session.json --out demo_reflection
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
    build_reflection,
    render_reflection_markdown,
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
    parser.add_argument("--out", default="demo_reflection",
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
    reflection = build_reflection(evaluation)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = reflection.to_dict()
    out["generated_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    out["source_session"] = str(args.session.name)
    out["evaluation"] = evaluation.to_dict()
    md = render_reflection_markdown(reflection)
    md_path = OUT_DIR / f"{args.out}.md"
    json_path = OUT_DIR / f"{args.out}.json"
    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    print(f"Summary: {reflection.summary}")
    print(f"Wrote {md_path.relative_to(REPO_ROOT)}")
    print(f"Wrote {json_path.relative_to(REPO_ROOT)}")
    if args.stdout:
        print()
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
