# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 12: Live Demo Readiness

## Current Task

LIVE-002: Run supervised live shadow session

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

## Next Task

LIVE-002 (short supervised live shadow validation), then DEMO-001 preflight.

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

or

    python scripts/live_shadow_run.py --duration-minutes 5 --poll-seconds 60

Then review reports/runtime/live_shadow_run.md and logs/live_shadow_journal.jsonl.
Record the result for LIVE-002.

## Safety Notes

- Do not commit .env.
- Do not enable real trading.
- Do not print credentials.
- Do not place demo orders.
- Do not call order_send.
- ExecutionGateway remains the only order pathway; it is not enabled.
- RiskGovernor remains final authority.
