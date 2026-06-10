# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 12: Live Demo Readiness — continuous service operational

## Current Task

INTELLIGENCE-001: IMPLEMENTED — graded confluence, MTF alignment, and
adaptive risk are wired into the live decision path; restart the continuous
service and collect evidence (user-started)

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

INTELLIGENCE-001 (2026-06-10, decision 2026-06-10-07) — live-evidence audit
of 170+ no-trade CHOPPY cycles found and fixed the root causes:
- PROVEN: regime classified the whole 25h M5 window (flips>=2 => CHOPPY
  almost always) — now classifies the recent ~5h window; PROVEN: the
  hypothesis engine hard-blocked CHOPPY — now a graded gate (tradeable chop
  subtype + confluence >= 0.65 may pass; NEWS_RISK/NO_TRADE never).
- ChopClassifier subtypes: DANGEROUS_CHOP / LOW_QUALITY_CHOP (hard block);
  LIQUIDITY_CHOP_WITH_SWEEP / TRAP_REVERSAL_FROM_CHOP /
  BREAKOUT_EXPANSION_FROM_CHOP / CONTINUATION_AFTER_CHOP (candidates).
- MtfAlignmentEngine: D1/H4/H1/M15/M5 (H1+M15 honest M5 aggregations) ->
  alignment score + direction; can direct when the old D1+H4 combo is
  neutral; never upgrades the NO_TRADE data-safety state.
- ConfluenceEngine: graded scoring of sweep, BOS/CHOCH, FVG, order blocks,
  premium/discount, displacement, session, spread, orderflow proxy, MTF —
  with per-component statuses and explicit missing-evidence reporting.
- Second setup type: sweepless BOS-continuation (displacement >= 1.5x +
  confluence >= 0.60 + swing invalidation). Sweep-reclaim remains primary.
- AdaptiveRiskEngine replaces static 0.5%: capital phases ($2k->10k->15k->
  25k+), expansion only on strong evidence (max x1.65 of base), multiplicative
  contraction on losses/drawdown/uncertainty/spread/exposure, zero budget on
  unclear news or untradeable regime, HARD-CLAMPED to the 0.5% policy cap.
  Budget feeds both the pipeline sizer and the planner hard cap (tighten-only).
- Terminal now shows per cycle: MTF row, intel row (sweep/BOS/FVG/OB/PD/
  displacement/flow), confluence + risk tier/% + chop subtype + regime
  reason, and for NO_TRADE the exact missing evidence.
- Opportunity audit: after 60 active-session cycles without an entry, a
  classified report (NO_TRADE_CORRECT / POSSIBLY_TOO_STRICT / MIXED) is
  written to reports/runtime/opportunity_audit_*.md/json.
- 634 tests pass; pre_demo_safety_check.sh passes.

## Next Task

User restarts the continuous service on the Windows MT5 host (PowerShell):
1. Stop the running service if any: New-Item -ItemType File control\KILL_SWITCH
   then Remove-Item control\KILL_SWITCH once stopped.
2. py -3.12 scripts\trading_service.py --profile continuous --stdout-progress
   (or --dry-run first to watch the new reasoning without orders)
3. Collect evidence over full London+NY sessions:
   - per-cycle MTF/intel/confluence/risk lines (regimes should now vary,
     conf/unc should move, chop subtypes visible),
   - any ORDER SENT tickets vs MT5 Toolbox/Trade tab,
   - reports/runtime/opportunity_audit_*.md if long no-trade stretches recur,
   - daily service_eval_* / service_reflection_* reports.
4. Next implementation candidates: BACKTEST-001 (calibrate the 0.65/0.60/
   1.5x thresholds on historical XAUUSDm data), NEWS-001 (real macro feed).

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
