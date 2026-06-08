# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 3: Market Structure and Liquidity

## Current Task ID:
P3-002

## Current Task Goal:
Liquidity Map Engine — detect buy-side/sell-side liquidity, equal highs/lows, session highs/lows, previous day/week highs/lows.

## Current Status:
P3-001 complete. Swing & market-structure engine implemented and tested.

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

## P3-001 Details

Files added/changed:
- src/structure/market_structure.py — MarketStructureEngine + SwingPoint, StructureEvent, StructureResult, and SwingType/StructureEventType/Bias enums.
- src/structure/__init__.py — package exports.
- tests/test_market_structure.py — 8 tests (fixed candle examples).

Design notes:
- Swings are fractal pivots: a swing high/low is a strict extreme vs `strength` candles on each side (default strength=2). It is CONFIRMED only at index i + strength, so it is never used before then.
- BOS/CHOCH use close-based breaks of the most recent confirmed swing level. A break continuing the prevailing bias is BOS; the first break against it is CHOCH (flips bias); the first break overall establishes the bias and is reported as BOS. A broken level is consumed until a new swing of that type confirms.
- No look-ahead: results are prefix-stable (a break detected on a prefix is identical on the full series) — covered by tests.
- Strict comparison means equal highs/lows form no swing (left for the liquidity engine in P3-002 to treat as equal-highs/equal-lows liquidity).

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 125 passed (8 structure + 27 sessions + 22 aggregation + 17 validation + 21 adapter + 29 schema + 1 structure-dirs).

Errors: none.

---

# Next Task

## Task:
P3-002: Liquidity Map Engine

## Goal:
Detect buy-side liquidity, sell-side liquidity, equal highs/lows, session highs/lows, previous day/week highs/lows.

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- likely src/liquidity/, src/utils/, tests/ (src/liquidity/ exists). Reuse src/structure/ swings and src/data/sessions.py. Do not touch src/execution|risk|strategy.

## Tests:
- known examples.

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

Continue P3-002 only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders.
Do not print credentials.
Do not bypass tests.
