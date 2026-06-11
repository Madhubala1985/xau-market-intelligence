# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

---

# Current Project State

## Current Phase:
Phase 12: Live Demo Readiness — continuous service operational; FINAL
LAST-CHANCE demo_challenge experiment ready

## Current Task ID:
DEMO-CHALLENGE-001 (implemented; user starts the run —
--profile demo_challenge, user-started only)

## Current Task Goal:
Run the aggressive fixed-lot momentum profile on the Exness MT5 DEMO
account and observe whether the system actually captures XAUUSD momentum:
fresh entry scan every candle, tactical M1/M5 stops instead of structural
stops, 0.05/0.10 fixed lots, same-direction add-ons only into floating
profit, full per-cycle reasoning in the terminal.

## Current Status:
DEMO-CHALLENGE-001 implemented. 753 tests pass; safety check passes.
- New decision layer behind the UNCHANGED safety stack: the momentum
  pipeline (src/strategy/challenge_momentum.py) and the fixed-lot planner
  (src/execution/challenge_planner.py) are swapped in ONLY when
  --profile demo_challenge; session/gateway/journal/reconciliation/
  trailing/kill switch identical; the institutional model is untouched
  and remains the default.
- Momentum logic: M15+M5 alignment OR M5 displacement with M1 agreement;
  triggers breakout / pullback_rejection / continuation; STRONG => 0.10,
  NORMAL => 0.05; low liquidity demotes 0.10->0.05 (never blocks alone).
- TACTICAL stop only: nearest valid local M1/M5 swing / rejection wick /
  pullback extreme + ATR/spread buffer, hard ceiling 8 USD; no valid local
  stop => skip with "waiting for local swing stop" (structural stops are
  NEVER substituted; STOP_TOO_WIDE_FOR_ACCOUNT cannot recur here).
- Add-ons: same direction only, every open trade in floating profit,
  none after a losing trade, max 3 open, no hedging — else exact reason.
- News: only an actual RISK state blocks (NEWS_BLOCK file / HIGH-impact
  active); NEWS_UNKNOWN and missing macro/futures are NEUTRAL.
- Owner-directed envelope (decision 2026-06-11-01, locked to this ONE
  profile): 3%/trade worst case, daily 5% pauses entries, weekly 10% stops
  the service, 10 trades/day, 3 open max. Real-money policy untouched.

OPERATIONAL-INTELLIGENCE-001 status (previous): implemented; 726 tests then.
- Warmstart context report at startup; raw-confluence (4-dec) + margin +
  alt-profile display; DIRECTIONAL_CHOP_BREAKDOWN for MTF-backed moves;
  AdaptiveExposureGovernor (0/0/1/3/6 by conditions, profile-bounded);
  growth_evaluation profile (hard max 6/day); macro/futures neutrality
  proven. Survival anchors unchanged.

SIZING-001 status (previous): implemented; 709 tests then.
- "invalid lot size 0.0" Proven Defect fixed: milestone-aware lot resolver
  with explicit verdicts; min-lot promotion bounded by the phase ceiling;
  the same promotion in the planner order path; stale RiskLimits default
  aligned to the 1.0% policy ceiling.
- Threshold profiles current/demo_exploration via --thresholds (default
  unchanged); active profile printed in the banner.
- Terminal sizing diagnostics per candidate cycle.

FINAL-INTELLIGENCE status (previous): implemented; 692 tests then.
- News: provider architecture, impact/category calendar, 5 graded states;
  HIGH blocks, MEDIUM/soon reduce risk; UNKNOWN fail-closed.
- Macro/futures: stale-aware operator file configs/macro_context.json ->
  confluence confirmation (never a trigger); UNAVAILABLE when absent/stale.
- M1 refinement live (veto/delay only; cannot create trades).
- Calibration verdicts KEEP/TIGHTEN/LOOSEN/NEED_MORE_DATA with drawdown +
  missed-opportunity decomposition + per-segment expectancies.
- Executable wiring verification: scripts/verify_wiring.py -> 16 LIVE /
  1 PARTIAL / 2 UNAVAILABLE_BY_CONFIG / 0 MISSING.

INTELLIGENCE-002 status (previous): implemented; 668 tests then.
- Wiring verified per layer: 25_WIRING_MATRIX.md (17 LIVE, news PARTIAL,
  futures/macro PLACEHOLDER — honest, never faked).
- True MT5 MTF: M15/H1/M1 fetched natively; labelled degradation; conflict
  reporting; M1 display-only.
- Asian range + London/NY expansion in confluence + terminal.
- Dangerous-volatility classifier hard-gates the pipeline.
- Adaptive Demo Risk Policy (03_RISK_POLICY updated): per-phase bases/
  ceilings 0.40%/1.00% -> 0.20%/0.50%; daily/weekly anchors unchanged.
