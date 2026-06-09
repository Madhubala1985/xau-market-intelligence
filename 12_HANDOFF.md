# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 12: Live Demo Readiness

## Current Task ID:
LIVE-001

## Current Task Goal:
Feed real or REPLAYED XAU/USD data into DecisionPipeline and ShadowRunner. No
orders; ExecutionGateway must not send.

## Current Status:
P0-P11 roadmap is complete. INT-001 DecisionPipeline is complete. RISK-001 and
LIVE-VERIFY-001 are complete and tested. WINMT5-001 tooling (read-only
connectivity validator + Windows runner + bridge plan) is complete and tested;
the LIVE MT5 demo proof (checks 3-9) is PENDING a Windows host because this
WSL/Linux host cannot import MetaTrader5 (ENVIRONMENT_ISSUE, not faked).

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
- WINMT5-001 completed (tooling; live proof pending Windows host):
  - src/broker/connectivity.py: MT5ConnectivityValidator runs 10 read-only proofs
    against an injected client (init/login via the existing read-only adapter,
    demo-account verification rejecting REAL, XAU/USD symbol + symbol_info,
    candle fetch, spread). Never calls order_send; never writes credential values
    (login number is excluded from the report; only non-secret facts recorded).
  - scripts/winmt5_validate.py: Windows-side runner. Loads .env safely (python-
    dotenv if present, else a builtin KEY=VALUE parser; no value printed),
    classifies the environment, and on a host without MetaTrader5 writes an honest
    ENVIRONMENT_ISSUE report (checks 1-2 + 10 resolved, 3 ENVIRONMENT_ISSUE, 4-9
    SKIPPED) plus a WSL->Windows bridge plan. Does NOT fake live validation.
  - scripts/winmt5_runner_README.md: Windows run instructions + bridge plan.
  - tests/test_winmt5_connectivity.py (13): full-validation PASS, order_send never
    called, REAL account refused, CONTEST accepted, missing symbol fails,
    connect-failure skips dependents, no credentials in the report, and runner
    environment classification (ENVIRONMENT_ISSUE, honest skips, missing-var names).
  - Report artifact: reports/runtime/winmt5_validation.md + .json (git-ignored).
    On this WSL host the runner produced outcome ENVIRONMENT_ISSUE.
- Real-money execution remains forbidden. No orders placed. No credentials printed.

---

# Next Task

## Task:
LIVE-001: Connect Live/Replay Data to DecisionPipeline and ShadowRunner

## Goal:
Feed real or replayed XAU/USD data into DecisionPipeline and ShadowRunner so an
end-to-end shadow run works. Pipeline may generate decisions; ShadowRunner may log
would-trade decisions; ExecutionGateway must NOT send orders.

## Rules:
- No orders. No order_send.
- Replay data may be used until the Windows MT5 live bridge is available, so
  LIVE-001 is not blocked by the pending WINMT5-001 live proof.

## Allowed Files (expected):
- src/broker/, src/data/, src/execution/ (shadow wiring only, no sending), scripts/,
  tests/, reports/runtime/, CURRENT_STATE.md, 12_HANDOFF.md, 11_DECISION_LOG.md

## Forbidden Files:
- .env
- real-money configuration
- any ExecutionGateway order-send path

## Stop Condition:
- end-to-end shadow run works on replay/live data, tests pass, commit LIVE-001.

---

# Current Known Risks

- Real-money trading is forbidden.
- Demo order execution must wait for Phase 12 gates.
- WINMT5-001 LIVE proof is still pending a Windows MT5 host (WSL cannot import
  MetaTrader5); re-run scripts/winmt5_validate.py there to reach outcome VALIDATED.
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
