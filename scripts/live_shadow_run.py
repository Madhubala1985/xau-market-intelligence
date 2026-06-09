#!/usr/bin/env python3
"""LIVE-001 runner: live MT5 demo data -> DecisionPipeline -> ShadowRunner.

Runs a READ-ONLY live shadow session on the WINDOWS host where MetaTrader5 is
installed. Every decision (trade and no-trade) is journaled; NO orders are ever
placed (order_send / order_check are never called) and NO credential values are
printed or written to any report.

Safety gates before any cycle runs:
  * settings load via load_mt5_settings (demo-only configuration enforced),
  * the logged-in account must verify as DEMO / non-real, otherwise abort,
  * the session has a mandatory stop condition (--cycles or --duration-minutes).

On a host without MetaTrader5 (e.g. WSL/Linux) the script reports an honest
ENVIRONMENT_ISSUE and exits non-zero. Live validation is never faked.

Output: reports/runtime/live_shadow_run.md + .json
Journal: logs/live_shadow_journal.jsonl (append-only, git-ignored)

Usage (Windows MT5 host, PowerShell):
    python scripts/live_shadow_run.py --cycles 5
    python scripts/live_shadow_run.py --duration-minutes 5 --poll-seconds 30
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
from src.execution.live_shadow import (  # noqa: E402
    LiveShadowReport,
    LiveShadowSession,
    make_live_pipeline,
)
from src.journal.journal import TradeJournal  # noqa: E402

OUT_DIR = REPO_ROOT / "reports" / "runtime"
ENV_PATH = REPO_ROOT / ".env"
JOURNAL_PATH = REPO_ROOT / "logs" / "live_shadow_journal.jsonl"

# MT5 ACCOUNT_TRADE_MODE_* fallback values (documented constants).
_TRADE_MODE_DEMO = 0
_TRADE_MODE_CONTEST = 1
_TRADE_MODE_REAL = 2


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
    """Return (client_or_None, reason). Never raises."""
    try:
        import MetaTrader5 as mt5  # type: ignore

        return mt5, "MetaTrader5 imported"
    except Exception as exc:
        return None, f"MetaTrader5 not importable: {exc.__class__.__name__}"


def verify_demo_account(client) -> str:
    """Verify the logged-in account is non-real. Raises RuntimeError on REAL.

    Returns a short, credential-free label (DEMO / CONTEST).
    """
    info = client.account_info() if hasattr(client, "account_info") else None
    if info is None:
        raise RuntimeError("account_info() returned no data; cannot verify demo account")
    demo = getattr(client, "ACCOUNT_TRADE_MODE_DEMO", _TRADE_MODE_DEMO)
    contest = getattr(client, "ACCOUNT_TRADE_MODE_CONTEST", _TRADE_MODE_CONTEST)
    real = getattr(client, "ACCOUNT_TRADE_MODE_REAL", _TRADE_MODE_REAL)
    trade_mode = getattr(info, "trade_mode", None)
    if trade_mode == real:
        raise RuntimeError("account trade_mode is REAL — refused (demo only)")
    if trade_mode == demo:
        return "DEMO"
    if trade_mode == contest:
        return "CONTEST"
    raise RuntimeError(f"account trade_mode {trade_mode!r} is not a known non-real mode")


# --------------------------------------------------------------------------
# Report rendering / IO (credential-free by construction)
# --------------------------------------------------------------------------

def render_markdown(payload: Dict[str, object]) -> str:
    lines: List[str] = []
    lines.append("# Live Shadow Run (LIVE-001)")
    lines.append("")
    lines.append(f"- Generated: {payload.get('generated_at')}")
    lines.append(f"- Outcome: **{payload.get('outcome')}**")
    lines.append(f"- Symbol: {payload.get('symbol')}")
    lines.append(f"- Account mode: {payload.get('account_mode', 'n/a')}")
    lines.append("- Real trading: **FORBIDDEN** — no order_send is ever called")
    if payload.get("detail"):
        lines.append(f"- Detail: {payload['detail']}")
    report = payload.get("report")
    if isinstance(report, dict):
        lines.append("")
        lines.append("## Session summary")
        lines.append("")
        for key in ("started_at_utc", "ended_at_utc", "cycles", "decisions_logged",
                    "actionable_decisions", "approved_decisions", "orders_sent",
                    "journal_path"):
            lines.append(f"- {key}: {report.get(key)}")
        lines.append("")
        lines.append("## Decision cycles")
        lines.append("")
        lines.append(
            "| # | time (UTC) | stage | direction | approved | spread | lot "
            "| conf | uncert | risk | reason |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for i, r in enumerate(report.get("results", []), start=1):
            risk = r.get("risk_action") or "-"
            risk_reasons = "; ".join(r.get("risk_reasons", []))
            reason = r["reason"] or risk_reasons
            lines.append(
                f"| {i} | {r['time_utc']} | {r['stage']} | {r['direction']} | "
                f"{r['approved']} | {r['spread_price']} | {r['lot_size']} | "
                f"{r.get('confidence', '-')} | {r.get('uncertainty', '-')} | "
                f"{risk} | {reason} |"
            )
        lines.append("")
    return "\n".join(lines)


def write_report(payload: Dict[str, object], report_name: str = "live_shadow_run") -> Dict[str, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    md_path = OUT_DIR / f"{report_name}.md"
    json_path = OUT_DIR / f"{report_name}.json"
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"markdown": md_path, "json": json_path}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--cycles", type=int, help="run exactly N decision cycles")
    group.add_argument("--duration-minutes", type=float,
                       help="run for N minutes (polling between cycles)")
    parser.add_argument("--poll-seconds", type=float, default=60.0,
                        help="seconds between decision cycles (default 60)")
    parser.add_argument("--report-name", default="live_shadow_run",
                        help="report basename under reports/runtime/ "
                             "(use live_shadow_session for LIVE-002 evidence)")
    parser.add_argument("--stdout", action="store_true", help="also print markdown")
    args = parser.parse_args()

    env_load = load_env_safely()
    payload: Dict[str, object] = {
        "task": "LIVE-001",
        "env_load": env_load,
        "symbol": str(os.environ.get("MT5_SYMBOL", "XAUUSD")).strip() or "XAUUSD",
    }

    client, import_reason = try_import_mt5()
    if client is None:
        payload.update({
            "outcome": "ENVIRONMENT_ISSUE",
            "detail": f"{import_reason}; run on the Windows MT5 host "
                      "(see scripts/winmt5_runner_README.md)",
        })
        paths = write_report(payload, args.report_name)
        print(f"Outcome: {payload['outcome']} ({import_reason})")
        print(f"Wrote {paths['markdown'].relative_to(REPO_ROOT)}")
        return 2

    try:
        settings = load_mt5_settings()  # enforces demo-only configuration
    except MissingCredentialsError as exc:
        payload.update({
            "outcome": "CONFIG_INCOMPLETE",
            "detail": "missing environment variables: " + ", ".join(exc.missing),
        })
        write_report(payload, args.report_name)
        print(f"Outcome: CONFIG_INCOMPLETE (missing: {', '.join(exc.missing)})")
        return 2

    payload["symbol"] = settings.symbol  # exact broker case, e.g. XAUUSDm

    adapter = MT5DataAdapter(settings)
    try:
        adapter.connect()
        # Hard safety gate: refuse anything that is not a demo/non-real account.
        payload["account_mode"] = verify_demo_account(adapter._mt5)

        pipeline = make_live_pipeline(settings.canonical_symbol)
        journal = TradeJournal(JOURNAL_PATH)
        session = LiveShadowSession(
            adapter=adapter,
            pipeline=pipeline,
            journal=journal,
            symbol=settings.symbol,
        )
        report: LiveShadowReport = session.run(
            poll_seconds=args.poll_seconds,
            duration_seconds=(
                args.duration_minutes * 60.0 if args.duration_minutes else None
            ),
            max_cycles=args.cycles,
        )
        payload["report"] = report.to_dict()
        payload["outcome"] = "COMPLETED" if report.orders_sent == 0 else "SAFETY_FAILURE"
        exit_code = 0 if report.orders_sent == 0 else 2
    except (BrokerError, RuntimeError) as exc:
        payload.update({"outcome": "FAIL", "detail": str(exc)})
        exit_code = 2
    finally:
        adapter.shutdown()

    paths = write_report(payload, args.report_name)
    print(f"Outcome: {payload['outcome']}")
    print(f"Wrote {paths['markdown'].relative_to(REPO_ROOT)}")
    print(f"Wrote {paths['json'].relative_to(REPO_ROOT)}")
    if args.stdout:
        print()
        print(render_markdown(payload))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
