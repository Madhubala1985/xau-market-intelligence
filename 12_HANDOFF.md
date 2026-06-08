# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 1: Data Foundation

## Current Task ID:
P1-002

## Current Task Goal:
MT5 Demo Data Adapter — connect to MT5 demo terminal and fetch XAU/USD candles safely.

## Current Status:
P1-001 complete. Core data schemas are defined, validated, and tested.

---

# Completed Work

- P0-000 completed: repository environment initialized.
- P0-001 completed: master control pack created.
- P0-002 completed: repository structure created.
- P0-003 completed: runtime directory structure preserved.
- P1-001 completed: core data schemas defined and tested.

## P1-001 Details

Files added/changed:
- src/utils/time.py — UTC normalization helpers (ensure_aware, to_utc); naive datetimes rejected.
- src/data/enums.py — Timeframe, Direction, DecisionStatus, SessionType, BrokerConnectionStatus, TradeOutcome.
- src/data/schemas.py — Candle, Tick, SpreadSnapshot, SessionState, BrokerState, TradeDecision, TradeRecord.
- src/data/__init__.py — package exports.
- tests/test_schemas.py — 29 tests (validation, invalid rejection, timestamp handling, immutability, no-credential checks).

Design notes:
- All schemas are frozen (immutable) and use extra="forbid" so unknown fields are rejected.
- Candle/Tick preserve broker_time (original offset) and time_utc (normalized to UTC).
- Impossible OHLC and inconsistent bid/ask are rejected; naive timestamps are rejected.
- TradeDecision enforces P6-001 guardrails: actionable LONG/SHORT requires thesis + invalidation_price; stop must be on the correct side of entry.
- BrokerState carries NO credential fields and defaults to UNKNOWN connection / trade_allowed=False (safe by default).

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 30 passed (29 schema + 1 structure).

Errors: none.

---

# Next Task

## Task:
P1-002: MT5 Demo Data Adapter

## Goal:
Connect to MT5 demo terminal and fetch XAU/USD candles safely into the Candle schema.

## Rules:
- demo credentials loaded from .env (secure loading, never printed),
- no real trading,
- order sending disabled,
- symbol must be XAU/USD mapped carefully.

## Allowed Files:
- src/broker/ and/or src/data/ (adapter), src/utils/, tests/
- (Confirm against 10_TASK_QUEUE.md before starting.)

## Tests:
- adapter initializes,
- fetches latest candles,
- rejects wrong symbols,
- does not print credentials.

---

# Current Known Risks

- Real-money trading is forbidden.
- Demo order execution must not be implemented in P1-002 (data fetch only).
- Exness/MT5 credentials must not be committed and must never be printed.
- .env must remain local only.
- No live self-mutation is allowed.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, and 10_TASK_QUEUE.md.

Continue P1-002 only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders.
Do not print credentials.
Do not bypass tests.