- Opportunity-audit verdicts extended; calibration replay tool ready
  (scripts/calibration_replay.py — recommendation only).

INTELLIGENCE-001 status (previous): implemented; 634 tests then.
- Live-evidence audit root causes FIXED: regime now classifies the recent
  ~5h window (was: whole 25h window -> near-permanent CHOPPY); CHOPPY is a
  graded gate (tradeable subtype + confluence >= 0.65), not a blind block;
  NEWS_RISK/NO_TRADE still always block.
- New live-path engines: ChopClassifier (6 subtypes), MtfAlignmentEngine
  (D1/H4/H1/M15/M5; H1+M15 aggregated honestly from M5), ConfluenceEngine
  (sweep/BOS-CHOCH/FVG/OB/premium-discount/displacement/session/spread/
  orderflow, with missing-evidence reporting), AdaptiveRiskEngine (capital
  phases, evidence-driven, policy-cap-clamped, contraction-only on adverse
  signals), sweepless BOS-continuation setup with swing invalidation.
- Terminal per cycle: MTF row, intel row, confluence + risk tier/% + chop
  subtype + regime reason, "needed: stronger ..." on NO_TRADE.
- Opportunity audit after 60 active-session no-trade cycles
  (reports/runtime/opportunity_audit_*).
- Unchanged safety: stop mandatory, governor final authority, gateway only
  order path, news fail-closed, demo-only, 0.5% policy cap intact.

CONTINUOUS-001 status (previous): implemented and committed; 583 tests then.
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

## Operator steps (Windows PowerShell) — DEMO-CHALLENGE run:
1. Maintain configs/news_windows.json (empty list = explicit all-clear);
   control/NEWS_BLOCK for manual blocks. Verify control/KILL_SWITCH absent.
2. py -3.12 scripts\demo_preflight.py            -> all 13 gates PASS
3. Optional rehearsal (identical loop, nothing sent):
   py -3.12 scripts\trading_service.py --profile demo_challenge --dry-run --stdout-progress
4. Ensure .env flags: TRADING_MODE=DEMO, REAL_TRADING_ENABLED=false,
   ALLOW_DEMO_ORDERS=true, ALLOW_MT5_ORDER_SEND=true, ALLOW_REAL_ORDERS=false
5. py -3.12 scripts\trading_service.py --profile demo_challenge --stdout-progress
   -> supervise; trades appear in MT5 Toolbox/Trade tab; every cycle prints
   momentum candidate/state, entry_plan, tactical_stop, lot_decision,
   first_trade_profit_state, add_on_allowed, and the exact WAIT reason
6. Stop: New-Item -ItemType File control\KILL_SWITCH
   Resume: Remove-Item control\KILL_SWITCH ; restart the service
7. Review daily service_eval_* / service_reflection_* and
   logs/demo_trade_journal.jsonl; the institutional profiles
   (continuous / growth_evaluation) remain available unchanged.

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

1. User runs the DEMO-CHALLENGE operator steps above on the Windows MT5
   host (dry-run first if desired, then live demo).
2. Record evidence (per-cycle challenge lines, ORDER SENT tickets vs MT5
   Toolbox, journal records, daily reports) and commit outcome notes.
3. If the experiment misbehaves: engage control\KILL_SWITCH; the
   institutional profiles remain available unchanged.

---

# Allowed Files

- scripts/, src/execution/, src/strategy/, src/broker/, src/reflection/,
  tests/, reports/runtime/
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

DEMO-CHALLENGE-001 is implemented (decision 2026-06-11-01): the FINAL
LAST-CHANCE aggressive momentum profile `--profile demo_challenge` — fixed
lots 0.05/0.10, tactical M1/M5 local stops (never structural), fresh entry
scan every candle, add-ons only into floating profit, max 3 open, daily 5%
pause / weekly 10% stop. It swaps ONLY the decision layer
(src/strategy/challenge_momentum.py + src/execution/challenge_planner.py);
session/gateway/journal safety is identical and the institutional model is
untouched. 753 tests pass. Guide the user to run
`py -3.12 scripts\trading_service.py --profile demo_challenge
--stdout-progress` on the Windows MT5 host (optionally --dry-run first) and
to collect the per-cycle challenge reasoning plus the trade journal as
evidence. Do not start the service. Do not enable real trading. The
demo_challenge envelope is reserved for that one profile; do not extend it.
Remaining external work: NEWS-001 / MACRO-001 / FUTURES-001 real feeds and
the BACKTEST-001 real-history decision.
