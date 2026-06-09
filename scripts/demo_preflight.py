#!/usr/bin/env python3
"""DEMO-001 runner: demo execution preflight (gates only — NO order placement).

Verifies every gate that must hold before demo order sending may be allowed.
order_send is NEVER called; the functional gateway probes are blocked before
any order path. No credential values are printed or written to any report.

On the Windows MT5 host the account/symbol gates run against the live demo
terminal; elsewhere they are honestly reported as SKIPPED (which blocks
readiness — preflight can only pass on the Windows MT5 host).

Output: reports/runtime/demo_preflight.md + .json

Usage (Windows MT5 host, PowerShell):
    python scripts/demo_preflight.py
    python scripts/demo_preflight.py --stdout
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.broker.errors import BrokerError, MissingCredentialsError  # noqa: E402
from src.broker.mt5_data_adapter import MT5DataAdapter  # noqa: E402
from src.broker.mt5_settings import load_mt5_settings  # noqa: E402
from src.execution.kill_switch import KillSwitch  # noqa: E402
from src.execution.preflight import DemoPreflight  # noqa: E402

OUT_DIR = REPO_ROOT / "reports" / "runtime"
ENV_PATH = REPO_ROOT / ".env"
KILL_SWITCH_PATH = REPO_ROOT / "control" / "KILL_SWITCH"
JOURNAL_PROBE_PATH = REPO_ROOT / "logs" / "demo_preflight_probe.jsonl"


def load_env_safely(dotenv_path: Path = ENV_PATH) -> str:
    """Load .env into os.environ without printing any value."""
    if not dotenv_path.is_file():
        return "no .env file found"
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(dotenv_path, override=False)
        return "loaded via python-dotenv"
    except Exception:
        loaded = 0
        for raw in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip()
                loaded += 1
        return f"loaded via builtin parser ({loaded} keys)"


def try_import_mt5():
    try:
        import MetaTrader5 as mt5  # type: ignore

        return mt5, "MetaTrader5 imported"
    except Exception as exc:
        return None, f"MetaTrader5 not importable: {exc.__class__.__name__}"


def render_markdown(payload: Dict[str, object]) -> str:
    lines: List[str] = []
    lines.append("# Demo Execution Preflight (DEMO-001)")
    lines.append("")
    lines.append(f"- Generated: {payload.get('generated_at')}")
    lines.append(f"- Ready for supervised demo: **{payload.get('ready')}**")
    lines.append(f"- Symbol: {payload.get('symbol')}")
    lines.append("- Real trading: **FORBIDDEN** — preflight places no orders")
    if payload.get("detail"):
        lines.append(f"- Detail: {payload['detail']}")
    lines.append("")
    lines.append("## Gates")
    lines.append("")
    lines.append("| # | Gate | Status | Detail |")
    lines.append("|---|---|---|---|")
    for i, g in enumerate(payload.get("gates", []), start=1):
        lines.append(f"| {i} | {g['name']} | {g['status']} | {g['detail']} |")
    lines.append("")
    if not payload.get("ready"):
        lines.append("Preflight is NOT ready: every gate must be PASS before "
                     "supervised demo trading (DEMO-002) may be considered. "
                     "SKIPPED gates require the Windows MT5 host.")
        lines.append("")
    return "\n".join(lines)


def write_report(payload: Dict[str, object]) -> Dict[str, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    md_path = OUT_DIR / "demo_preflight.md"
    json_path = OUT_DIR / "demo_preflight.json"
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"markdown": md_path, "json": json_path}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdout", action="store_true", help="also print markdown")
    args = parser.parse_args()

    env_load = load_env_safely()
    symbol = str(os.environ.get("MT5_SYMBOL", "XAUUSD")).strip() or "XAUUSD"
    payload: Dict[str, object] = {"task": "DEMO-001", "env_load": env_load}

    client, import_reason = try_import_mt5()
    adapter = None
    detail = import_reason
    if client is not None:
        try:
            settings = load_mt5_settings()  # enforces demo-only configuration
            symbol = settings.symbol
            adapter = MT5DataAdapter(settings)
            adapter.connect()
            client = adapter._mt5
        except (MissingCredentialsError, BrokerError) as exc:
            client = None
            detail = f"MT5 connect failed: {exc}"

    preflight = DemoPreflight(
        env=os.environ,
        broker_symbol=symbol,
        client=client,
        journal_probe_path=JOURNAL_PROBE_PATH,
        kill_switch=KillSwitch(KILL_SWITCH_PATH),
    )
    try:
        report = preflight.run()
    finally:
        if adapter is not None:
            adapter.shutdown()

    payload.update(report.to_dict())
    payload["detail"] = detail
    paths = write_report(payload)
    print(f"Ready: {report.ready}")
    print(f"Wrote {paths['markdown'].relative_to(REPO_ROOT)}")
    print(f"Wrote {paths['json'].relative_to(REPO_ROOT)}")
    if args.stdout:
        print()
        print(render_markdown(payload))
    return 0 if report.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
