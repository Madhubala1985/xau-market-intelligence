# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 2: Session and Timeframe Context

## Current Task ID:
P2-001

## Current Task Goal:
Timeframe Aggregation — build reliable 1M -> 5M/15M/1H/4H/Daily aggregation with correctness and no future leakage.

## Current Status:
P1-003 complete. Data Validation Engine implemented and tested. Phase 1 (Data Foundation) is finished.

---

# Completed Work

- P0-000 completed: repository environment initialized.
- P0-001 completed: master control pack created.
- P0-002 completed: repository structure created.
- P0-003 completed: runtime directory structure preserved.
- P1-001 completed: core data schemas defined and tested.
- P1-002 completed: MT5 demo data adapter (data fetch only) implemented and tested.
- P1-003 completed: data validation engine implemented and tested.

## P1-003 Details

Files added/changed:
- src/data/validation.py — DataValidator + ValidationConfig/Report/Issue and ValidationStatus/IssueSeverity/ValidationCode enums.
- src/data/__init__.py — export validation API.
- tests/test_data_validation.py — 17 tests.

Design notes:
- Validates a series of already-constructed Candle objects (the adapter's output). Impossible OHLC and inconsistent bid/ask are already rejected by the schema layer; the engine adds series-level + freshness checks.
- Detects: empty input, mixed symbols, symbol mismatch vs expected, mixed timeframes, duplicate timestamps, non-monotonic/misaligned intervals, missing candles (gaps), bad OHLC (defensive), spread-too-high, zero volume, stale data, look-ahead.
- Any BLOCKING issue -> ValidationStatus.NO_TRADE (06_DATA_POLICY.md: bad data must never trade). Zero-volume is a WARNING by default (configurable to block).
- Freshness (stale/look-ahead) checks require a `now` reference; skipped when now is None.
- Weekend/session gaps are out of scope here (handled by P2 session engine); gap detection is configurable via detect_gaps.

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 68 passed (17 validation + 21 adapter + 29 schema + 1 structure).

Errors: none.

---

# Next Task

## Task:
P2-001: Timeframe Aggregation

## Goal:
Build reliable 1M -> 5M/15M/1H/4H/Daily aggregation.

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- src/data/, src/utils/, tests/
  (Consider a dedicated aggregation module under src/data/ or src/utils/.)

## Tests:
- aggregation correctness,
- no future leakage (only completed source bars form an aggregated bar).

---

# Current Known Risks

- Real-money trading is forbidden.
- Demo order execution must not be implemented (data / analysis only).
- Exness/MT5 credentials must not be committed and must never be printed.
- .env must remain local only.
- MetaTrader5 cannot be imported on this Linux/WSL host; keep using dependency injection for tests.
- No live self-mutation is allowed.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, and 10_TASK_QUEUE.md.

Continue P2-001 only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders.
Do not print credentials.
Do not bypass tests.
