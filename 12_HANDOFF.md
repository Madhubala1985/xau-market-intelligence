# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

---

# Current Project State

## Current Phase:
Phase 12: Live Demo Readiness — continuous service operational; FINAL
LAST-CHANCE demo_challenge experiment ready

## Current Task ID:
SMC-V2-001 (decisions 2026-06-12-10 and the ownership transfer that
evening — see memory/ownership-transfer.md): the owner handed the model
and the demo account to Claude entirely (full power of attorney, no
approvals), with the standing critique that the model trades like an
indicator bot (one trade after another) instead of identifying
institutional moves with patience. DEMO-ONLY and all risk anchors
remain absolute.

State at handoff (Fri 2026-06-12 ~19:3x UTC, market closed for the
weekend at 21:00, account week resets Monday 2026-06-15):
- Service STOPPED flat (kill switch cleared, no open positions).
  Campaign account login ..63 Trial14 XAUUSD, balance ~1,904.70
  (-4.8% from the 2,000 baseline). Live day 2026-06-12: trades 20-24
  (-65.29 net), all stops honored, zero broker/accounting defects.
- Live fixes shipped during the day: SMC-EXECUTION-008 H8 zone
  consumption (85774b4), 008b protective-exit scope (9c89d97), 008c
  clearance cap (772438d). 854 tests green.
- SMC v2 decision brain BUILT (commits 10b7512..): day_narrative.py
  (pure day classifier), smc_v2.py (narrative -> conviction ->
  playbooks -> quality bar; trade memory; institutional cadence cap
  3/day; trend runner targets; structural-stop mode), decision_replay
  engine + scripts/decision_replay.py + scripts/v2_sweep.py
  (walk-forward: tune on 15 train days, judge on unseen days).
- REPLAY EVIDENCE (25 days real history): v1 -82.7R / DD 96.8 / 636
  trades — systematically losing, retire it. v2 (pre-knobs) -5.2R /
  DD 15.1 / 158 trades. 12-day window: v2 +10.7R vs v1 -36.8R. Six
  manual iterations proved per-day fixes degrade the whole (history in
  11_DECISION_LOG + commit messages).
- SHIP BAR (self-imposed, non-negotiable): a v2 variant trades live
  demo Monday ONLY if its walk-forward VALIDATION days (unseen) are
  positive. Otherwise NO trading — protecting the 1,904 is the
  position. v2 sweep over selectivity variants was RUNNING at handoff:
  logs/v2_sweep_run1.log -> reports/runtime/v2_sweep.md/.json.

RESOLVED (decisions 2026-06-12-11/-12): smc_v2 ships Monday with the
MAXIMUM-SELECTIVITY knobs (quality bar 0.70, 2 entries/day, 3R trend
targets), confirmed on two independent measures — the 8.5-month
longhaul replay (+7.0R, 7/10 months positive, DD 22R; the defaults
measured -12.9R and were superseded) and the walk-forward sweep's
unseen validation days (+8.16R, best of 10). Honest expectancy: +0.038
R/day under punitive fills — positive, below the +0.15 goal-grade bar;
live fills are cheaper, week 1 measures the truth. v1 (smc_challenge)
is RETIRED from live use (-82.7R/25d, -12.9R..-83R everywhere). Week 1
= evidence week with a self-imposed early stop at -5% weekly net (hard
floor 10% unchanged). Reports: v2_longhaul.md, v2_sweep.md.

## MONDAY RUNBOOK (2026-06-15, after 00:00 UTC week reset) — operator
Windows PowerShell, repo root:
1. Verify no kill switch:   Test-Path control\KILL_SWITCH   (False)
   If True: Remove-Item control\KILL_SWITCH
