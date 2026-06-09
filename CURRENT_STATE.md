# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 12: Live Demo Readiness

## Current Task

LIVE-VERIFY-001: Generate Implementation Evidence Pack

## Last Completed Task

P0-P11 roadmap completed.
INT-001: DecisionPipeline integration completed.
RISK-001: Leverage-aware sizing and protected pyramiding completed.

## Next Task

LIVE-VERIFY-001

## Current Execution Mode

DEMO_CONFIGURED_BUT_NOT_YET_LIVE_VALIDATED

## Real Trading

FORBIDDEN

## Demo Trading

ALLOWED ONLY AFTER PHASE 12 GATES PASS

## Paper / Shadow Trading

ALLOWED

## Environment Status

- .env.example exists.
- .env is local only and ignored by git.
- Demo MT5 credentials may be stored only in .env.
- Real credentials are forbidden.
- MT5 live validation is not yet proven in this phase.

## Next Exact Action

Start LIVE-VERIFY-001:
Generate a compact implementation evidence pack (implemented / tested / stubbed /
live-proven / not-yet-live-proven modules) under reports/runtime/.

## Safety Notes

- Do not commit .env.
- Do not enable real trading.
- Do not print credentials.
- Do not place orders in LIVE-VERIFY-001.
- Do not start demo orders until WINMT5-001, LIVE-001, LIVE-002, and DEMO-001 pass.
