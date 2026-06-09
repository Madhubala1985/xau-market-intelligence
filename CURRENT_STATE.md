# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 10: Backtest and Validation

## Current Task

P10-002: Walk-Forward Validation

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

## Next Task

P10-002: Walk-Forward Validation

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

Start P10-002:
Implement Walk-Forward Validation that splits data into train/test windows and
validates on unseen periods. Tests: train/test split, no leakage. Build in
src/backtest/; reuse the Backtester. Strictly time-ordered splits (test always
after train); the backtester remains strictly causal within each window.

## Safety Notes

- Do not commit .env.
- Do not enable real trading; ALLOW_REAL_ORDERS must stay false.
- Do not print credentials.
- Do not place MT5 orders (simulation/validation only; no order_send).
- No leakage across folds: test windows must be strictly later than their train
  windows; never fit on test data.
