# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

---

# Current Project State

## Current Phase:
Phase 12: Live Demo Readiness

## Current Task ID:
DEMO-002 (BLOCKED — see blockers)

## Current Task Goal:
Supervised MT5 demo trading. NOT to be implemented/run until the recorded
blockers clear and the user manually starts supervised demo mode.

## Current Status:
LIVE-001, LIVE-002 (tooling) and DEMO-001 (preflight tooling) are complete and
committed. WINMT5-LIVE-001 live proof passed on Windows PowerShell (VALIDATED,
XAUUSDm, demo account, candles + spread read, no order_send).

## DEMO-002 Blockers (recorded 2026-06-10):
1. LIVE-002 supervised shadow session evidence not yet produced — user must run
   on the Windows MT5 host:
   `python scripts/live_shadow_run.py --duration-minutes 5 --poll-seconds 60 --report-name live_shadow_session`
2. DEMO-001 preflight has not yet PASSED on the Windows MT5 host — user must run:
   `python scripts/demo_preflight.py`
   (On WSL the account/symbol gates are SKIPPED, which blocks readiness.)
3. DEMO-002 requires the user to manually start supervised demo mode; Claude
   must not start it.
4. The demo order path itself (gateway wiring of live sizing + protected
   pyramiding into a supervised session loop) is intentionally NOT implemented
   until blockers 1-2 clear.

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
- LIVE-002 committed: cycle results and session report now carry confidence,
  uncertainty, and the Risk Governor action/reasons; --report-name lets the
  supervised session write reports/runtime/live_shadow_session.md/.json.
- DEMO-001 committed: src/execution/preflight.py (12 gates, no orders),
  src/execution/kill_switch.py (file-based manual halt at control/KILL_SWITCH,
  honored by ExecutionGateway as a blocking check), scripts/demo_preflight.py
  (honest SKIPPED gates off-Windows -> NOT ready, exit 2). .gitignore defect
  fixed (!logs/ was un-ignoring runtime journals; now logs/* + !logs/.gitkeep;
  control/ ignored).

---

# Next Exact Steps

1. User runs on Windows PowerShell (short smoke first):
   `python scripts/live_shadow_run.py --cycles 5`
2. User runs the supervised LIVE-002 session:
   `python scripts/live_shadow_run.py --duration-minutes 5 --poll-seconds 60 --report-name live_shadow_session`
   Review reports/runtime/live_shadow_session.md (COMPLETED, orders_sent 0).
3. User runs DEMO-001 preflight on the Windows MT5 host:
   `python scripts/demo_preflight.py`
   All 12 gates must be PASS (exit 0).
4. Only then consider DEMO-002, started manually by the user.

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
