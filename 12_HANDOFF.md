# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

---

# Current Project State

## Current Phase:
Phase 12: Live Demo Readiness

## Current Task ID:
LIVE-002

## Current Task Goal:
Run a short supervised live shadow validation session on the Windows MT5 host
and record the report, then proceed to DEMO-001 (demo execution preflight).

## Current Status:
LIVE-001 is complete and committed. WINMT5-LIVE-001 live proof passed on
Windows PowerShell (VALIDATED, XAUUSDm, demo account, candles + spread read,
no order_send). The live shadow runner exists and is safe by construction.

---

# Completed Work

- P0-P11 roadmap, INT-001, RISK-001, LIVE-VERIFY-001, WINMT5-001 completed.
- WINMT5-LIVE-001 proven against the real Exness demo terminal (XAUUSDm).
- Case-sensitive broker symbol fix committed (XAUUSDm preserved for MT5 calls).
- LIVE-001 committed:
  - MT5DataAdapter gained read-only fetch_tick + fetch_broker_state.
  - src/execution/live_shadow.py: LiveShadowSession (live data -> DecisionPipeline
    -> ShadowRunner/journal), make_live_pipeline (validator with detect_gaps=False
    + max_staleness, governor expecting the CANONICAL broker symbol, price-unit
    max_spread=1.0).
  - scripts/live_shadow_run.py: Windows runner, --cycles N or --duration-minutes N,
    verifies demo/non-real account before running, writes
    reports/runtime/live_shadow_run.md/.json, journal at logs/live_shadow_journal.jsonl.
  - Tests: tests/test_live_shadow.py + adapter tests (no order_send, no credentials,
    exact XAUUSDm case in every MT5 call, stale data -> NO_TRADE journaled).

---

# Current Blocker

None for LIVE-002 tooling; the actual short shadow session must be run manually
by the user on the Windows MT5 host (Claude must not run live sessions itself).

---

# Next Exact Steps

1. User runs on Windows PowerShell (short smoke first):
   `python scripts/live_shadow_run.py --cycles 5`
2. Review reports/runtime/live_shadow_run.md (outcome COMPLETED, orders_sent 0).
3. Record LIVE-002 session evidence and commit as LIVE-002.
4. Then DEMO-001: demo execution preflight (gates only, NO order placement).

---

# Allowed Files

- scripts/
- src/execution/ (shadow/preflight only; gateway send path stays gated)
- reports/runtime/
- tests/
- CURRENT_STATE.md, 12_HANDOFF.md, 11_DECISION_LOG.md

---

# Forbidden

- .env (never commit, never print values)
- enabling REAL_TRADING_ENABLED / ALLOW_REAL_ORDERS
- any order_send in shadow / preflight tasks
- demo order placement before DEMO-001 passes and user starts DEMO-002 manually

---

# Safety Rules

- No real trading.
- No demo orders yet.
- No order_send.
- No credentials printed.
- Do not fake live validation.
- ExecutionGateway is the only order pathway; RiskGovernor is final authority.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, 10_TASK_QUEUE.md,
23_DEMO_TRADING_RUNBOOK.md.

Continue LIVE-002: guide the user to run the short live shadow session on the
Windows MT5 host, then record results. Do not place orders. Do not run long
sessions autonomously. After LIVE-002 evidence is recorded, continue DEMO-001
(preflight checks only, no order placement).
