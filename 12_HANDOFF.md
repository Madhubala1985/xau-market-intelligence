# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 12: Live Demo Readiness

## Current Task ID:
WINMT5-001

## Current Task Goal:
Validate MT5 demo terminal connectivity and XAU/USD read-only data on the Windows
MT5 host. No order_send. No credentials printed.

## Current Status:
P0-P11 roadmap is complete. INT-001 DecisionPipeline is complete. RISK-001
leverage-aware sizing and protected pyramiding is complete and tested.
LIVE-VERIFY-001 implementation evidence pack generator is complete and tested.
Next gate is real MT5 demo connectivity validation on a Windows host.

---

# Completed Work

- P0-P11 roadmap completed and tested.
- INT-001 completed: engines wired into DecisionPipeline.
- RISK-001 completed: src/risk/leverage_sizing.py (LeverageAwareSizer, SymbolSpec,
  DemoTierTable, AccountSnapshot, ConfidenceTier, TradingMode) and
  src/risk/pyramiding.py (PyramidingGuard, OpenTrade, PyramidLimits), with
  tests/test_leverage_sizing.py and tests/test_pyramiding.py.
- LIVE-VERIFY-001 completed:
  - scripts/generate_evidence_pack.py: read-only introspection generator (does not
    import/run src; no order_send; no credentials). Classifies every src module
    (implemented / tested / external-mock / live-proven / shadow-ready /
    demo-order-ready / needs-Windows-MT5) and renders reports/runtime/
    evidence_pack.md + .json. build_evidence() raises if any module is
    unclassified, keeping the report honest.
  - tests/test_evidence_pack.py: verifies full module coverage, live_proven == 0,
    ready_for_demo_order == 0, MT5-boundary modules need Windows validation, and
    all required markdown sections render.
  - Evidence pack output lives under reports/runtime/ which is GIT-IGNORED
    (runtime artifact). The committed deliverable is the generator + test + docs;
    regenerate with `python scripts/generate_evidence_pack.py`.
  - Findings: 34 modules, all implemented and tested; 5 MT5/order-boundary modules
    (broker.errors, broker.mt5_settings, broker.mt5_data_adapter,
    execution.gateway, execution.shadow) are external-mock and require WINMT5-001;
    0 modules live-proven; 0 modules cleared for demo orders.
- Real-money execution remains forbidden. No orders placed. No credentials printed.

---

# Next Task

## Task:
WINMT5-001: Validate MT5 Demo Connectivity

## Goal:
Validate MT5 demo terminal connectivity and XAU/USD read-only data: MT5 init/login,
demo account verified, XAU/USD symbol detected, symbol info read, candles fetched,
spread read, account info read safely.

## Rules:
- No orders. No order_send. No credentials printed.
- If WSL cannot import MetaTrader5, create a Windows-side runner or safe bridge plan
  (22_MT5_WINDOWS_VALIDATION.md). Do not fake live validation.

## Allowed Files:
- src/broker/
- scripts/
- tests/
- CURRENT_STATE.md
- 12_HANDOFF.md
- 11_DECISION_LOG.md

## Forbidden Files:
- .env
- real-money configuration
- src/execution/ order paths

## Stop Condition:
- validation report created,
- commit WINMT5-001.

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
