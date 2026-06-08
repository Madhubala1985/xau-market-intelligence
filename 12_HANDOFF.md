# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 0: Project Foundation

## Current Task ID:
P0-001

## Current Task Goal:
Create and verify the master project control pack.

## Current Status:
Control-pack files 00 through 19 have been created and populated.

Repository environment and structure already exist.

---

# Completed Work

- P0-000 completed: repository environment initialized.
- P0-002 completed: repository structure created.
- P0-001 in progress: master control-pack files populated.

---

# Files Changed In Current Task

Expected files:

- 00_PROJECT_CHARTER.md
- 01_SYSTEM_MINDSET.md
- 02_ARCHITECTURE.md
- 03_RISK_POLICY.md
- 04_ADAPTATION_POLICY.md
- 05_EXECUTION_POLICY.md
- 06_DATA_POLICY.md
- 07_TEST_POLICY.md
- 08_ERROR_POLICY.md
- 09_CLAUDE_WORKFLOW.md
- 10_TASK_QUEUE.md
- 11_DECISION_LOG.md
- 12_HANDOFF.md
- 13_XAUUSD_SMC_PLAYBOOK.md
- 14_SESSION_KILLZONE_POLICY.md
- 15_LIQUIDITY_ENGINEERING.md
- 16_ORDERFLOW_PROXY_POLICY.md
- 17_STOP_AND_TRAILING_POLICY.md
- 18_CAPITAL_AND_SCALING_POLICY.md
- 19_GOLD_FUTURES_CONFIRMATION_POLICY.md
- CLAUDE.md
- CURRENT_STATE.md
- scripts/verify_control_pack.sh

---

# Tests Run

Pending:

- bash scripts/verify_control_pack.sh
- pytest tests/test_project_structure.py

---

# Test Results

Pending.

---

# Current Known Risks

- Real-money trading is forbidden.
- Demo order execution is allowed only through DEMO mode with risk governor approval.
- Exness/MT5 credentials must not be committed.
- .env must remain local only.
- CVD/delta must be treated as proxy.
- No live self-mutation is allowed.

---

# Next Exact Step

1. Run scripts/verify_control_pack.sh.
2. Run pytest tests/test_project_structure.py.
3. Ensure .env is ignored.
4. Commit P0-001.
5. Update CURRENT_STATE.md to next task P1-001.
6. Start Claude with the resume prompt.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, and 10_TASK_QUEUE.md.

Continue the current task only.

Do not broaden scope.
Do not trade real money.
Do not print credentials.
Do not bypass tests.
