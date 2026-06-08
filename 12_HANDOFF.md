# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 1: Data Foundation

## Current Task ID:
P1-003

## Current Task Goal:
Data Validation Engine — detect missing/duplicate/stale candles, bad OHLC, spread anomalies, timestamp issues; invalid data must produce NO_TRADE.

## Current Status:
P1-002 complete. MT5 demo data adapter implemented (data fetch only) and tested.

---

# Completed Work

- P0-000 completed: repository environment initialized.
- P0-001 completed: master control pack created.
- P0-002 completed: repository structure created.
- P0-003 completed: runtime directory structure preserved.
- P1-001 completed: core data schemas defined and tested.
- P1-002 completed: MT5 demo data adapter (data fetch only) implemented and tested.

## P1-002 Details

Files added/changed:
- src/broker/errors.py — broker exceptions (messages never contain secret values).
- src/broker/mt5_settings.py — MT5Settings + load_mt5_settings(); validates required env vars by NAME only, masks credentials in repr/str, enforces DEMO-only config, optional MT5_SERVER_UTC_OFFSET_MINUTES.
- src/broker/mt5_data_adapter.py — MT5DataAdapter: connect/shutdown, fetch_candles -> Candle, XAUUSD-only symbol validation, MT5 timestamp normalization. NEVER calls order_send.
- src/broker/__init__.py — package exports.
- tests/test_mt5_data_adapter.py — 21 tests.

Design / safety notes:
- MetaTrader5 is Windows-only and NOT installed here; the adapter lazily imports it or accepts an injected client, so it is testable on Linux. Tests inject a FakeMT5.
- order_send / order_check are mocked in tests and asserted never called across the full connect+fetch+shutdown cycle. No trade/order calls exist in src/.
- Credentials: loaded from env (populated from local .env, never committed). Password and login are masked in MT5Settings repr/str. Missing vars reported by NAME only; invalid login does not echo its value.
- Demo-only gate: REAL_TRADING_ENABLED=true, TRADING_MODE!=DEMO, MT5_ACCOUNT_TYPE!=DEMO, or non-XAU MT5_SYMBOL are all rejected.
- Timestamps: MT5 server epoch -> broker_time (server offset preserved) + time_utc (normalized). Default offset 0 treats epoch as UTC. Configurable via MT5_SERVER_UTC_OFFSET_MINUTES (optional, non-secret; .env.example not modified).

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 51 passed (21 adapter + 29 schema + 1 structure).

Errors: none.

Note: requirements.txt was NOT modified; MetaTrader5 is not Linux-installable. Install it on the Windows MT5 host before running against a live demo terminal (P1-003+ / runtime).

---

# Next Task

## Task:
P1-003: Data Validation Engine

## Goal:
Detect missing candles, duplicate candles, stale data, bad OHLC, spread anomalies, timestamp issues. Invalid data must produce a NO_TRADE status.

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- src/data/, src/utils/, tests/

## Tests:
- malformed data is rejected,
- valid data passes,
- invalid data produces NO_TRADE status.

---

# Current Known Risks

- Real-money trading is forbidden.
- Demo order execution must not be implemented (data fetch / validation only).
- Exness/MT5 credentials must not be committed and must never be printed.
- .env must remain local only.
- MetaTrader5 cannot be imported on this Linux/WSL host; keep using dependency injection for tests.
- No live self-mutation is allowed.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, and 10_TASK_QUEUE.md.

Continue P1-003 only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders.
Do not print credentials.
Do not bypass tests.
