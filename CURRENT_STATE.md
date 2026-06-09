# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 7: Risk and Execution

## Current Task

P7-003: MT5 Demo Execution Gateway

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

## Next Task

P7-003: MT5 Demo Execution Gateway

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

Start P7-003:
Implement the MT5 Demo Execution Gateway that places MT5 demo trades ONLY after
risk-governor approval and only when all safety flags are enabled. Use an
injected/mock MT5 client (Windows-only package). Tests: wrong symbol blocked, no
SL blocked, duplicate blocked, order state logged, no credentials printed. Build
in src/execution/; reuse RiskGovernor, TradeDecision, BrokerState.

## Safety Notes

- Do not commit .env.
- Do not enable real trading; ALLOW_REAL_ORDERS must stay false.
- Do not print credentials.
- Demo order_send is gated behind risk approval AND the demo safety flags
  (TRADING_MODE=DEMO, REAL_TRADING_ENABLED=false, ALLOW_DEMO_ORDERS=true,
  ALLOW_MT5_ORDER_SEND=true). Default must never send; tests use a fake client.
- Risk governor has final authority. Do not weaken/bypass risk checks or tests.
