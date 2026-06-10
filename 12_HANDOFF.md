# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

---

# Current Project State

## Current Phase:
Phase 12: Live Demo Readiness

## Current Task ID:
DEMO-002 (implemented; first supervised run pending — user-started only)

## Current Task Goal:
Produce first supervised demo session evidence on the Windows MT5 host:
dry-run first, then ONE supervised order maximum, then review.

## Current Status:
SupervisedDemoSession + scripts/demo_session_run.py implemented and committed.
529 tests pass. The session refuses to construct without a READY preflight and
the exact confirmation token; --dry-run runs the full loop with sending
hard-disabled. Orders flow ONLY planner -> governor -> gateway; stop updates
ONLY via gateway.modify_stop (never widens/removes); kill switch halts the
session; orphans and unknown news fail closed; filled orders journal their MT5
ticket; closes are detected with real P&L from deal history so loss limits
operate on real losses.

## Operator steps for the first supervised run (Windows PowerShell):
1. Review the week's calendar and create configs/news_windows.json
   (an empty {"windows": []} is an explicit all-clear assertion);
   control/NEWS_BLOCK engages an immediate manual block at any time.
2. Verify control/KILL_SWITCH is absent (create it to stop the session).
3. python scripts/demo_preflight.py            -> all 13 gates PASS
4. python scripts/demo_session_run.py --dry-run --duration-minutes 10
   -> verdict CLEAN, zero orders, review events
5. python scripts/demo_session_run.py --confirm "START SUPERVISED DEMO" --duration-minutes 60 --max-orders 1
   -> supervise live; stop anytime: New-Item -ItemType File control\KILL_SWITCH
6. Review reports/runtime/demo_session.md + logs/demo_trade_journal.jsonl;
   record evidence; commit the outcome notes.

## After first evidence:
- If CLEAN: consider longer supervised sessions (still demo, still supervised).
- DEMO-003 candidates: partial take-profit execution, richer close
  classification (commission/swap split), reflection report generation from
  the demo journal, multi-session aggregation.
- Real trading remains FORBIDDEN.

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
- AUDIT-001 committed: 24_INTELLIGENCE_AUDIT_ROADMAP.md (full audit, gate map,
  classified findings). Fixed: RiskStateTracker feeds real daily/weekly loss,
  trades/day, loss streak, open symbols from the journal into every live cycle;
  DecisionPipeline max_spread aligns execution-quality scoring with the
  governor's price-unit spread limit in the live config.

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
