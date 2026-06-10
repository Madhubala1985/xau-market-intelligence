# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 12: Live Demo Readiness — continuous service operational

## Current Task

CONTINUOUS-001: IMPLEMENTED — continuous MT5 trading service is the MAIN
mode; first continuous run on the Windows MT5 host pending (user-started)

## Last Completed Task

P0-P11 roadmap, INT-001, RISK-001, LIVE-VERIFY-001, WINMT5-001,
WINMT5-LIVE-001, LIVE-001, LIVE-002, DEMO-001, AUDIT-001,
DEMO-002-BLOCKERS, DEMO-002, DEMO-EVAL completed (see 11_DECISION_LOG.md).
CONTINUOUS-001 (2026-06-10, decision 2026-06-10-06):
- ONE continuous MT5 trading service (scripts/trading_service.py +
  src/execution/trading_service.py): starts once, connects to the MT5
  account configured in .env (currently Exness DEMO -> demo orders), runs
  the DecisionPipeline continuously, executes approved trades through the
  SAME planner -> governor -> gateway stack (TradingService drives
  SupervisedDemoSession.run_cycle(); zero duplicated execution logic),
  reconciles positions and detects closes from MT5 history every cycle,
  manages break-even/trailing stops continuously.
- No fixed duration, no artificial order cap: risk policy governs (3
  trades/day, 2% daily pauses entries until UTC rollover [DAY_PAUSED], 5%
  weekly STOPS the service [RISK_SHUTDOWN]). Stops cleanly on kill switch,
  weekly-loss shutdown, Ctrl+C, or fatal error.
- Market-closed handling: MarketSchedule (weekend Fri 21:00 -> Sun 22:05
  UTC + daily break 21:00 -> 22:05 UTC) plus tick-staleness ground truth;
  prints MARKET CLOSED / FEED STALE, heartbeats to
  logs/service_heartbeat.jsonl, resumes automatically.
- Terminal observability: startup banner (masked login, account type
  verified non-real, server, symbol, mode, risk limits, news, kill switch,
  paths, stop instructions) + per-cycle progress (market state, bid/ask/
  spread, regime, HTF bias, decision + exact no-trade reason, confidence,
  positions with floating P&L, orders sent/simulated, trades today, daily
  P&L, risk/news/kill state, next poll). Sent orders print their MT5
  ticket + Toolbox/Trade-tab hint.
- Daily rollover writes service_eval_YYYYMMDD + service_reflection_YYYYMMDD
  (same evaluator as DEMO-EVAL); trading_service.md/.json written on stop.
- PROVEN DEFECT F-14 FIXED before any live order: the gateway built
  order_send requests with the canonical symbol ("XAUUSDM") — MT5 symbols
  are case-sensitive, the terminal would have rejected it. Requests now
  carry the exact broker case ("XAUUSDm"); verify_demo_account is shared in
  src/broker/mt5_data_adapter.py (REAL accounts refused).
- 583 tests pass; pre_demo_safety_check.sh passes.

## Next Task

User runs on the Windows MT5 host (PowerShell):
1. py -3.12 scripts\demo_preflight.py                       (13 gates PASS)
2. py -3.12 scripts\trading_service.py --profile continuous --dry-run --stdout-progress
   (watch a few cycles; verdicts/plans visible; zero orders; Ctrl+C to stop)
3. Set the demo execution flags in .env, then:
   py -3.12 scripts\trading_service.py --profile continuous --stdout-progress
   (supervise initially; orders appear in MT5 Toolbox/Trade tab)
4. Stop: New-Item -ItemType File control\KILL_SWITCH
   Resume: Remove-Item control\KILL_SWITCH ; restart the service
5. Review reports/runtime/trading_service.md, daily service_eval_* /
   service_reflection_*, logs/demo_trade_journal.jsonl.
Bounded sessions (scripts/demo_session_run.py) and shadow mode remain
available as validation tools.

## Current Execution Mode

CONTINUOUS_SERVICE_READY (gated by .env flags + fresh preflight + kill
switch; user-started only)

## Real Trading

FORBIDDEN (REAL accounts refused at start; real flags abort the gateway)

## Demo Trading

ALLOWED via scripts/trading_service.py (continuous, MAIN mode) or
scripts/demo_session_run.py (bounded sessions) — both require a fresh READY
preflight, the .env execution flags for sending, an available news source,
and an absent kill switch.

## Paper / Shadow Trading

ALLOWED: scripts/live_shadow_run.py (journals only, never sends)

## Environment Status

- .env.example exists; .env is local only and ignored by git.
- The service trades the account configured in .env (currently Exness
  DEMO); credentials are never printed (login masked in the banner).
- WSL cannot import MetaTrader5; the service runs on the Windows MT5 host
  (off-Windows it reports an honest ENVIRONMENT_ISSUE, exit 2).
- Post-session report scripts run anywhere (offline file readers).

## Safety Notes

- Do not commit .env. Do not print credentials.
- Do not enable real trading (REAL_TRADING_ENABLED / ALLOW_REAL_ORDERS).
- ExecutionGateway remains the only order pathway; RiskGovernor final
  authority; profiles can only tighten 03_RISK_POLICY.
- Claude never starts the service; the user does.
