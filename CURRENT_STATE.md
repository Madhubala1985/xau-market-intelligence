# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 0: Project Foundation

## Current Task

P0-001: Create Project Control Pack

## Last Completed Task

P0-002: Create Repository Structure

## Next Task

P0-001 completion, then P1-001

## Current Execution Mode

DEMO_CONFIGURED_BUT_NOT_YET_TESTED

## Real Trading

FORBIDDEN

## Demo Trading

ALLOWED ONLY AFTER RISK GOVERNOR AND EXECUTION GATEWAY SAFETY CHECKS

## Paper Trading

ALLOWED

## Environment Status

- .env.example exists.
- .env is local only and must remain ignored.
- Demo MT5 credentials may be stored only in .env.
- Real credentials are forbidden.

## Control Pack Status

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

## Next Exact Action

1. Run scripts/verify_control_pack.sh.
2. Run pytest tests/test_project_structure.py.
3. Ensure .env is ignored.
4. Commit P0-001.
5. Then start P1-001.

## Safety Notes

- Do not commit .env.
- Do not enable real trading.
- Do not print credentials.
- Do not implement strategy before schemas are defined.
