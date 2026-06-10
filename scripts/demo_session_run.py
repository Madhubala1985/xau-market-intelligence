#!/usr/bin/env python3
"""DEMO-002 / DEMO-EVAL runner: supervised MT5 demo session (Windows host only).

THE ONLY script that can lead to demo orders. Hard requirements before any
cycle runs:

  1. MetaTrader5 importable and demo login works (demo-only settings),
  2. DEMO-001 preflight passes ON THIS RUN (all gates, fresh),
  3. the operator passes the EXACT confirmation:
         --confirm "START SUPERVISED DEMO"
  4. a news source exists (configs/news_windows.json or control/NEWS_BLOCK);
     unknown news state blocks every entry by design,
  5. control/KILL_SWITCH stops the session at the next cycle.

Without --confirm (or with --dry-run) order sending stays DISABLED: the full
loop runs, plans are evaluated through planner -> gateway and counted as
SIMULATED orders, nothing reaches order_send.

Session profiles (--profile) configure duration, polling, and order limits,
bounded by 03_RISK_POLICY.md (a profile can tighten policy, never loosen it):

  smoke       10 min, max ONE order (the only artificial cap; smoke runs only)
  evaluation  60 min, policy-governed order count (DEFAULT, serious eval)
  london      4 h, start at London open, policy-governed
  newyork     4 h, start at New York open, policy-governed
  full_day    8 h (hard ceiling), policy-governed

"Policy-governed" means how much the session trades is decided by the risk
policy (max 3 trades/day, 2% daily / 5% weekly loss, single position plus at
most one protected add-on), confidence tiers, regime, and setup quality —
NOT by an artificial per-session order cap.

Real trading is forbidden: settings/flags that request real mode abort the run.
No credential values are printed or written to any report.

Output: reports/runtime/demo_session.md + .json
Journal: logs/demo_trade_journal.jsonl

Usage (Windows MT5 host, PowerShell):
    # dry-run rehearsal (no orders possible, full loop + plans):
    python scripts/demo_session_run.py --dry-run --profile evaluation

    # smoke run (max ONE order):
    python scripts/demo_session_run.py --confirm "START SUPERVISED DEMO" --profile smoke

    # serious 1-hour supervised evaluation (policy-governed):
    python scripts/demo_session_run.py --confirm "START SUPERVISED DEMO" --profile evaluation
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
from src.execution.demo_planner import DemoTradePlanner  # noqa: E402
from src.execution.demo_session import (  # noqa: E402
    CONFIRMATION_TOKEN,
    SupervisedDemoSession,
)
from src.execution.gateway import (  # noqa: E402
    ExecutionFlags,
    ExecutionGateway,
    load_execution_flags,
)
from src.execution.kill_switch import KillSwitch  # noqa: E402
from src.execution.live_shadow import make_live_pipeline  # noqa: E402
from src.execution.preflight import DemoPreflight  # noqa: E402
from src.execution.session_profiles import PROFILES, get_profile  # noqa: E402
from src.journal.journal import TradeJournal  # noqa: E402
from src.risk.governor import RiskGovernor  # noqa: E402
from src.risk.news_guard import NewsRiskGuard  # noqa: E402

OUT_DIR = REPO_ROOT / "reports" / "runtime"
ENV_PATH = REPO_ROOT / ".env"
JOURNAL_PATH = REPO_ROOT / "logs" / "demo_trade_journal.jsonl"
KILL_SWITCH_PATH = REPO_ROOT / "control" / "KILL_SWITCH"
NEWS_BLOCK_PATH = REPO_ROOT / "control" / "NEWS_BLOCK"
NEWS_CALENDAR_PATH = REPO_ROOT / "configs" / "news_windows.json"


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


def render_markdown(payload: Dict[str, object]) -> str:
    lines: List[str] = []
    lines.append("# Supervised Demo Session (DEMO-002)")
    lines.append("")
    lines.append(f"- Generated: {payload.get('generated_at')}")
    lines.append(f"- Outcome: **{payload.get('outcome')}**")
    lines.append(f"- Verdict: **{payload.get('verdict', 'n/a')}**")
    lines.append(f"- Symbol: {payload.get('symbol')}")
    lines.append(f"- Mode: {payload.get('mode')}")
    lines.append(f"- Profile: {payload.get('profile', 'n/a')}")
    lines.append("- Real trading: **FORBIDDEN**")
    if payload.get("detail"):
        lines.append(f"- Detail: {payload['detail']}")
    report = payload.get("report")
    if isinstance(report, dict):
        lines.append("")
        lines.append("## Session summary")
        lines.append("")
        for key in ("started_at_utc", "ended_at_utc", "cycles", "decisions_logged",
                    "max_orders", "orders_sent", "orders_simulated",
                    "orders_rejected", "entries_blocked",
                    "stop_updates", "violations", "halt_reason"):
            lines.append(f"- {key}: {report.get(key)}")
        recon = report.get("final_reconciliation")
        if recon:
            lines.append(f"- final reconciliation clean: {recon.get('clean')} "
                         f"({recon.get('detail')})")
        lines.append("")
        lines.append("## Events")
        lines.append("")
        lines.append("| # | time (UTC) | kind | detail |")
        lines.append("|---|---|---|---|")
        for i, e in enumerate(report.get("events", []), start=1):
            lines.append(f"| {i} | {e['time_utc']} | {e['kind']} | {e['detail']} |")
        lines.append("")
    return "\n".join(lines)


def write_report(payload: Dict[str, object], name: str) -> Dict[str, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    md_path = OUT_DIR / f"{name}.md"
    json_path = OUT_DIR / f"{name}.json"
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"markdown": md_path, "json": json_path}


_UNSET = object()  # argparse runs `type` on STRING defaults; an object skips it


def parse_max_orders(value: str):
    """Parse --max-orders: an integer cap, or 'policy'/'none' for no cap."""
    text = value.strip().lower()
    if text in ("policy", "none"):
        return None
    count = int(text)
    if count < 0:
        raise argparse.ArgumentTypeError("--max-orders must be >= 0")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--confirm", default="",
                        help=f"exact confirmation token: {CONFIRMATION_TOKEN!r}")
    parser.add_argument("--dry-run", action="store_true",
                        help="full loop with order sending DISABLED; approved "
                             "plans are counted as SIMULATED orders")
    parser.add_argument("--profile", default="evaluation",
                        choices=sorted(PROFILES),
                        help="session risk profile (policy-bounded); "
                             "default: evaluation")
    parser.add_argument("--duration-minutes", type=float, default=None,
                        help="override the profile duration")
    parser.add_argument("--poll-seconds", type=float, default=None,
                        help="override the profile poll interval")
    parser.add_argument("--max-orders", type=parse_max_orders, default=_UNSET,
                        help="override the profile session order cap: an "
                             "integer, or 'policy' for no artificial cap")
    parser.add_argument("--max-open-positions", type=int, default=None,
                        help="override the profile max open positions "
                             "(policy bound still applies)")
    parser.add_argument("--report-name", default="demo_session")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    profile = get_profile(args.profile)
    try:
        profile = profile.with_overrides(
            duration_minutes=args.duration_minutes,
            poll_seconds=args.poll_seconds,
            max_orders=(args.max_orders if args.max_orders is not _UNSET
                        else profile.max_orders),
            max_open_positions=args.max_open_positions,
        )
    except ValueError as exc:
        print(f"REFUSED: {exc}")
        return 2

    env_load = load_env_safely()
    payload: Dict[str, object] = {
        "task": "DEMO-002", "env_load": env_load,
        "symbol": str(os.environ.get("MT5_SYMBOL", "XAUUSD")).strip() or "XAUUSD",
        "mode": "DRY_RUN" if args.dry_run else "SUPERVISED_DEMO",
        "profile": profile.name,
        "max_orders": profile.max_orders,
    }

    # Confirmation gating (before anything touches MT5).
    if not args.dry_run and args.confirm != CONFIRMATION_TOKEN:
        payload.update({
            "outcome": "REFUSED",
            "detail": "missing/incorrect --confirm token; use --dry-run for a "
                      "no-order rehearsal",
        })
        write_report(payload, args.report_name)
        print("REFUSED: supervised demo requires the exact --confirm token "
              f"({CONFIRMATION_TOKEN!r}) or --dry-run.")
        return 2

    try:
        import MetaTrader5  # type: ignore  # noqa: F401
    except Exception as exc:
        payload.update({
            "outcome": "ENVIRONMENT_ISSUE",
            "detail": f"MetaTrader5 not importable: {exc.__class__.__name__}; "
                      "run on the Windows MT5 host",
        })
        write_report(payload, args.report_name)
        print(f"Outcome: ENVIRONMENT_ISSUE")
        return 2

    try:
        settings = load_mt5_settings()  # demo-only configuration enforced
    except MissingCredentialsError as exc:
        payload.update({"outcome": "CONFIG_INCOMPLETE",
                        "detail": "missing: " + ", ".join(exc.missing)})
        write_report(payload, args.report_name)
        print("Outcome: CONFIG_INCOMPLETE")
        return 2

    payload["symbol"] = settings.symbol
    canonical = settings.canonical_symbol
    kill_switch = KillSwitch(KILL_SWITCH_PATH)
    news_guard = NewsRiskGuard(block_path=NEWS_BLOCK_PATH,
                               calendar_path=NEWS_CALENDAR_PATH)

    adapter = MT5DataAdapter(settings)
    try:
        adapter.connect()
        client = adapter._mt5

        # Fresh DEMO-001 preflight ON THIS RUN; refuse anything not READY.
        preflight = DemoPreflight(
            env=os.environ, broker_symbol=settings.symbol, client=client,
            journal_probe_path=REPO_ROOT / "logs" / "demo_preflight_probe.jsonl",
            kill_switch=kill_switch,
        ).run()
        payload["preflight_ready"] = preflight.ready
        if not preflight.ready:
            failed = [g.name for g in preflight.gates if g.status.value != "PASS"]
            payload.update({"outcome": "PREFLIGHT_FAILED",
                            "detail": f"gates not PASS: {failed}"})
            write_report(payload, args.report_name)
            print(f"Outcome: PREFLIGHT_FAILED ({failed})")
            return 2

        # Execution flags: env-driven for the confirmed run, hard-disabled
        # for --dry-run. Real mode aborts inside the gateway/session anyway.
        # A dry run keeps the profile's order limits so it rehearses the
        # exact loop the live run will execute; approved plans surface as
        # SIMULATED orders and never reach order_send.
        flags = ExecutionFlags() if args.dry_run else load_execution_flags(os.environ)
        limits = profile.risk_limits(canonical)
        gateway = ExecutionGateway(
            RiskGovernor(limits), flags, client,
            expected_symbol=canonical, kill_switch=kill_switch,
        )
        session = SupervisedDemoSession(
            adapter=adapter,
            pipeline=make_live_pipeline(
                canonical, max_spread_price=profile.max_spread_price
            ),
            planner=DemoTradePlanner(limits=limits),
            gateway=gateway,
            journal=TradeJournal(JOURNAL_PATH),
            symbol=settings.symbol,
            confirmation=CONFIRMATION_TOKEN,  # CLI/dry-run gating happened above
            preflight=preflight,
            news_guard=news_guard,
            kill_switch=kill_switch,
            max_orders=profile.max_orders,
            profile_name=profile.name,
        )
        report = session.run(
            duration_seconds=profile.duration_minutes * 60.0,
            poll_seconds=profile.poll_seconds,
        )
        payload["report"] = report.to_dict()
        payload["verdict"] = report.verdict
        payload["outcome"] = "COMPLETED"
        exit_code = 0 if report.verdict in ("CLEAN", "HALTED_BY_KILL_SWITCH") else 2
    except (BrokerError, RuntimeError, ValueError) as exc:
        payload.update({"outcome": "FAIL", "detail": str(exc)})
        exit_code = 2
    finally:
        adapter.shutdown()

    paths = write_report(payload, args.report_name)
    print(f"Outcome: {payload['outcome']}  Verdict: {payload.get('verdict', 'n/a')}")
    print(f"Wrote {paths['markdown'].relative_to(REPO_ROOT)}")
    print(f"Wrote {paths['json'].relative_to(REPO_ROOT)}")
    if args.stdout:
        print()
        print(render_markdown(payload))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
