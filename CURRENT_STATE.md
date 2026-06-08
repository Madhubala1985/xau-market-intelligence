# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 3: Market Structure and Liquidity

## Current Task

P3-003: Liquidity Sweep Engine

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

## Next Task

P3-003: Liquidity Sweep Engine

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

Start P3-003:
Implement the Liquidity Sweep Engine that detects sweep, rejection, reclaim, and
displacement confirmation against the liquidity map (src/liquidity/). Tests cover
true sweep, false sweep, and no sweep. Build on the Candle schema and the
liquidity map / structure engines; no look-ahead.

## Safety Notes

- Do not commit .env.
- Do not enable real trading.
- Do not print credentials.
- Do not place MT5 orders (data / analysis only).
- MT5 adapter (src/broker/) is data-read only; order_send is never called.
- Sweep detection must not use future candles (no look-ahead); a sweep is not a
  trade by itself (15_LIQUIDITY_ENGINEERING.md).
