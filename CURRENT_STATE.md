# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 5: Order-Flow Proxy and Futures Context

## Current Task

P5-001: Order-Flow Proxy Engine

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

## Next Task

P5-001: Order-Flow Proxy Engine

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

Start P5-001:
Implement the Order-Flow Proxy Engine that uses MT5 tick volume, spread behavior,
tick movement, and an optional delta/CVD proxy cautiously. Proxy values must be
calculated but must NOT produce a direct trade signal alone (INIT-005). Build on
the Candle/Tick schemas (src/data/); no look-ahead.

## Safety Notes

- Do not commit .env.
- Do not enable real trading.
- Do not print credentials.
- Do not place MT5 orders (data / analysis only).
- MT5 adapter (src/broker/) is data-read only; order_send is never called.
- Order-flow proxy is a proxy only (INIT-005): no direct trade signal from proxy
  alone; no look-ahead.
