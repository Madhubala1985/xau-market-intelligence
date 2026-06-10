# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

---

# Current Project State

## Current Phase:
Phase 12: Live Demo Readiness

## Current Task ID:
DEMO-EVAL (implemented; first policy-governed evaluation session pending —
user-started only)

## Current Task Goal:
Produce serious demo evaluation evidence on the Windows MT5 host with REAL
Exness MT5 demo execution on XAUUSDm: smoke first, then policy-governed
sessions (evaluation/london/newyork/full_day), with evaluation + reflection
reports after every session.

## Current Status:
DEMO-EVAL implemented and committed. 559 tests pass.
- Session risk profiles (smoke/evaluation/london/newyork/full_day) configure
  duration, polling, order cap, and RiskLimits; profiles can only TIGHTEN
  03_RISK_POLICY demo limits (construction-validated).
- No artificial order cap in evaluation modes (max_orders=None): risk policy,
  confidence tiers, regime, and setup quality govern. The one-order cap
  survives only in the smoke profile.
- Dry-run rehearses the FULL planner -> gateway path (orders_simulated,
  ORDER_SIMULATED events); order_send unreachable with flags disabled.
- Session report separates modes (DEMO_LIVE vs DRY_RUN) and carries per-cycle
  CycleStats for analysis. FILLED orders journal their MT5 ticket; closes
  reconcile from MT5 deal history with real P&L.
- Post-session: scripts/demo_eval_report.py (performance + classified
  findings) and scripts/demo_reflection.py (too strict/loose, missed,
  avoided, backtest-first, fix-now). Offline; no live self-mutation.
- Audit roadmap §6: F-11 zones/premium-discount NOT wired into the pipeline
  (Design Improvement, backtest before wiring), F-12 futures confirmation has
  no live feed, F-13 no dedicated dangerous-volatility classifier.

## Operator steps (Windows PowerShell, in order):
1. Maintain configs/news_windows.json for the week (empty windows list is an
   explicit all-clear assertion); control/NEWS_BLOCK for manual blocks.
2. Verify control/KILL_SWITCH is absent (create it to stop any session).
3. python scripts/demo_preflight.py            -> all 13 gates PASS
4. python scripts/demo_session_run.py --dry-run --profile evaluation
   -> verdict CLEAN, orders_sent 0; review ORDER_SIMULATED events
5. python scripts/demo_session_run.py --confirm "START SUPERVISED DEMO" --profile smoke
   -> first real demo order evidence (max ONE order; ticket in journal and
   MT5 Toolbox/Trade tab)
6. python scripts/demo_eval_report.py ; python scripts/demo_reflection.py
7. If CLEAN: --profile evaluation, then london / newyork / full_day.
   Evaluation + reflection after EVERY session; review before the next one.

## After evidence:
- Aggregate multi-session evidence toward the real-money gate map
  (24_INTELLIGENCE_AUDIT_ROADMAP.md §7). Real trading remains FORBIDDEN.
- Backtest-gated candidates: F-11 zone/premium-discount wiring, F-13
  dangerous-volatility classifier, partial take-profits, futures feed (F-12).

---

# Completed Work

- P0-P11, INT-001, RISK-001, LIVE-VERIFY-001, WINMT5-001/WINMT5-LIVE-001,
  LIVE-001, LIVE-002, DEMO-001, AUDIT-001, DEMO-002-BLOCKERS, DEMO-002 —
  see CURRENT_STATE.md and 11_DECISION_LOG.md.
- DEMO-EVAL (2026-06-10, decision 2026-06-10-05):
  - src/execution/session_profiles.py (new): policy-bounded profiles.
  - src/execution/demo_session.py: Optional max_orders, orders_simulated,
    CycleStats, mode/profile in the report.
  - scripts/demo_session_run.py: --profile/--max-orders/--max-open-positions,
    profile-driven RiskLimits + pipeline spread, dry-run fixed.
  - src/reflection/demo_evaluation.py (new): SessionEvaluator, findings
    classification, reflection builder, markdown renderers.
  - scripts/demo_eval_report.py + scripts/demo_reflection.py (new).
  - Tests: test_session_profiles.py (12), test_demo_evaluation.py (10),
    test_demo_session.py (+5). Suite: 559 passed.

---

# Next Exact Steps

1. User runs the operator steps above on the Windows MT5 host.
2. Record evidence (session report verdicts, tickets, evaluation/reflection
   outputs) and commit the outcome notes.
3. Only after reviewed evidence: longer or repeated sessions; any strategy
   change (F-11/F-13) goes through backtest + walk-forward first.

---

# Allowed Files

- scripts/, src/execution/, src/reflection/, tests/, reports/runtime/
- CURRENT_STATE.md, 12_HANDOFF.md, 11_DECISION_LOG.md

---

# Forbidden

- .env (never commit, never print values)
- enabling REAL_TRADING_ENABLED / ALLOW_REAL_ORDERS
- loosening 03_RISK_POLICY limits (profiles may only tighten)
- starting supervised sessions autonomously (user-started only)
- live self-mutation from reflection output

---

# Safety Rules

- No real trading. Stop-loss mandatory. Kill switch honored every cycle.
- ExecutionGateway is the only order pathway; RiskGovernor is final authority.
- Unknown news state and orphan positions fail closed.
- No credentials printed, logged, or committed.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, 10_TASK_QUEUE.md,
23_DEMO_TRADING_RUNBOOK.md, 24_INTELLIGENCE_AUDIT_ROADMAP.md.

DEMO-EVAL is implemented. Guide the user through the operator steps (preflight
-> dry-run -> smoke -> evaluation sessions) on the Windows MT5 host and review
the evaluation/reflection reports with them. Do not start sessions. Do not
weaken risk. Strategy changes (F-11/F-13) require backtest evidence first.
