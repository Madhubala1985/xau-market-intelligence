# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 2: Session and Timeframe Context

## Current Task

P2-002: Session/Kill-Zone Engine

## Last Completed Task

P0-001: Create Project Control Pack
P0-002: Create Repository Structure
P0-003: Preserve Runtime Directory Structure
P1-001: Define Core Data Schemas
P1-002: MT5 Demo Data Adapter
P1-003: Data Validation Engine
P2-001: Timeframe Aggregation

## Next Task

P2-002: Session/Kill-Zone Engine

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

Start P2-002:
Implement the Session/Kill-Zone Engine that classifies Asian, London, New York,
London-New-York overlap, and low-liquidity periods, and tracks session
highs/lows. Map normalized (UTC) timestamps to sessions (06_DATA_POLICY.md
timestamp policy; 14_SESSION_KILLZONE_POLICY.md). Build on the Candle schema and
SessionState (src/data/).

## Safety Notes

- Do not commit .env.
- Do not enable real trading.
- Do not print credentials.
- Do not place MT5 orders (data / analysis only).
- MT5 adapter (src/broker/) is data-read only; order_send is never called.
- Session classification must use normalized UTC time; no look-ahead.
