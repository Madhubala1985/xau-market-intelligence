# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 8: Trade Management

## Current Task

P8-002: Trailing Stop Engine

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

## Next Task

P8-002: Trailing Stop Engine

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

Start P8-002:
Implement the Trailing Stop Engine with structure-based, volatility-based, and
liquidity-target trailing, plus partial/runner logic. Tests: no premature
trailing, no widening stop, valid partial/runners. Build in src/trade_management/;
reuse StopPlacementEngine and structure/liquidity outputs. No order placement; no
look-ahead.

## Safety Notes

- Do not commit .env.
- Do not enable real trading; ALLOW_REAL_ORDERS must stay false.
- Do not print credentials.
- Do not place MT5 orders (trailing logic only; gateway/risk governor remain the
  only gated execution path).
- A trailing stop may only move in the trade's favor; NEVER widen a stop. No
  premature trailing before confirmation. No look-ahead.
