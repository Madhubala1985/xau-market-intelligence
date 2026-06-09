# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 12: Live Demo Readiness

## Current Task

WINMT5-001: Validate MT5 Demo Connectivity

## Last Completed Task

P0-P11 roadmap completed.
INT-001: DecisionPipeline integration completed.
RISK-001: Leverage-aware sizing and protected pyramiding completed.
LIVE-VERIFY-001: Implementation evidence pack generator completed.

## Next Task

WINMT5-001

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

Start WINMT5-001:
Validate MT5 demo terminal connectivity and XAU/USD read-only data on the Windows
MT5 host (init/login, demo account, symbol info, candles, spread, account info),
with NO order_send and no credentials printed. If MetaTrader5 cannot import in
WSL, create a Windows-side runner / safe bridge plan (22_MT5_WINDOWS_VALIDATION.md).

The implementation evidence pack is regenerated with:
  python scripts/generate_evidence_pack.py
Output lands in reports/runtime/ (git-ignored runtime artifact).

## Safety Notes

- Do not commit .env.
- Do not enable real trading.
- Do not print credentials.
- Do not place orders. Do not call order_send in WINMT5-001 (data validation only).
- Do not start demo orders until WINMT5-001, LIVE-001, LIVE-002, and DEMO-001 pass.
