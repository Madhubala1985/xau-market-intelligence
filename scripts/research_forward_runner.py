#!/usr/bin/env python3
"""DEMO forward-test runner for the research-lab setups (RESEARCH-LAB-001).

RUN THIS ON THE WINDOWS MT5 TERMINAL (MetaTrader5 is Windows-only). It connects
to the DEMO account, watches each newly-closed M5 bar, and forward-tests the
four directional research setups. Every order is routed through the existing
ExecutionGateway, so all safety layers apply unchanged (real-money refusal, kill
switch, demo preflight, RiskGovernor, broker stops-level).

IMPORTANT — these setups are UNPROVEN: no backtest has run yet (data/raw is
empty). This collects live DEMO behaviour only; it is not evidence of an edge.
For real evidence, export history (scripts/export_mt5_history.py) and backtest
(scripts/research_run.py).

Usage (Windows venv):
    python scripts/research_forward_runner.py            # send DEMO orders
    python scripts/research_forward_runner.py --dry-run  # detect only, send nothing
    python scripts/research_forward_runner.py --poll-seconds 15 --max-cycles 5000
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

KILL_SWITCH_PATH = REPO_ROOT / "logs" / "KILL_SWITCH"


def main() -> int:
    ap = argparse.ArgumentParser(description="DEMO forward-test the research setups.")
    ap.add_argument("--dry-run", action="store_true",
                    help="detect signals and size them but send NO orders")
    ap.add_argument("--poll-seconds", type=float, default=20.0)
    ap.add_argument("--max-cycles", type=int, default=0, help="0 = run until Ctrl-C")
    ap.add_argument("--risk-pct", type=float, default=0.005)
    args = ap.parse_args()

    try:
        import MetaTrader5  # type: ignore  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        print(f"ENVIRONMENT_ISSUE: MetaTrader5 not importable "
              f"({exc.__class__.__name__}); run on the Windows MT5 host.")
        return 2

    import os

    from src.broker.mt5_data_adapter import MT5DataAdapter, verify_demo_account
    from src.broker.mt5_settings import load_dotenv_file, load_mt5_settings
    from src.execution.gateway import (
        ExecutionFlags, ExecutionGateway, load_execution_flags,
    )
    from src.execution.kill_switch import KillSwitch
    from src.execution.preflight import DemoPreflight
    from src.execution.research_forward import ResearchForwardRunner
    from src.execution.trading_service import mask_login
    from src.risk.governor import RiskGovernor, RiskLimits
    from src.risk.position_sizing import PositionSizer
    from research.setups import REGISTRY

    load_dotenv_file()
    settings = load_mt5_settings()  # raises if not demo-only configured
    canonical = settings.canonical_symbol
    kill_switch = KillSwitch(KILL_SWITCH_PATH)

    adapter = MT5DataAdapter(settings)
    try:
        adapter.connect()
        client = adapter._mt5

        # REAL accounts are refused here; only DEMO proceeds.
        account_type = verify_demo_account(client)

        preflight = DemoPreflight(
            env=os.environ, broker_symbol=settings.symbol, client=client,
            journal_probe_path=REPO_ROOT / "logs" / "research_forward_probe.jsonl",
            kill_switch=kill_switch,
        ).run()
        if not preflight.ready:
            failed = [g.name for g in preflight.gates if g.status.value != "PASS"]
            print(f"PREFLIGHT_FAILED: gates not PASS: {failed}")
            return 2

        flags = ExecutionFlags() if args.dry_run else load_execution_flags(os.environ)
        # Hard demo lock before we build anything that can send.
        if flags.real_requested:
            print("REFUSED: execution flags request REAL trading. DEMO only.")
            return 2

        limits = RiskLimits()
        gateway = ExecutionGateway(
            RiskGovernor(limits), flags, client,
            expected_symbol=canonical, broker_symbol=settings.symbol,
            kill_switch=kill_switch,
        )
        setups = [cls() for cls in REGISTRY.values()]
        runner = ResearchForwardRunner(
            setups=setups, adapter=adapter, gateway=gateway,
            sizer=PositionSizer(), symbol=settings.symbol, risk_pct=args.risk_pct,
            on_event=lambda e: _print_event(e),
        )

        mode = "DRY_RUN (no orders sent)" if not flags.demo_send_enabled else \
            f"EXECUTION — DEMO orders WILL be sent ({account_type})"
        print("=" * 72)
        print("RESEARCH FORWARD-TEST RUNNER — UNPROVEN setups, DEMO only")
        print(f"  account: {mask_login(settings.login)} ({account_type})  "
              f"server: {settings.server}  symbol: {settings.symbol}")
        print(f"  mode: {mode}")
        print(f"  risk/trade: {args.risk_pct:.2%}   setups: "
              f"{', '.join(REGISTRY)}")
        print(f"  kill switch: {'ENGAGED' if kill_switch.engaged else 'absent'} "
              f"({KILL_SWITCH_PATH})")
        print("  NOTE: no backtest behind these setups yet — observation only.")
        print("=" * 72)

        cycles = 0
        while True:
            if kill_switch.engaged:
                print("KILL_SWITCH engaged — stopping.")
                break
            try:
                runner.step(datetime.now(timezone.utc))
            except Exception as exc:  # noqa: BLE001 - surfaced, never swallowed
                print(f"STEP_ERROR: {exc.__class__.__name__}: {exc}")
            cycles += 1
            if args.max_cycles and cycles >= args.max_cycles:
                print(f"reached max-cycles={args.max_cycles}; stopping.")
                break
            time.sleep(max(1.0, args.poll_seconds))
        return 0
    except KeyboardInterrupt:
        print("\ninterrupted; shutting down.")
        return 0
    finally:
        adapter.shutdown()


def _print_event(e) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    arrow = {"SIGNAL_ARMED": "•", "INVALIDATED": "x", "EXPIRED": "·",
             "FILL_ATTEMPT": "→"}.get(e.kind, "?")
    print(f"[{ts}] {arrow} {e.kind:<13} {e.setup:<26} {e.detail}")


if __name__ == "__main__":
    raise SystemExit(main())