2. Preflight (13 gates):    py -3.12 scripts\demo_preflight.py
3. Start:  py -3.12 scripts\trading_service.py --profile smc_v2 --stdout-progress
4. Watch per cycle: narrative=STATE conviction playbooks evidence[...],
   accounting_verified=true, CLOSE_DETECTED lines vs MT5 history.
   Expect FEW trades (cap 3/day) — long NO_TRADE stretches with
   DAY_NARRATIVE_*/CONVICTION/QUALITY reasons are the design.
5. Stop any time: New-Item -ItemType File control\KILL_SWITCH
   (service stops cleanly; remove the file before the next start).
6. Self-stopping: daily 5% net pause (entries blocked to next UTC
   day), weekly 10% net stop (service exits), kill switch, Ctrl+C.
7. Do NOT run --profile smc_challenge or demo_challenge (retired;
   replay -82.7R/25d). Reports: reports/runtime/supervision_ledger.md,
   v2_sweep.md, smc_v2_replay.md.

Previously: SMC-EXECUTION-008/b/c (H8 family, this morning) and
SMC-EXECUTION-007 doctrine — see CURRENT_STATE.md.

Previously: SMC-EXECUTION-007 (decision 2026-06-12-04): owner-directed decision-layer
rebuild after the 14-trade live watch (balance 1,946.78, -2.7%; full
evidence in reports/runtime/supervision_ledger.md). Doctrine now: D2
stale-anchor guard, D3 trend-day consensus override, D5 counter-consensus
displacement requirement, D6 market-state gate (volatility+chop on the
m5[:-1] environment — consolidation is NOT traded), H6b sweep freshness
at the rejection extreme, H7 two-leg pyramid cap. Chassis (gateway/
accounting/equity sizing/stops/trailing/brakes) unchanged — zero
execution defects in 14 live trades. 814 tests pass; safety passes.

Previously: SMC-EXECUTION-003: equity-scaled risk sizing (1.0%/1.5% by tier,
compounds with equity, 3% cap & all brakes unchanged) + per-account MT5
trade count (fetch_entry_count_since). Owner's "remove the cap"
partially refused — envelope brakes intact.

Previously: SMC-EXECUTION-002 (implemented after the first live smc_challenge run;
owner authorized Claude-supervised runs this session)

## Current Task Goal:
Live-run the SMC execution mode, collect evidence, fix only proven/
high-confidence defects. DONE for run 1 (61 cycles 2026-06-11
17:27-17:58 UTC, clean KILL_SWITCH stop): 1 trade (LOSS -30.13, SL +
spike slippage — Market Artifact), journal == MT5 history exactly, all
six TFs + killzone/liquidity/anchor/trigger gates active, 0 rejections.
D1 defect found and fixed (decision 2026-06-11-04).

## Current Status:
SMC-EXECUTION-002 implemented (D1 + D1b). 801 tests pass; safety check
passes.
- D1b (decision 2026-06-11-05): deposits can no longer dilute the
  MT5-tightened daily/weekly loss percentages — the period-start
  denominator subtracts balance operations
  (MT5DataAdapter.fetch_balance_ops_since; unknown ops => deposit-free
  fallback, still a tighten). Trigger: owner's +176.59 top-up to exactly
  2,000.00 made the daily figure read 8.11% instead of the true 8.83%.
- The weekly stop on account *******95 stays in force (true weekly loss
  170.4% of the 1,146.02 week start) until Monday 2026-06-15 UTC.
  Deposits do NOT reset it (by design). A genuinely fresh demo login in
  .env restarts the campaign cleanly; journal-based trades_today=10
  blocks entries until the UTC rollover either way.
- D1 (High-Confidence, FIXED): governor daily/weekly loss inputs were
  journal-pnl only; the morning pre-fix run's fabricated WINs hid the
  real MT5 -176.59 day (-8.8% of day start) => DAY_PAUSED never fired
  (d=0.017 printed). _mt5_tightened_risk_state() in demo_session.py now
  tightens the snapshot with MT5 realized P&L (day start + ISO week
  start) every verified cycle — tighten-only; unverified accounting
  unchanged (entries already blocked). Tightened snapshot reaches
  pipeline, exposure governor, planner risk_inputs, gateway RiskContext,
  CycleOutcome.risk (DAY_PAUSED label + weekly RISK_SHUTDOWN).
