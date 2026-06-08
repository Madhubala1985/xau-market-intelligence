# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 3: Market Structure and Liquidity

## Current Task ID:
P3-003

## Current Task Goal:
Liquidity Sweep Engine — detect sweep, rejection, reclaim, displacement confirmation.

## Current Status:
P3-002 complete. Liquidity map engine implemented and tested.

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

## P3-002 Details

Files added/changed:
- src/liquidity/liquidity_map.py — LiquidityMapEngine + LiquidityMap, LiquidityLevel, and LiquidityKind/LiquiditySide enums.
- src/liquidity/__init__.py — package exports.
- tests/test_liquidity_map.py — 9 tests (known examples).

Design notes:
- Scope is the liquidity MAP only (where liquidity rests). Sweep/manipulation detection is P3-003 and is intentionally NOT here.
- Level kinds: SWING_HIGH/LOW (reuses src/structure swings), EQUAL_HIGHS/LOWS (clusters of near-equal swings within equal_tolerance, default 0.1), SESSION_HIGH/LOW (reuses src/data/sessions.py; main sessions only: Asian/London/NY/overlap), PREV_DAY_HIGH/LOW and PREV_WEEK_HIGH/LOW.
- Side convention: high-type levels = BUY_SIDE (rest above price); low-type = SELL_SIDE. Helpers: map.buy_side(), map.sell_side(), map.of_kind(kind).
- Equal cluster representative price = top of cluster for highs, bottom for lows; touches = cluster size; time = most recent touch.
- Previous day/week = the period immediately before the latest candle's period (handles gaps/weekends by using the previous available period key).
- No look-ahead: levels derive only from supplied candles; swings are confirmed pivots; prev day/week are completed past periods. Covered by a prefix test.

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 134 passed (9 liquidity + 8 structure + 27 sessions + 22 aggregation + 17 validation + 21 adapter + 29 schema + 1 structure-dirs).

Errors: none.

---

# Next Task

## Task:
P3-003: Liquidity Sweep Engine

## Goal:
Detect sweep, rejection, reclaim, and displacement confirmation against liquidity levels.

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- likely src/liquidity/, src/utils/, tests/. Reuse src/liquidity/ map and src/structure/. Do not touch src/execution|risk|strategy.

## Tests:
- true sweep,
- false sweep,
- no sweep.

## Notes for P3-003:
- A sweep requires: a known liquidity level is taken (wick beyond), price fails to continue, closes back / rejects, displacement appears, structure confirms (15_LIQUIDITY_ENGINEERING.md). A wick alone is not enough.
- A sweep is NOT a trade by itself; output detection only.

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

Continue P3-003 only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders.
Do not print credentials.
Do not bypass tests.
