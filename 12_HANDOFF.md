# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 1: Data Foundation

## Current Task ID:
P1-001

## Current Task Goal:
Define core data schemas.

## Current Status:
Foundation is complete. Repository environment, folder structure, runtime directory preservation, and master control pack are committed.

---

# Completed Work

- P0-000 completed: repository environment initialized.
- P0-001 completed: master control pack created.
- P0-002 completed: repository structure created.
- P0-003 completed: runtime directory structure preserved.

---

# Next Task

## Task:
P1-001: Define Core Data Schemas

## Required Schemas:
- Candle
- Tick
- SpreadSnapshot
- SessionState
- BrokerState
- TradeDecision
- TradeRecord

## Allowed Files:
- src/data/
- src/utils/
- tests/

## Forbidden Files:
- src/execution/
- src/risk/
- src/strategy/
- .env

## Required Tests:
- schema validation tests
- invalid data rejection tests
- timestamp handling tests
- no credential printing

---

# Current Known Risks

- Real-money trading is forbidden.
- Demo order execution must not be implemented in P1-001.
- Exness/MT5 credentials must not be committed.
- .env must remain local only.
- No live self-mutation is allowed.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, and 10_TASK_QUEUE.md.

Continue P1-001 only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders.
Do not print credentials.
Do not bypass tests.
