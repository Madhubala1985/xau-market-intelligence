# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 11: Live Shadow and Real Readiness

## Current Task

P11-001: Live Shadow Mode

## Last Completed Task

P0-001: Create Project Control Pack
P0-002: Create Repository Structure
P0-003: Preserve Runtime Directory Structure
P1-001: Define Core Data Schemas
P1-002: MT5 Demo Data Adapter
P1-003: Data Validation Engine
P2-001: Timeframe Aggregation
P2-002: Session/Kill-Zone Engine
P3-001: Swing and Structure Engine
P3-002: Liquidity Map Engine
P3-003: Liquidity Sweep Engine
P3-004: FVG / Order Block / Supply-Demand Engine
P3-005: Premium/Discount Engine
P4-001: Daily and 4H Bias Engine
P4-002: Regime Engine
P5-001: Order-Flow Proxy Engine
P5-002: Gold Futures Confirmation Layer
P6-001: Trade Hypothesis Engine
P6-002: Confidence and Uncertainty Engine
P7-001: Risk Governor
P7-002: Position Sizing
P7-003: MT5 Demo Execution Gateway
P8-001: Stop Placement Intelligence
P8-002: Trailing Stop Engine
P9-001: Trade Journal
P9-002: Reflection Engine
P10-001: Backtesting Engine
P10-002: Walk-Forward Validation

## Next Task

P11-001: Live Shadow Mode

## Current Execution Mode

DEMO_CONFIGURED_BUT_NOT_YET_TESTED

## Real Trading

FORBIDDEN

## Demo Trading

ALLOWED ONLY AFTER RISK GOVERNOR AND EXECUTION GATEWAY SAFETY CHECKS

## Paper Trading

ALLOWED

## Environment Status

- .env.example exists.
- .env is local only and ignored by git.
- Demo MT5 credentials may be stored only in .env.
- Real credentials are forbidden.

## Next Exact Action

Start P11-001:
Implement Live Shadow Mode that runs live market analysis and logs decisions
WITHOUT sending real-money orders. Tests: live decisions logged, real orders not
sent. Build in a suitable module (e.g., src/execution/ shadow runner or a new
shadow module); reuse the strategy/decision pipeline, journal, and the gated
ExecutionGateway in dry-run/demo. No real orders ever.

## Safety Notes

- Do not commit .env.
- Do not enable real trading; ALLOW_REAL_ORDERS must stay false.
- Do not print credentials.
- Shadow mode must NEVER send real orders; decisions are analyzed and logged
  only (and at most routed to the gated demo gateway in dry-run).
- Real orders not sent must be proven by tests.
