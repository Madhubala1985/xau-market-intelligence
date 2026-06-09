# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 12: Live Demo Readiness

## Current Task

WINMT5-LIVE-001: Execute Windows MT5 Demo Validation

## Last Completed Task

P0-P11 roadmap completed.
INT-001: DecisionPipeline integration completed.
RISK-001: Leverage-Aware Sizing and Protected Pyramiding completed.
LIVE-VERIFY-001: Implementation Evidence Pack completed.
WINMT5-001: MT5 validation tooling completed, but live Windows MT5 proof is still pending.
WINMT5-001 (case fix): broker symbols now preserve exact case (e.g. Exness XAUUSDm) for all MT5 API calls; uppercase is used only for canonical validation.

## Next Task

WINMT5-LIVE-001

## Current Execution Mode

DEMO_CONFIGURED_BUT_MT5_LIVE_PROOF_PENDING

## Real Trading

FORBIDDEN

## Demo Trading

READ-ONLY MT5 VALIDATION ONLY

## Paper / Shadow Trading

PAUSED UNTIL MT5 DEMO VALIDATION IS PROVEN

## Environment Status

- .env.example exists.
- .env is local only and ignored by git.
- Demo MT5 credentials may be stored only in .env.
- Real credentials are forbidden.
- WSL cannot import MetaTrader5 directly.
- Windows MT5 validation must be run using Windows Python or a safe Windows-side runner.

## Next Exact Action

Run the Windows-side MT5 validation script and prove:

1. MT5 initializes.
2. Exness demo login works.
3. Account is not real-money.
4. XAU/USD symbol is detected.
5. symbol_info is read.
6. candles are fetched.
7. spread is read.
8. no order_send is called.
9. no credentials are printed.

## Safety Notes

- Do not commit .env.
- Do not enable real trading.
- Do not print credentials.
- Do not place demo orders.
- Do not call order_send.
- Do not continue LIVE-001 until MT5 demo validation is proven.
