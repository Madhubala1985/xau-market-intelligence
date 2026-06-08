# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 2: Session and Timeframe Context

## Current Task

P2-001: Timeframe Aggregation

## Last Completed Task

P0-001: Create Project Control Pack
P0-002: Create Repository Structure
P0-003: Preserve Runtime Directory Structure
P1-001: Define Core Data Schemas
P1-002: MT5 Demo Data Adapter
P1-003: Data Validation Engine

## Next Task

P2-001: Timeframe Aggregation

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

Start P2-001:
Implement reliable timeframe aggregation (1M -> 5M/15M/1H/4H/Daily) on top of
the Candle schema (src/data/). Must guarantee aggregation correctness and no
future leakage (only completed source bars contribute to an aggregated bar).

## Safety Notes

- Do not commit .env.
- Do not enable real trading.
- Do not print credentials.
- Do not place MT5 orders (data / analysis only).
- MT5 adapter (src/broker/) is data-read only; order_send is never called.
- DataValidator (src/data/validation.py) emits NO_TRADE on bad data; feed
  validated candles into aggregation. No look-ahead.
