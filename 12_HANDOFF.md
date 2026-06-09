# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 12: Live Demo Readiness

## Current Task ID:
LIVE-VERIFY-001

## Current Task Goal:
Generate a compact implementation evidence pack (implemented / tested / stubbed /
live-proven / not-yet-live-proven modules) under reports/runtime/.

## Current Status:
P0-P11 roadmap is complete. INT-001 DecisionPipeline is complete. RISK-001
leverage-aware sizing and protected pyramiding is complete and tested. Next phase
prepares the system for live shadow and supervised MT5 demo execution.

---

# Completed Work

- P0-P11 roadmap completed and tested.
- INT-001 completed: engines wired into DecisionPipeline.
- RISK-001 completed:
  - src/risk/leverage_sizing.py: LeverageAwareSizer with SymbolSpec (contract/tick),
    DemoTierTable (NORMAL $40 / HIGH_CONFLUENCE $80 / ELITE $100), AccountSnapshot,
    ConfidenceTier, TradingMode. Sizes from the dollar max-loss cap and the
    structural stop; leverage only affects margin (never loss/lot); fixed lots
    (0.01/0.05/0.10) assessed against the cap; real mode uses a conservative
    balance-relative cap (no demo-tier inheritance).
  - src/risk/pyramiding.py: PyramidingGuard + OpenTrade + PyramidLimits enforcing
    protected pyramiding (add only into protected, non-losing winners with a fresh
    setup, own risk plan, continuation support, and within the total-exposure cap).
  - Tests: tests/test_leverage_sizing.py (19), tests/test_pyramiding.py (12).
- Real-money execution remains forbidden. No orders placed in RISK-001.

---

# Next Task

## Task:
LIVE-VERIFY-001: Generate Implementation Evidence Pack

## Goal:
Create a compact report showing implemented modules, tested modules,
stubbed/mocked modules, live-proven modules, and not-yet-live-proven modules.

## Rules:
- No broad rewrite.
- No strategy changes.
- No order placement.

## Allowed Files:
- reports/runtime/
- scripts/ (read-only evidence generation, optional)
- CURRENT_STATE.md
- 12_HANDOFF.md
- 11_DECISION_LOG.md

## Forbidden Files:
- .env
- real-money configuration
- uncontrolled execution code

## Stop Condition:
- evidence report created under reports/runtime/,
- commit LIVE-VERIFY-001.

---

# Current Known Risks

- Real-money trading is forbidden.
- Demo order execution must wait for Phase 12 gates.
- Exness/MT5 credentials must not be committed.
- .env must remain local only.
- MT5 live terminal validation is not yet proven.
- No live self-mutation is allowed.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, 10_TASK_QUEUE.md, 20_LEVERAGE_AND_PYRAMIDING_POLICY.md, and 21_LIVE_DEMO_VALIDATION_PLAN.md.

Continue the current task only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders unless the current task explicitly allows it and all gates pass.
Do not print credentials.
Do not bypass tests.
