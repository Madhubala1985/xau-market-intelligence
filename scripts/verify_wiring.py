#!/usr/bin/env python3
"""FINAL-INTELLIGENCE: executable wiring verification report.

Runs the real DecisionPipeline on synthetic candles, introspects the result
and the live execution classes, and writes the per-layer wiring status
(LIVE / PARTIAL / UNAVAILABLE_BY_CONFIG / PLACEHOLDER / MISSING) with
evidence. Read-only; runs anywhere (no MT5 required).

Usage:
    python scripts/verify_wiring.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.reflection.wiring_verification import (  # noqa: E402
    render_wiring_markdown,
    verify_wiring,
)

OUT_DIR = REPO_ROOT / "reports" / "runtime"


def main() -> int:
    report = verify_wiring(REPO_ROOT)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["generated_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    (OUT_DIR / "wiring_verification.md").write_text(
        render_wiring_markdown(report), encoding="utf-8"
    )
    (OUT_DIR / "wiring_verification.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print("Wiring:", "  ".join(
        f"{k}={v}" for k, v in payload["summary"].items()
    ))
    print("Wrote reports/runtime/wiring_verification.md and .json")
    return 0 if report.missing == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
