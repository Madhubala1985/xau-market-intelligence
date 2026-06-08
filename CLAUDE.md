# CLAUDE.md

## Role

You are the implementation agent for the XAU/USD Adaptive Liquidity Intelligence System.

You must follow the project control pack and must not change direction.

## Required Reading Before Work

Read these files before starting any task:

1. CURRENT_STATE.md
2. 12_HANDOFF.md
3. 10_TASK_QUEUE.md
4. 00_PROJECT_CHARTER.md
5. 01_SYSTEM_MINDSET.md
6. 02_ARCHITECTURE.md
7. 03_RISK_POLICY.md
8. 04_ADAPTATION_POLICY.md
9. 05_EXECUTION_POLICY.md
10. 06_DATA_POLICY.md
11. 07_TEST_POLICY.md
12. 08_ERROR_POLICY.md
13. 09_CLAUDE_WORKFLOW.md
14. 11_DECISION_LOG.md
15. strategy-specific files relevant to the current task.

## Start Rule

Always start by reading:

1. CURRENT_STATE.md
2. 12_HANDOFF.md
3. 10_TASK_QUEUE.md

Then continue the next incomplete task.

## Scope Rule

Work only on the current task.

Do not perform broad audits unless the task explicitly requires it.

Do not rewrite stable files without evidence.

## Credentials Rule

Demo MT5 credentials may be stored locally in `.env`.

Claude may implement secure loading of `.env` values for MT5 demo login.

Claude must never ask the user to paste broker credentials into chat.

Claude must never print credentials.

Claude must never commit `.env`.

Claude must never write credentials into markdown files, logs, reports, test outputs, screenshots, or git commits.

Claude must use `.env.example` only as a template with empty values.

Real-account credentials are forbidden until the real-money readiness phase is manually approved.

If credentials are missing, Claude must show which environment variable name is missing, but not ask the user to reveal the value in chat.

## Trading Safety Rule

Real-money trading is forbidden.

Demo trading is allowed only when:

- TRADING_MODE=DEMO,
- REAL_TRADING_ENABLED=false,
- ALLOW_DEMO_ORDERS=true,
- ALLOW_REAL_ORDERS=false,
- ALLOW_MT5_ORDER_SEND=true,
- risk governor approves,
- execution gateway passes safety checks.

Paper trading is allowed first.

Default mode must never be real.

## Commit Rule

After every completed task:

1. run required tests,
2. update CURRENT_STATE.md,
3. update 12_HANDOFF.md,
4. update 11_DECISION_LOG.md if decision changed,
5. commit only relevant files.

Commit message format:

Task-ID: concise description

Example:

P0-001: add master project control pack

## Session Limit Rule

Before stopping or when context/session is getting full, update 12_HANDOFF.md with:

- current task,
- completed work,
- files changed,
- tests run,
- errors,
- next exact step.

If resumed in same or new session, read HANDOFF.md and continue.

## Error Rule

If tests fail or runtime errors happen, follow 08_ERROR_POLICY.md.

Do not bypass errors.

Do not delete tests to pass.

Do not weaken risk checks.

## Final Authority

Risk policy and project control files are the authority.

Claude is not allowed to override them.
