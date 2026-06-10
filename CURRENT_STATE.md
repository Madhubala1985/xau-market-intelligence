# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 12: Live Demo Readiness

## Current Task

DEMO-EVAL: IMPLEMENTED — serious demo evaluation engine ready; first
policy-governed supervised evaluation session pending (user-started)

## Last Completed Task

P0-P11 roadmap completed.
INT-001, RISK-001, LIVE-VERIFY-001, WINMT5-001, WINMT5-LIVE-001 completed.
LIVE-001/LIVE-002: live MT5 read-only data -> DecisionPipeline -> shadow
journal, supervised session reporting. Windows proof CLEARED (2026-06-10).
DEMO-001: 13-gate demo execution preflight; manual kill switch.
AUDIT-001: intelligence audit; RiskStateTracker + price-unit spread scoring.
DEMO-002-BLOCKERS: DemoTradePlanner (tier -> sizer -> pyramiding -> governor),
position reconciliation (fail-closed), BE/trailing proposals, NewsRiskGuard.
DEMO-002: SupervisedDemoSession + runner; close detection with real P&L;
journal collapse semantics; lot-step snapping.
DEMO-EVAL (2026-06-10): serious demo evaluation + reflection workflow:
- Session risk profiles (src/execution/session_profiles.py): smoke /
  evaluation / london / newyork / full_day. Profiles configure duration,
  polling, session order cap, and the governor/planner RiskLimits; they can
  TIGHTEN 03_RISK_POLICY demo limits, never loosen them (validated at
  construction).
- NO artificial order cap in evaluation modes: max_orders=None means the risk
  policy (3 trades/day, 2%/5% loss limits, 1 position + 1 protected add-on),
  confidence tiers, regime, and setup quality govern. max_orders=1 survives
  only in the smoke profile.
- Dry-run defect fixed: it now rehearses the FULL planner -> gateway path;
  approved plans are counted as orders_simulated (ORDER_SIMULATED) and can
  never reach order_send. Previously max_orders=0 blocked before planning.
- Mode separation: DEMO_LIVE (real MT5 demo orders, tickets journaled) vs
  DRY_RUN (simulated) in the session report; shadow stays LiveShadowSession.
- Per-cycle CycleStats (regime/session/HTF bias/confidence/spread/news/risk/
  entry action) recorded for post-session analysis.
- Post-session intelligence: scripts/demo_eval_report.py (totals,
  distributions, no-trade reasons, news/risk blocks, P&L, max drawdown,
  win/loss, mistakes, findings classified PROVEN_DEFECT /
  HIGH_CONFIDENCE_DEFECT / HYPOTHESIS / OBSERVATION / DESIGN_IMPROVEMENT) and
  scripts/demo_reflection.py (did well / too strict / too loose / missed /
  avoided correctly / backtest-first / fix-now). Offline; no self-mutation.
- Gold-intelligence audit recorded (24_INTELLIGENCE_AUDIT_ROADMAP.md §6):
  F-11 zones/premium-discount engines NOT wired into the pipeline (Design
  Improvement, backtest first), F-12 futures confirmation has no live feed,
  F-13 no dedicated dangerous-volatility classifier (implicit gates only).

## Windows Validation Proof (2026-06-10)

live_shadow_run --cycles 5 COMPLETED; live_shadow_session 5 min COMPLETED;
demo_preflight Ready: True. LIVE-001/LIVE-002/DEMO-001 proof CLEARED.

## Next Task

User runs on the Windows MT5 host (PowerShell), in order:
1. python scripts/demo_preflight.py                     (13 gates PASS)
2. python scripts/demo_session_run.py --dry-run --profile evaluation
   (verdict CLEAN, orders_simulated >= 0, zero orders_sent)
3. python scripts/demo_session_run.py --confirm "START SUPERVISED DEMO" --profile smoke
   (first real-order evidence: max ONE order)
4. python scripts/demo_eval_report.py ; python scripts/demo_reflection.py
5. If CLEAN: --profile evaluation (1h, policy-governed), then london /
   newyork / full_day sessions; evaluation + reflection after each.
Kill switch any time: New-Item -ItemType File control\KILL_SWITCH

## Current Execution Mode

DEMO_EVAL_READY (demo order path implemented and gated; user-started only)

## Real Trading

FORBIDDEN

## Demo Trading

ALLOWED only via scripts/demo_session_run.py with the exact confirmation
token, fresh READY preflight, env flags set, news source present, kill switch
absent. Supervised sessions only; the user starts every session manually.

## Paper / Shadow Trading

ALLOWED: scripts/live_shadow_run.py (journals only, never sends)

## Environment Status

- .env.example exists; .env is local only and ignored by git.
- Demo MT5 credentials only in .env; real credentials forbidden.
- WSL cannot import MetaTrader5; sessions run on the Windows MT5 host.
- Off-Windows the runners report an honest ENVIRONMENT_ISSUE (exit 2).
- Post-session reports (demo_eval_report.py, demo_reflection.py) are offline
  file readers and run on Windows or WSL.

## Safety Notes

- Do not commit .env. Do not print credentials.
- Do not enable real trading (REAL_TRADING_ENABLED / ALLOW_REAL_ORDERS).
- ExecutionGateway remains the only order pathway; RiskGovernor final
  authority; risk profiles can only tighten policy.
- Claude never starts a supervised session; the user does.
