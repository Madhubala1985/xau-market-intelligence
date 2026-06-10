# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

---

# Current Project State

## Current Phase:
Phase 12: Live Demo Readiness — continuous service operational

## Current Task ID:
CONTINUOUS-001 (implemented; first continuous run pending — user-started only)

## Current Task Goal:
Operate the continuous MT5 trading service on the Windows MT5 host against
the .env account (Exness DEMO -> real MT5 demo orders on XAUUSDm), collect
multi-day evidence via the daily evaluation/reflection reports.

## Current Status:
CONTINUOUS-001 implemented and committed. 583 tests pass.
- scripts/trading_service.py is the MAIN runner: starts once, fresh
  preflight every start, continuous loop until kill switch / weekly-loss
  risk shutdown / Ctrl+C / fatal error. Daily loss limit = DAY_PAUSED
  (entries blocked until UTC rollover, positions still managed).
- ONE execution stack: TradingService drives SupervisedDemoSession
  .run_cycle() — same planner/governor/gateway/journal as bounded sessions;
  .env decides the account, .env flags decide whether orders are SENT
  (without them the identical loop is a dry-run with simulated plans).
- Market closed (schedule + stale tick) -> waits, prints, heartbeats
  (logs/service_heartbeat.jsonl), resumes automatically.
- Terminal observability: startup banner + per-cycle progress; orders print
  MT5 tickets (Toolbox/Trade tab); login masked; no credentials anywhere.
- Daily rollover writes service_eval_YYYYMMDD + service_reflection_YYYYMMDD;
  trading_service.md/.json on stop.
- F-14 Proven Defect FIXED: order requests now carry the exact broker
  symbol case ("XAUUSDm"); canonical forms are comparison-only.
  verify_demo_account shared in src/broker/mt5_data_adapter.py.

## Operator steps (Windows PowerShell):
1. Maintain configs/news_windows.json (empty list = explicit all-clear);
   control/NEWS_BLOCK for manual blocks. Verify control/KILL_SWITCH absent.
2. py -3.12 scripts\demo_preflight.py            -> all 13 gates PASS
3. py -3.12 scripts\trading_service.py --profile continuous --dry-run --stdout-progress
   -> watch the banner + a few cycles; Ctrl+C stops cleanly
4. Ensure .env flags: TRADING_MODE=DEMO, REAL_TRADING_ENABLED=false,
   ALLOW_DEMO_ORDERS=true, ALLOW_MT5_ORDER_SEND=true, ALLOW_REAL_ORDERS=false
5. py -3.12 scripts\trading_service.py --profile continuous --stdout-progress
   -> supervise initially; trades appear in MT5 Toolbox/Trade tab
6. Stop: New-Item -ItemType File control\KILL_SWITCH
   Resume: Remove-Item control\KILL_SWITCH ; restart the service
7. Review daily service_eval_* / service_reflection_* and
   logs/demo_trade_journal.jsonl; collect multi-day evidence.

## After evidence:
- Multi-week continuous-demo evidence feeds the real-money gate map
  (24_INTELLIGENCE_AUDIT_ROADMAP.md §7). Real trading remains FORBIDDEN.
- Backtest-gated candidates: F-11 zone/premium-discount wiring, F-12
  futures feed, F-13 dangerous-volatility classifier, partial take-profits.

---

# Completed Work

- Full history in CURRENT_STATE.md and 11_DECISION_LOG.md (P0..DEMO-EVAL).
- CONTINUOUS-001 (decision 2026-06-10-06): src/execution/trading_service.py
  + market_hours.py (new), run_cycle()/CycleOutcome on the session,
  'continuous' profile (duration None), gateway broker_symbol fix (F-14),
  shared verify_demo_account, scripts/trading_service.py (new), runbook
  section, tests test_trading_service.py (15) + test_market_hours.py (6).

---

# Next Exact Steps

1. User runs the operator steps above on the Windows MT5 host.
2. Record evidence (banner output, first cycles, tickets vs MT5 Toolbox,
   daily reports) and commit outcome notes.
3. Any strategy change (F-11/F-13) goes through backtest + walk-forward
   first. No risk loosening.

---

# Allowed Files

- scripts/, src/execution/, src/broker/, src/reflection/, tests/,
  reports/runtime/
- CURRENT_STATE.md, 12_HANDOFF.md, 11_DECISION_LOG.md

---

# Forbidden

- .env (never commit, never print values)
- enabling REAL_TRADING_ENABLED / ALLOW_REAL_ORDERS
- loosening 03_RISK_POLICY limits (profiles may only tighten)
- starting the service or sessions autonomously (user-started only)
- live self-mutation from reflection output

---

# Safety Rules

- No real trading; REAL accounts refused at start.
- Stop-loss mandatory; stops never widen or get removed.
- Kill switch honored every check; Ctrl+C stops cleanly.
- ExecutionGateway is the only order pathway; RiskGovernor final authority.
- Unknown news state and orphan positions fail closed.
- No credentials printed, logged, or committed (login masked in banner).

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, 10_TASK_QUEUE.md,
23_DEMO_TRADING_RUNBOOK.md, 24_INTELLIGENCE_AUDIT_ROADMAP.md.

CONTINUOUS-001 is implemented. Guide the user through the continuous-service
operator steps on the Windows MT5 host and review the daily reports with
them. Do not start the service. Do not weaken risk. Strategy changes
(F-11/F-13) require backtest evidence first.
