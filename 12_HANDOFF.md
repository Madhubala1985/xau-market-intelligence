# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 4: Regime and Bias

## Current Task ID:
P4-001

## Current Task Goal:
Daily and 4H Bias Engine — classify higher-timeframe bias as bullish, bearish, neutral, or no-trade.

## Current Status:
P3-005 complete. Premium/discount engine implemented and tested. Phase 3 finished.

---

# Completed Work

- P0-000 completed: repository environment initialized.
- P0-001 completed: master control pack created.
- P0-002 completed: repository structure created.
- P0-003 completed: runtime directory structure preserved.
- P1-001 completed: core data schemas defined and tested.
- P1-002 completed: MT5 demo data adapter (data fetch only) implemented and tested.
- P1-003 completed: data validation engine implemented and tested.
- P2-001 completed: timeframe aggregation implemented and tested.
- P2-002 completed: session/kill-zone engine implemented and tested.
- P3-001 completed: swing & market-structure engine implemented and tested.
- P3-002 completed: liquidity map engine implemented and tested.
- P3-003 completed: liquidity sweep engine implemented and tested.
- P3-004 completed: FVG / order block / supply-demand engine implemented and tested.
- P3-005 completed: premium/discount engine implemented and tested.

## P3-005 Details

Files added/changed:
- src/structure/premium_discount.py — PremiumDiscountEngine + DealingRange, PremiumDiscountBand, PriceZone, DEFAULT_SEGMENTS.
- src/structure/__init__.py — export premium/discount API.
- tests/test_premium_discount.py — 11 tests (correct zone mapping).

Design notes:
- DealingRange(high, low) with equilibrium = 50% midpoint; rejects degenerate (high <= low).
- classify(range, price): discount below equilibrium, premium above, EQUILIBRIUM within a configurable band around 50% (default 0 -> exact midpoint). Prices outside the range still map (frac<0 discount, frac>1 premium).
- segments(range): Gann-box-style bands at configurable fractions (default quartiles 0/25/50/75/100%), each labeled and classified premium/discount/equilibrium.
- range_from_candles(candles): auto-selects the most recent confirmed swing high and swing low (reuses P3-001). Returns None if no swings or degenerate. No look-ahead (confirmed swings only).

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 164 passed (11 premium/discount + 11 zones + 8 sweep + 9 liquidity + 8 structure + 27 sessions + 22 aggregation + 17 validation + 21 adapter + 29 schema + 1 structure-dirs).

Errors: none.

---

# Next Task

## Task:
P4-001: Daily and 4H Bias Engine

## Goal:
Classify higher-timeframe bias as bullish, bearish, neutral, or no-trade.

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- likely src/regime/ + src/utils/ + tests/ (src/regime/ exists). Reuse src/structure/ (structure final_bias, premium/discount) and src/data/aggregation.py. Do not touch src/execution|risk|strategy.

## Tests:
- bias cases (bullish / bearish / neutral / no-trade).

## Notes for P4-001:
- Derive HTF bias from market structure (P3-001 final_bias / BOS-CHOCH sequence) on Daily and 4H, optionally combined with premium/discount location.
- Output one of: BULLISH, BEARISH, NEUTRAL, NO_TRADE. Consider a no-trade when structure is unclear / conflicting.
- No look-ahead; reuse the existing Bias enum from src/structure/market_structure.py where possible.

---

# Current Known Risks

- Real-money trading is forbidden.
- Demo order execution must not be implemented (data / analysis only).
- Exness/MT5 credentials must not be committed and must never be printed.
- .env must remain local only.
- MetaTrader5 cannot be imported on this Linux/WSL host; keep using dependency injection for tests.
- Analysis engines must avoid look-ahead (only past/known candles); preserve prefix stability.
- No live self-mutation is allowed.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, and 10_TASK_QUEUE.md.

Continue P4-001 only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders.
Do not print credentials.
Do not bypass tests.
