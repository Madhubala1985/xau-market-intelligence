# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 12: Live Demo Readiness

## Current Task

DEMO-002: IMPLEMENTED — awaiting the first supervised demo run (user-started)

## Last Completed Task

P0-P11 roadmap completed.
INT-001: DecisionPipeline integration completed.
RISK-001: Leverage-Aware Sizing and Protected Pyramiding completed.
LIVE-VERIFY-001: Implementation Evidence Pack completed.
WINMT5-001: MT5 validation tooling completed (incl. case-sensitive broker symbol fix).
WINMT5-LIVE-001: PROVEN on Windows PowerShell — outcome VALIDATED, symbol XAUUSDm,
Exness demo account verified non-real, contract_size=100.0, digits=3, point=0.001,
volume_min=0.01, volume_step=0.01, candles fetched, spread read, no order_send.
LIVE-001: live MT5 read-only data connected to DecisionPipeline + ShadowRunner
(LiveShadowSession, make_live_pipeline, scripts/live_shadow_run.py). Smoke run
supports --cycles N or --duration-minutes N. No orders, no order_send.
LIVE-002: supervised session support added — per-cycle confidence, uncertainty,
risk action/reasons in the cycle results and the markdown/json session report;
--report-name live_shadow_session for LIVE-002 evidence. The actual short
supervised session must be run manually on the Windows MT5 host.
DEMO-001: demo execution preflight implemented (scripts/demo_preflight.py).
12 gates: 5 env flags, demo account, XAUUSDm symbol, governor blocks no-SL,
gateway stop-loss mandatory, journal writable, state persistence, manual kill
switch (control/KILL_SWITCH, honored by ExecutionGateway). No orders placed.
Also fixed a .gitignore defect: !logs/ negation was un-ignoring runtime logs.
AUDIT-001: intelligence audit completed (24_INTELLIGENCE_AUDIT_ROADMAP.md).
Fixed two High-Confidence Defects: (1) governor loss-limit inputs were
permanently zero in the live loop — added RiskStateTracker (journal-driven
daily/weekly loss, trades/day, loss streak, open symbols) wired into
LiveShadowSession; (2) execution-quality scoring used a points spread scale on
price-unit live data — DecisionPipeline now takes max_spread, aligned with the
governor in make_live_pipeline. DEMO-002 blockers recorded in the audit:
RISK-001 sizing/pyramiding unwired (F-3), no open-trade management loop (F-4),
news protection unfed (F-5).

## Windows Validation Proof (2026-06-10)

All three manual validations PASSED on the Windows MT5 host (PowerShell):
1. live_shadow_run --cycles 5 -> COMPLETED (reports/runtime/live_shadow_run.*)
2. live_shadow_run --duration-minutes 5 --report-name live_shadow_session
   -> COMPLETED (reports/runtime/live_shadow_session.*)
3. demo_preflight -> Ready: True (reports/runtime/demo_preflight.*)
LIVE-001, LIVE-002, and DEMO-001 Windows proof is CLEARED.

## DEMO-002 Blocker Implementation (2026-06-10)

F-3/F-4/F-5 implemented (commit DEMO-002-BLOCKERS):
- DemoTradePlanner: tier -> LeverageAwareSizer (cap = min(tier cap, governor
  budget)) -> PyramidingGuard (protected add-ons only) -> RiskGovernor final.
- Position safety: fetch_positions (read-only), PositionReconciler (orphans
  fail-closed), PositionProtectionManager (BE/trailing stop proposals only).
- NewsRiskGuard: manual block file + static calendar; UNKNOWN state blocks
  order planning (fail-closed); wired into LiveShadowSession.

## DEMO-002 Implementation (2026-06-10)

SupervisedDemoSession (src/execution/demo_session.py) + scripts/demo_session_run.py:
- requires EXACT confirmation token "START SUPERVISED DEMO" (or --dry-run),
- runs a FRESH DEMO-001 preflight every start; refuses anything not READY
  (preflight now includes a 13th gate: news_source_available),
- per cycle: kill-switch check -> close detection (real P&L from deal history)
  -> reconciliation (orphans fail closed) -> pipeline decision (journaled) ->
  break-even/trailing stop updates ONLY via gateway.modify_stop (never widens,
  never removes) -> entry via DemoTradePlanner -> ExecutionGateway,
- FILLED orders journaled with their MT5 ticket (notes="ticket=<n>"),
- max_orders cap (first run: 1), 8h hard session ceiling, session report with
  events, verdict CLEAN / HALTED_BY_KILL_SWITCH / ATTENTION_REQUIRED.
Integration defects fixed: gateway duplicate check now honors guard-approved
protected add-ons; journal append-only streams collapse to latest-per-record_id
(closed trades no longer block forever); stopped-out positions auto-close in
the journal with real P&L (loss limits see real losses); order volume snaps
down to the broker lot step; sizing reduction applied once (not twice).

## Next Task

User runs on the Windows MT5 host, in order:
1. python scripts/demo_preflight.py            (13 gates, needs news calendar)
2. python scripts/demo_session_run.py --dry-run --duration-minutes 10
3. python scripts/demo_session_run.py --confirm "START SUPERVISED DEMO" --duration-minutes 60 --max-orders 1
Then record evidence and review the session report before any longer run.

## Current Execution Mode

LIVE_SHADOW_READY (read-only; no order path enabled)

## Real Trading

FORBIDDEN

## Demo Trading

READ-ONLY DATA ONLY (no demo orders until DEMO-001 preflight passes)

## Paper / Shadow Trading

ALLOWED: live shadow via scripts/live_shadow_run.py (journals only, never sends)

## Environment Status

- .env.example exists.
- .env is local only and ignored by git.
- Demo MT5 credentials may be stored only in .env.
- Real credentials are forbidden.
- WSL cannot import MetaTrader5; live runs happen on the Windows MT5 host.
- Off-Windows the runner reports an honest ENVIRONMENT_ISSUE (exit 2).

## Next Exact Action

On the Windows MT5 host run a SHORT smoke validation first:

    python scripts/live_shadow_run.py --cycles 5

Then the short supervised LIVE-002 session:

    python scripts/live_shadow_run.py --duration-minutes 5 --poll-seconds 60 --report-name live_shadow_session

Review reports/runtime/live_shadow_session.md (outcome COMPLETED, orders_sent 0)
and logs/live_shadow_journal.jsonl. Then continue DEMO-001 preflight.

## Safety Notes

- Do not commit .env.
- Do not enable real trading.
- Do not print credentials.
- Do not place demo orders.
- Do not call order_send.
- ExecutionGateway remains the only order pathway; it is not enabled.
- RiskGovernor remains final authority.