- VALIDATED LIVE (run 2, 2026-06-11 18:20 UTC): on restart the first
  cycle printed risk=WEEKLY_LIMIT and the service stopped cleanly with
  RISK_SHUTDOWN weekly loss 0.5172 >= 0.10. Verified directly against
  MT5 history: 30 XAUUSDm trade deals since Monday 2026-06-08, net
  -1952.98 (pre-SMC profiles Mon-Wed -1776.39 + today -176.59) — losses
  the poisoned journal had hidden. Per policy NO service trading on this
  account until the week resets (Monday 2026-06-15 UTC). For the $2,000
  campaign the owner should fund a FRESH Exness demo account at exactly
  2,000 and update .env — clean baseline, all anchors intact.
- Tracked hypothesis (sample of one, NOT acted on): stop sat just past
  the obvious local swing and was swept in a spike; candidate = require
  sweep completion / anchor stops beyond the engineered-liquidity
  extreme. Decide only on more session evidence.

SMC-EXECUTION-001 status (previous): implemented; 792 tests then.
- ACCOUNTING (Proven Defect fixed): history_deals_get(dates, position=)
  silently drops the position filter — every account deal in the window
  (incl. balance ops) was summed, fabricating "WIN pnl=1158.62" on a
  losing trade. Now: fetch_closed_position(position=ticket only, per-deal
  position_id check, balance-deal exclusion, net = profit+commission+swap,
  close price/time/reason from the OUT deal);
  fetch_realized_pnl_since(day_start) for the terminal daily P&L; per-cycle
  accounting snapshot with accounting_verified gate (UNVERIFIED blocks new
  entries: ACCOUNTING_UNVERIFIED_BLOCK_NEW_ENTRIES); LOSS_COOLDOWN after 2
  consecutive MT5 losses (30 min).
- STRATEGY: src/strategy/challenge_momentum.py DELETED (retail momentum
  gone); src/strategy/smc_execution.py NEW. Gates per candle:
  A HTF (D1/H4/H1/M15 MtfAlignment or D1/H4 bias) -> candidate;
  B session/liquidity (kill zone OR ASIAN_LOW/HIGH_SWEEP OR
  SESSION_LIQUIDITY sweep OR LIQUIDITY_TARGET_AHEAD);
  C SMC anchor (SWEEP_DISPLACEMENT > FVG_RETEST > OB_RETEST > BREAK_RETEST
  > CHOCH > BOS) — momentum alone = SMC_ANCHOR_MISSING, no trade;
  D local trigger (MITIGATION_REJECTION / PULLBACK_REJECTION /
  BREAK_RETEST / CONTINUATION) + tactical stop from FVG/OB boundary, sweep
  rejection extreme, or local M1/M5 swing (+ ATR/spread buffer, 8 USD
  ceiling) with stop_logic / invalidation_reason / risk_if_sl_hit printed.
- ANTI-FREEZE: every refusal prints reentry_plan + waiting_for
  (FVG_RETEST/OB_RETEST/LOCAL_SWING/SWEEP/BREAK_RETEST) and rescans next
  candle.
- ADD-ONS: protected winners only — break-even stop or >= 0.5R floating
  (live +0.21 case => ADDON_BLOCKED_PROFIT_TOO_SMALL); same-candle (300s)
  and weakened-context blocks; hedge/max-3/post-loss unchanged.
- PROFILES: smc_challenge (primary) + demo_challenge (deprecated alias,
  same SMC behavior); challenge envelope unchanged (3%/trade worst case,
  daily 5% pause, weekly 10% stop, 3 open max, fixed lots 0.05/0.10).

