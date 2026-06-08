# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 2: Session and Timeframe Context

## Current Task ID:
P2-002

## Current Task Goal:
Session/Kill-Zone Engine — classify Asian, London, New York, London-NY overlap, and low-liquidity periods; track session highs/lows.

## Current Status:
P2-001 complete. Timeframe aggregation implemented and tested.

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

## P2-001 Details

Files added/changed:
- src/data/aggregation.py — TimeframeAggregator + aggregate() + AggregationError.
- src/data/__init__.py — export aggregation API.
- tests/test_aggregation.py — 22 tests.

Design notes:
- Aggregates a lower-timeframe Candle series into 5M/15M/1H/4H/Daily.
- Bars grouped into aligned UTC windows [start, start+step); open=first open, high=max, low=min, close=last close, tick_volume=sum, real_volume=sum (None if any source bar lacks it), spread=None.
- Daily aligns to UTC midnight; intraday aligns to the UTC epoch grid.
- broker_time of an aggregated bar re-expresses the window start in the source bars' UTC offset (offset preserved).
- No future leakage: each bar uses only source bars inside its own window; the still-forming trailing bar is withheld when drop_incomplete=True (default). With `now`, any bucket whose end > now is dropped; without `now`, the last bucket is dropped. Pass drop_incomplete=False to keep the forming bar.
- Input is validated: single symbol, single source timeframe, strictly increasing time order (no duplicates); target must be a larger whole multiple of the source. Errors raise AggregationError.

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 90 passed (22 aggregation + 17 validation + 21 adapter + 29 schema + 1 structure).

Errors: none.

---

# Next Task

## Task:
P2-002: Session/Kill-Zone Engine

## Goal:
Classify Asian, London, New York, London-New-York overlap, and low-liquidity periods; track session highs/lows.

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- src/data/, src/utils/, tests/
  (See also 14_SESSION_KILLZONE_POLICY.md for the session definitions.)

## Tests:
- timestamp-to-session mapping,
- session highs/lows tracking.

---

# Current Known Risks

- Real-money trading is forbidden.
- Demo order execution must not be implemented (data / analysis only).
- Exness/MT5 credentials must not be committed and must never be printed.
- .env must remain local only.
- MetaTrader5 cannot be imported on this Linux/WSL host; keep using dependency injection for tests.
- Session classification must use normalized UTC time; broker server offset (MT5_SERVER_UTC_OFFSET_MINUTES) may matter for session boundaries.
- No live self-mutation is allowed.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, and 10_TASK_QUEUE.md.

Continue P2-002 only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders.
Do not print credentials.
Do not bypass tests.
