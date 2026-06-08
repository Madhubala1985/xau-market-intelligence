# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 1: Data Foundation

## Current Task

P1-002: MT5 Demo Data Adapter

## Last Completed Task

P0-001: Create Project Control Pack
P0-002: Create Repository Structure
P0-003: Preserve Runtime Directory Structure
P1-001: Define Core Data Schemas

## Next Task

P1-002: MT5 Demo Data Adapter

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

Start P1-002:
Implement the MT5 demo data adapter that connects to the MT5 demo terminal,
loads demo credentials from .env (secure loading, never printed), and fetches
XAU/USD candles into the Candle schema. No order sending.

## Safety Notes

- Do not commit .env.
- Do not enable real trading.
- Do not print credentials.
- Do not place MT5 orders in P1-002 (data fetch only).
- Schemas are now defined in src/data/schemas.py; build the adapter on top of them.