BROKER-EXECUTION-001 status (previous): implemented; 769 tests then.
- PROVEN root causes of the live rejections (request builder, not symbol
  case): stale candle-close price outside the deviation window + missing
  type_filling. Fixed: live ask/bid in the request; filling mode from
  symbol_info (IOC > FOK > RETURN); graceful degradation when
  symbol_info/tick are unavailable.
- Journal now persists typed execution events (ORDER_ATTEMPTED/SENT/
  REJECTED/BLOCKED/ERROR) with retcode + name + broker comment + the exact
  XAUUSDm request + quotes + symbol trade conditions + margin check;
  searchable with Select-String "ORDER_REJECTED","retcode","broker".
- ORDER_BLOCKED_STOPS_LEVEL guard: an SL/TP inside the broker minimum stop
  distance is never sent and never silently widened.
- Terminal prints decision=ORDER_REJECTED_BY_BROKER with
  reason=retcode/comment + request_symbol/volume/price/sl/tp (the
  contradictory "BLOCKED: all risk checks passed" is gone);
  ORDER_ERROR is its own label. Runtime report refreshes live with the
  active profile.
- The journal's XAUUSDM on TradeDecision/TradeRecord is the CANONICAL
  comparison form (F-14 design) — the wire request always carried XAUUSDm;
  the new ORDER_* events record the exact broker case.
- Strategy / momentum / lot / tactical-stop logic UNCHANGED.

DEMO-CHALLENGE-001 status (previous): implemented; 753 tests then.
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

## Operator steps (Windows PowerShell) — SMC EXECUTION run:
1. Maintain configs/news_windows.json (empty list = explicit all-clear);
   control/NEWS_BLOCK for manual blocks. Verify control/KILL_SWITCH absent.
2. py -3.12 scripts\demo_preflight.py            -> all 13 gates PASS
3. Optional rehearsal (identical loop, nothing sent):
   py -3.12 scripts\trading_service.py --profile smc_challenge --dry-run --stdout-progress
4. Ensure .env flags: TRADING_MODE=DEMO, REAL_TRADING_ENABLED=false,
   ALLOW_DEMO_ORDERS=true, ALLOW_MT5_ORDER_SEND=true, ALLOW_REAL_ORDERS=false
5. py -3.12 scripts\trading_service.py --profile smc_challenge --stdout-progress
   -> supervise; every cycle prints the MT5 accounting line
   (mt5_balance/equity/free_margin, realized_daily_pnl, floating_pnl,
   accounting_verified), htf_context, killzone, liquidity_context,
   smc_anchor, entry_trigger, tactical_stop + stop_logic + risk_if_sl_hit,
   and reentry_plan/waiting_for on every NO_TRADE.
   Verify each CLOSE_DETECTED (outcome/net_pnl/reason, source=MT5_HISTORY)
   against the MT5 history tab. Broker rejections persist as before:
   Select-String -Path logs\demo_trade_journal.jsonl -Pattern "ORDER_REJECTED","retcode","broker"
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

SMC-EXECUTION-001 is implemented (decision 2026-06-11-03) on top of
DEMO-CHALLENGE-001 / BROKER-EXECUTION-001: the retail momentum pipeline is
DELETED; --profile smc_challenge (and its alias demo_challenge) runs the
institutional SMC execution mode — A+B+C+D gates (HTF context, kill-zone/
liquidity, SMC anchor, local trigger + structurally justified tactical
stop), re-entry plans instead of silent blocks, add-ons only onto protected
winners (>=0.5R or break-even). MT5 is the only source of truth for P&L:
fetch_closed_position / fetch_realized_pnl_since (the
history_deals_get(dates, position=) contamination defect is fixed),
per-cycle accounting_verified gate, LOSS_COOLDOWN after 2 MT5 losses.
792 tests pass. Guide the user to run
`py -3.12 scripts\trading_service.py --profile smc_challenge
--stdout-progress` and to verify CLOSE_DETECTED lines against the MT5
history tab. Do not start the service. Do not weaken risk or the gates.

DEMO-CHALLENGE-001 context: the FINAL
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
