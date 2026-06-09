# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 12: Live Demo Readiness

## Current Task

DEMO-002: Supervised MT5 demo trading (BLOCKED until gates pass; see blockers)

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

## Next Task

1. User runs the LIVE-002 supervised session on the Windows MT5 host.
2. User runs DEMO-001 preflight on the Windows MT5 host:
   python scripts/demo_preflight.py
   (Preflight passes only there; on WSL the MT5 gates are SKIPPED = NOT ready.)
3. DEMO-002 only after both are clean and the user manually starts it.

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
