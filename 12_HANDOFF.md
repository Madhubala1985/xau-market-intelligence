# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 3: Market Structure and Liquidity

## Current Task ID:
P3-001

## Current Task Goal:
Swing and Structure Engine — detect swing highs/lows, BOS, CHOCH from a Candle series.

## Current Status:
P2-002 complete. Session/kill-zone engine implemented and tested. Phase 2 finished.

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

## P2-002 Details

Files added/changed:
- src/data/sessions.py — SessionEngine, SessionConfig, SessionSegment, SessionLevels, DEFAULT_SEGMENTS.
- src/data/__init__.py — export session API.
- tests/test_sessions.py — 27 tests.

Design notes:
- The UTC day is tiled into ordered, non-overlapping segments covering [00:00,24:00). London-NY overlap is its own segment between London-only and NY-only, so every timestamp maps to exactly one session with exact [start,end) bounds and no gaps.
- Default tiling (UTC): 00-08 ASIAN, 08-13 LONDON, 13-16 LONDON_NY_OVERLAP, 16-21 NEW_YORK, 21-22 ROLLOVER, 22-24 LOW_LIQUIDITY. All configurable; SessionConfig validates the tiling.
- Weekend/closed: Saturday all day; Friday >= 21:00 UTC; Sunday < 22:00 UTC (configurable). classify() returns CLOSED.
- Flags: is_kill_zone for {LONDON, NEW_YORK, LONDON_NY_OVERLAP}; is_tradeable False for {ROLLOVER, LOW_LIQUIDITY, CLOSED}. Flags only — kill zone never triggers a trade (risk governor decides).
- Timestamps are normalized to UTC; naive datetimes are rejected.
- Level tracking: track_session_levels() returns per-occurrence high/low (keyed by session + start instant, so same session on different days are separate). annotate() returns a SessionState per candle with running high/low up to that candle (no look-ahead).

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 117 passed (27 sessions + 22 aggregation + 17 validation + 21 adapter + 29 schema + 1 structure).

Errors: none.

---

# Next Task

## Task:
P3-001: Swing and Structure Engine

## Goal:
Detect swing highs/lows, BOS (break of structure), CHOCH (change of character).

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- likely src/structure/, src/utils/, tests/ (src/structure/ exists). Confirm against the queue; do not touch src/execution|risk|strategy.

## Tests:
- fixed candle examples (deterministic swing/BOS/CHOCH cases).

---

# Current Known Risks

- Real-money trading is forbidden.
- Demo order execution must not be implemented (data / analysis only).
- Exness/MT5 credentials must not be committed and must never be printed.
- .env must remain local only.
- MetaTrader5 cannot be imported on this Linux/WSL host; keep using dependency injection for tests.
- Structure detection must avoid look-ahead (only past/known candles).
- Session boundaries are fixed UTC windows; DST/broker-session nuances are deferred and configurable.
- No live self-mutation is allowed.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, and 10_TASK_QUEUE.md.

Continue P3-001 only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders.
Do not print credentials.
Do not bypass tests.
