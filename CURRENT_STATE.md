# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 1: Data Foundation

## Current Task

P1-001: Define Core Data Schemas

## Last Completed Task

P0-001: Create Project Control Pack
P0-002: Create Repository Structure
P0-003: Preserve Runtime Directory Structure

## Next Task

P1-001: Define Core Data Schemas

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

Start P1-001:
Create schemas for Candle, Tick, SpreadSnapshot, SessionState, BrokerState, TradeDecision, and TradeRecord.

## Safety Notes

- Do not commit .env.
- Do not enable real trading.
- Do not print credentials.
- Do not place MT5 orders in P1-001.
- Do not implement strategy before schemas are defined.
