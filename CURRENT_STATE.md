# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 1: Data Foundation

## Current Task

P1-003: Data Validation Engine

## Last Completed Task

P0-001: Create Project Control Pack
P0-002: Create Repository Structure
P0-003: Preserve Runtime Directory Structure
P1-001: Define Core Data Schemas
P1-002: MT5 Demo Data Adapter

## Next Task

P1-003: Data Validation Engine

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

Start P1-003:
Implement the Data Validation Engine that detects missing candles, duplicate
candles, stale data, bad OHLC, spread anomalies, and timestamp issues, and
produces a NO_TRADE status on invalid data. Build it on top of the Candle/Tick
schemas (src/data/) and the MT5 adapter output (src/broker/).

## Safety Notes

- Do not commit .env.
- Do not enable real trading.
- Do not print credentials.
- Do not place MT5 orders (data fetch / validation only).
- MT5 adapter (src/broker/) is data-read only; order_send is never called.
