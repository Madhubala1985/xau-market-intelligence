#!/usr/bin/env python3
r"""CONTINUOUS-001 runner: continuous MT5 trading service (Windows host only).

THE main way to run the system. Starts once and keeps running:

    connect to the MT5 account configured in .env
      -> fresh DEMO-001 preflight (refuses anything not READY)
      -> continuous loop: live XAUUSDm data -> DecisionPipeline -> planner
         (sizing + pyramiding) -> RiskGovernor -> ExecutionGateway -> orders
         on the .env account -> journal -> reconciliation -> stop management
      -> pauses while the market is closed, resumes when it opens
      -> daily evaluation + reflection reports at UTC rollover
      -> stops ONLY on kill switch, weekly-loss risk shutdown, Ctrl+C, or a
         fatal error.

Which account is traded is decided by .env (currently an Exness DEMO account,
so every order is a demo order and appears in the MT5 Toolbox/Trade tab).
Whether orders are SENT is decided by the .env execution flags:
TRADING_MODE=DEMO, REAL_TRADING_ENABLED=false, ALLOW_DEMO_ORDERS=true,
ALLOW_MT5_ORDER_SEND=true, ALLOW_REAL_ORDERS=false. Without them (or with
--dry-run) the IDENTICAL loop runs with sending disabled (plans simulated).

REAL accounts are refused at start until the real-money readiness phase is
manually approved (CLAUDE.md). No credentials are printed; the login is
masked in the banner.

Live terminal output is ON by default: startup banner + per-cycle progress.

Usage (Windows MT5 host, PowerShell):
    # continuous dry-run rehearsal (no orders possible):
    py -3.12 scripts\trading_service.py --profile continuous --dry-run --stdout-progress

    # continuous MT5 execution on the .env account:
    py -3.12 scripts\trading_service.py --profile continuous --stdout-progress

    # stop safely (service halts at the next check):
    New-Item -ItemType File control\KILL_SWITCH

Output: reports/runtime/trading_service.md/.json, daily service_eval_*/
service_reflection_* reports. Journal: logs/demo_trade_journal.jsonl.
Heartbeats while closed: logs/service_heartbeat.jsonl.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.broker.errors import BrokerError, MissingCredentialsError  # noqa: E402
from src.broker.mt5_data_adapter import (  # noqa: E402
    MT5DataAdapter,
    verify_demo_account,
)
from src.broker.mt5_settings import load_mt5_settings  # noqa: E402
from src.execution.challenge_planner import ChallengeTradePlanner  # noqa: E402
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
from src.execution.session_profiles import (  # noqa: E402
    CHALLENGE_PROFILE_NAMES,
    PROFILES,
    get_profile,
)
from src.strategy.smc_execution import make_smc_pipeline  # noqa: E402
from src.strategy.pipeline import THRESHOLD_PROFILES  # noqa: E402
from src.execution.trading_service import (  # noqa: E402
    BannerInfo,
    ProgressPrinter,
    StopReason,
    TradingService,
    mask_login,
)
from src.journal.journal import TradeJournal  # noqa: E402
from src.orderflow.macro_context import FileMacroProvider  # noqa: E402
from src.risk.adaptive_risk import CapitalPhase  # noqa: E402
from src.risk.exposure_governor import AdaptiveExposureGovernor  # noqa: E402
from src.risk.governor import RiskGovernor  # noqa: E402
from src.risk.news_guard import NewsRiskGuard  # noqa: E402

OUT_DIR = REPO_ROOT / "reports" / "runtime"
ENV_PATH = REPO_ROOT / ".env"
JOURNAL_PATH = REPO_ROOT / "logs" / "demo_trade_journal.jsonl"
HEARTBEAT_PATH = REPO_ROOT / "logs" / "service_heartbeat.jsonl"
KILL_SWITCH_PATH = REPO_ROOT / "control" / "KILL_SWITCH"
NEWS_BLOCK_PATH = REPO_ROOT / "control" / "NEWS_BLOCK"
NEWS_CALENDAR_PATH = REPO_ROOT / "configs" / "news_windows.json"

_CLEAN_STOPS = {
    StopReason.KILL_SWITCH,
    StopReason.RISK_SHUTDOWN,
    StopReason.OPERATOR_INTERRUPT,
    StopReason.MAX_CYCLES,
}


def load_env_safely(dotenv_path: Path = ENV_PATH) -> None:
    """Load .env into os.environ without printing any value."""
    if not dotenv_path.is_file():
        return
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(dotenv_path, override=False)
    except Exception:
        for raw in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--profile", default="continuous",
                        choices=sorted(PROFILES))
    parser.add_argument("--dry-run", action="store_true",
                        help="run the identical loop with order sending "
                             "DISABLED (plans simulated)")
    parser.add_argument("--stdout-progress", action="store_true", default=True,
                        help="live terminal banner + per-cycle progress "
                             "(default: on)")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress live terminal progress")
    parser.add_argument("--poll-seconds", type=float, default=None,
                        help="override the profile poll interval")
    parser.add_argument("--max-cycles", type=int, default=None,
                        help="diagnostic: stop after N cycles")
    parser.add_argument("--thresholds", default="current",
                        choices=sorted(THRESHOLD_PROFILES),
                        help="threshold profile (explicit operator choice; "
                             "default: current)")
    args = parser.parse_args()

    profile = get_profile(args.profile)
    if args.poll_seconds is not None:
        try:
            profile = profile.with_overrides(poll_seconds=args.poll_seconds)
        except ValueError as exc:
            print(f"REFUSED: {exc}")
            return 2

    load_env_safely()

    try:
        import MetaTrader5  # type: ignore  # noqa: F401
    except Exception as exc:
        print(f"ENVIRONMENT_ISSUE: MetaTrader5 not importable "
              f"({exc.__class__.__name__}); run on the Windows MT5 host.")
        return 2

    try:
        settings = load_mt5_settings()  # demo-only configuration enforced
    except MissingCredentialsError as exc:
        print(f"CONFIG_INCOMPLETE: missing {', '.join(exc.missing)} "
              f"(set them in .env; values are never printed)")
        return 2

    canonical = settings.canonical_symbol
    kill_switch = KillSwitch(KILL_SWITCH_PATH)
    news_guard = NewsRiskGuard(block_path=NEWS_BLOCK_PATH,
                               calendar_path=NEWS_CALENDAR_PATH)
    printer = ProgressPrinter(enabled=not args.quiet)

    adapter = MT5DataAdapter(settings)
    exit_code = 0
    try:
        adapter.connect()
        client = adapter._mt5

        # Readiness gate: REAL accounts are refused until manually approved.
        account_type = verify_demo_account(client)

        # Fresh DEMO-001 preflight ON THIS START; refuse anything not READY.
        preflight = DemoPreflight(
            env=os.environ, broker_symbol=settings.symbol, client=client,
            journal_probe_path=REPO_ROOT / "logs" / "demo_preflight_probe.jsonl",
            kill_switch=kill_switch,
        ).run()
        if not preflight.ready:
            failed = [g.name for g in preflight.gates if g.status.value != "PASS"]
            print(f"PREFLIGHT_FAILED: gates not PASS: {failed}")
            return 2

        flags = ExecutionFlags() if args.dry_run else load_execution_flags(os.environ)
        limits = profile.risk_limits(canonical)
        gateway = ExecutionGateway(
            RiskGovernor(limits), flags, client,
            expected_symbol=canonical, broker_symbol=settings.symbol,
            kill_switch=kill_switch,
        )
        journal = TradeJournal(JOURNAL_PATH)
        # SMC-EXECUTION-001: the challenge profiles (smc_challenge and its
        # deprecated alias demo_challenge) swap the DECISION layer for the
        # institutional SMC execution pipeline + fixed-lot planner (no
        # exposure governor) while every safety layer stays identical: same
        # session, gateway, kill switch, journal, reconciliation, stops.
        challenge_mode = profile.name in CHALLENGE_PROFILE_NAMES
        if challenge_mode:
            if profile.name == "smc_v2":
                # SMC-V2-001: day-narrative brain; knobs are the
                # walk-forward winner from reports/runtime/v2_sweep.md —
                # changed only with fresh replay evidence.
                from src.strategy.smc_v2 import make_smc_v2_pipeline
                pipeline = make_smc_v2_pipeline(
                    canonical, max_spread_price=profile.max_spread_price,
                )
            else:
                pipeline = make_smc_pipeline(
                    canonical, max_spread_price=profile.max_spread_price,
                )
            planner = ChallengeTradePlanner(limits=limits)
            exposure_governor = None
        else:
            pipeline = make_live_pipeline(
                canonical, max_spread_price=profile.max_spread_price,
                threshold_profile=args.thresholds,
            )
            planner = DemoTradePlanner(limits=limits)
            # Adaptive Exposure Policy (OPERATIONAL-001): condition-driven
            # entry allowance, hard-bounded by the profile.
            exposure_governor = AdaptiveExposureGovernor()
        session = SupervisedDemoSession(
            adapter=adapter,
            pipeline=pipeline,
            planner=planner,
            gateway=gateway,
            journal=journal,
            symbol=settings.symbol,
            confirmation=CONFIRMATION_TOKEN,
            preflight=preflight,
            news_guard=news_guard,
            kill_switch=kill_switch,
            max_orders=profile.max_orders,
            profile_name=profile.name,
            # Adaptive Demo Risk Policy: this is the STATIC ceiling the
            # pipeline/governor enforce; the AdaptiveRiskEngine's per-phase
            # ceilings and evidence budget decide the actual risk below it.
            risk_pct=limits.max_risk_per_trade,
            exposure_governor=exposure_governor,
            hard_max_trades=limits.max_trades_per_day,
            hard_max_open=limits.max_open_trades,
            max_daily_loss=limits.max_daily_loss,
            max_weekly_loss=limits.max_weekly_loss,
        )

        now = datetime.now(timezone.utc)
        news = news_guard.assess(now)
        broker_state = adapter.fetch_broker_state(now)
        equity = broker_state.equity or broker_state.balance or 0.0
        phase = CapitalPhase.of(equity)
        if flags.demo_send_enabled:
            mode_label = (
                f"EXECUTION — orders WILL be sent to the .env account "
                f"({account_type})"
            )
        else:
            mode_label = "DRY_RUN — sending disabled; approved plans simulated"
        banner = BannerInfo(
            profile=profile.name,
            execution_mode=mode_label,
            account_login_masked=mask_login(settings.login),
            account_type=account_type,
            server=settings.server,
            symbol=settings.symbol,
            risk_summary=(
                f"{limits.max_risk_per_trade:.2%}/trade, "
                f"daily {limits.max_daily_loss:.1%}, "
                f"weekly {limits.max_weekly_loss:.1%}, "
                f"{limits.max_trades_per_day} trades/day, "
                f"{limits.max_open_trades} open max, "
                f"spread<= {limits.max_spread}"
            ),
            news_status=f"{getattr(news, 'status', '') or 'n/a'} ({news.detail})",
            kill_switch_status=(
                "ENGAGED (service will stop immediately)"
                if kill_switch.engaged else "absent"
            ),
            journal_path=str(JOURNAL_PATH.relative_to(REPO_ROOT)),
            report_dir=str(OUT_DIR.relative_to(REPO_ROOT)),
            macro_status=FileMacroProvider(
                REPO_ROOT / "configs" / "macro_context.json"
            ).assess(now).summary(),
            capital_phase=f"{phase.value} (equity ~{equity:,.0f})",
            thresholds=(
                "smc_challenge: HTF+killzone/liquidity+SMC anchor+local "
                "trigger required; fixed lots 0.05/0.10; tactical stops; "
                "add-ons only onto protected winners (>=0.5R/BE); max 3 open"
                if challenge_mode else
                f"profile={args.thresholds} "
                + " ".join(f"{k}={v}" for k, v in
                           THRESHOLD_PROFILES[args.thresholds].items())
            ),
        )

        def tick_age(now_utc: datetime):
            try:
                tick = adapter.fetch_tick()
                return max(0.0, (now_utc - tick.time_utc).total_seconds())
            except BrokerError:
                return None

        service = TradingService(
            session=session,
            journal=journal,
            kill_switch=kill_switch,
            profile=profile,
            printer=printer,
            banner=banner,
            report_dir=OUT_DIR,
            heartbeat_path=HEARTBEAT_PATH,
            tick_age=tick_age,
            max_cycles=args.max_cycles,
            warmstart=True,
        )
        report = service.run()
        exit_code = 0 if report.stop_reason in _CLEAN_STOPS else 2
        print(f"Stop reason: {report.stop_reason}  cycles={report.cycles}  "
              f"orders_sent={report.orders_sent}  "
              f"orders_simulated={report.orders_simulated}")
        print(f"Service report: {OUT_DIR.relative_to(REPO_ROOT)}/trading_service.md")
    except (BrokerError, RuntimeError, ValueError) as exc:
        print(f"FATAL: {exc}")
        exit_code = 2
    finally:
        adapter.shutdown()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
