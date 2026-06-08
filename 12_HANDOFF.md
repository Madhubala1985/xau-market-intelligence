# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 3: Market Structure and Liquidity

## Current Task ID:
P3-004

## Current Task Goal:
FVG / Order Block / Supply-Demand Engine — detect FVGs, order-block-like zones, supply/demand zones, mitigation status.

## Current Status:
P3-003 complete. Liquidity sweep engine implemented and tested.

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

## P3-003 Details

Files added/changed:
- src/liquidity/sweep.py — SweepEngine + SweepEvent + SweepStatus.
- src/liquidity/__init__.py — export sweep API.
- tests/test_sweep.py — 8 tests (true / false / no sweep + edges).

Design notes:
- Candidate sweep = a known liquidity level is taken (wick beyond) AND price closes back across it with a rejection wick >= rejection_ratio of the candle range. "A wick alone is not enough."
- Confirmation = displacement candle in the rejection direction (range >= displacement_factor * baseline range) AND a structure event (BOS/CHOCH, reusing P3-001) in the rejection direction within confirm_window.
- Status: TRUE_SWEEP (both confirmations), FALSE_SWEEP (window elapsed without both), PENDING (window not yet elapsed). A level taken but closed-through (breakout) yields no candidate; an untouched level yields nothing.
- Buy-side level swept -> bearish rejection; sell-side -> bullish rejection.
- No look-ahead: only levels established strictly before the sweep candle are used; confirmation sets confirmed_index at the later candle; unconfirmed-but-open candidates are PENDING (not FALSE). Each level is consumed by its first sweep.
- A sweep is NOT a trade by itself (15_LIQUIDITY_ENGINEERING.md) — engine only classifies.
- Accepts a LiquidityMap or a list of LiquidityLevel.

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 142 passed (8 sweep + 9 liquidity + 8 structure + 27 sessions + 22 aggregation + 17 validation + 21 adapter + 29 schema + 1 structure-dirs).

Errors: none.

---

# Next Task

## Task:
P3-004: FVG / Order Block / Supply-Demand Engine

## Goal:
Detect fair value gaps (FVGs), order-block-like zones, supply/demand zones, and mitigation status.

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- likely src/orderflow/ or a new structure/zones module + src/utils/ + tests/. Check the queue. src/orderflow/ exists. Reuse src/structure/ and src/data/ schemas. Do not touch src/execution|risk|strategy.

## Tests:
- valid/invalid zones.

## Notes for P3-004:
- FVG (3-candle imbalance): bullish FVG when candle[i-1].high < candle[i+1].low (gap), bearish when candle[i-1].low > candle[i+1].high. Mitigation = later price trades back into the gap.
- Order block = last opposing candle before displacement that breaks structure; supply/demand = zone left behind by displacement.
- Mitigation status must be evaluated with no look-ahead (only candles available at decision time).

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

Continue P3-004 only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders.
Do not print credentials.
Do not bypass tests.
