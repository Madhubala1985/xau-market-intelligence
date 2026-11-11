# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

---

# Current Project State

## Current Phase:
Phase 17: GOLD-INTEL-001 — built + gate FAILED, model FLAT (2026-07-07);
see 44_GOLD_INTEL_DESIGN.md + reports/research/gold_intel_gate_results.md

## GOLD-INTEL-001 (2026-07-07, owner directive: "superintelligent model, no
ML training, Claude decides"): built the three-brain gold_intel engine —
restored day-narrative brain + regime dial + cost gates + exit model,
brakes reinstated (3%/trade, 5%/10% daily/weekly, 3 open), gold_alpha
retired, Dukascopy replay harness (scripts/intel_replay.py) so multi-year
gates run in WSL. 906 tests pass. Commits b5d6ee2, a8c19bf, c23d80c + final.

GATE VERDICT (pre-registered, frozen before each run): **FAIL — FLAT.**
v1 flat-USD costs: −130.4R/577 trades/2/14 windows. v2 bps costs:
−73.7R/566/2/14. Zero-cost diagnostic: −1.56R/596 — the brain's decisions
are a coin flip BEFORE costs; costs only decide how fast it loses. The
day-narrative composite is falsified at scale; its June record was
regime-local. NO service start, NO run command, NO re-tune (gross ≈ 0
means selectivity has nothing to select — the gold_alpha EV-sweep lesson).
2026 holdout unexamined (clean for future protocols). Decisions
2026-07-07-02/-03.

NEXT EXACT STEP (unchanged from Phase 16, still the ONE live thread): the
owner runs, on the Windows MT5 host (read-only, no orders):
  py -3.12 scripts\measure_venue_spread.py
daily ~16:45-18:25 ET for ~2 weeks. Round-trip ≤ 2.6 bps revives
overnight-drift v1 at criterion 2 (2025 validation → 2026 holdout → demo
forward). Otherwise ALPHA-HUNT-001 closes as an honest negative extension
(intraday, time-of-day, events, H1 ML, daily price+macro ML, and now the
day-narrative composite are ALL falsified) in a 43_* terminal doc.

## (history) Phase 16 header below

## ALPHA-HUNT-001 (2026-07-05, owner directive): project reopened with full
authority — goal is a profitable model, high trade counts fine. Decision
2026-07-05-01: statistical honesty gates KEPT (they are the instrument);
demo-only + mandatory SL + no martingale + kill switch absolute; everything
else (process gates, cadence caps, closed-project freeze) removable. Target =
the never-tested space from 40_CONCLUSION.md: intraday at scale, time-of-day
structure, cross-asset M1 lead-lag, ML with purged walk-forward, vol structure.

State at handoff (2026-07-05, end of day):
- Phase A DONE: 7.5y Dukascopy M1 for XAUUSD/XAGUSD/EURUSD/DOLLARIDXUSD in
  data/raw/dukascopy/; XAUUSD converted to lab schema data/raw/XAUUSD_1M.csv
  (2.66M bars; zero-volume filler bars dropped — ALWAYS filter volume>0).
  VALIDATED: same-instant H1 opens vs GLD correlate 0.9997 (vs GC=F only
  0.88-0.95 — that gap is futures basis + async sampling, documented in
  scripts/dukascopy_to_lab.py). Old Yahoo intraday archived (archive_yahoo/).
- Phase B DONE: scripts/intraday_scan.py (212 cells, Bonferroni z>=3.68) →
  reports/research/intraday_scan.md. Findings: (1) M5 mean reversion z=-8.6
  but ~0.07 bps — sub-spread, untradeable; (2) ALL of gold's drift sits in
  the COMEX-reopen hour, ET-anchored (ET18 +2.35 bps t=4.7; first 10 min
  +2.52 bps t=9.3); (3) calm-regime H1 continuation (z≈3.2, sub-threshold)
  → Phase C feature.
- OVERNIGHT-DRIFT CANDIDATE v1: **FAILED its pre-registered gate** —
  reports/research/overnight_drift_protocol.md (protocol frozen BEFORE
  validation; criteria 1/4/5 failed). Tick-level truth: reopen spread 5.7
  bps kills reopen entry; pre-close entry (16:50→18:20 ET, gross +3.09 bps
  t=11.1, positive 6/6 train years) nets only +0.13 bps (t=0.22, n=157
  sampled days) through the measured 2.29 bps Dukascopy entry spread. The
  anomaly is REAL in mids and lives inside the spread. Conditional revival:
  measure the REAL venue cost on the Exness demo (symbol_info spread at
  16:50/18:20 ET for ~2 weeks); if all-in ≤ ~1.3 bps → re-enter at
  criterion 2. Evaluator: scripts/overnight_drift_run.py. 2025+2026 data
  remain UNEXAMINED for this rule.
- PROGRAM LESSON: at ~2 bps retail round-trip, tradeable XAU effects need
  edge >> 5 bps/trade → 4h-48h holds, not sub-hour windows.
- Phase C DONE (2026-07-05): ml_walkforward.py — all 6 combos No Edge
  (best IC +0.043 t=1.24, bar 2.64). Phase B2 DONE: event study — no
  post-announcement drift (1154 events).
- Phase C2 DONE (2026-07-07, decision 2026-07-07-01): daily-horizon ML with
  JOINT price + macro features. Protocol frozen BEFORE the run:
  reports/research/daily_ml_protocol.md. Script: scripts/ml_daily_macro.py.
  D1 2011-2025 (2026 untouched holdout), Ridge + HGB × 1/5/20-day horizons,
  expanding walk-forward (3y initial, 126-day windows, horizon embargo),
  pooled non-overlapping OOS Spearman IC, Bonferroni t>=2.64, top-decile
  net > 0 at 4.5 bps RT. Result: ALL 6 No Edge (best hgb h=5 IC +0.097
  t=+2.18; hgb h=20 16/20 positive folds but n=126 → t=+1.14). All ICs
  positive — the same weak long-tilt as June's macro-only model; not
  provable at the bar; the bar was NOT weakened post hoc.
  Report: reports/research/ml_daily_macro.md.
- NEXT EXACT STEP: the ONE live thread is the venue-cost measurement for
  overnight-drift v1 — the OWNER runs, on the Windows MT5 host (read-only,
  no orders):  py -3.12 scripts\measure_venue_spread.py
  daily at ~16:45-18:25 ET (or leave it running) for ~2 weeks. If measured
  round-trip ≤ 2.6 bps → v1 re-enters at criterion 2 (2025 validation, then
  2026 holdout, then demo forward). If it fails → close ALPHA-HUNT-001 as an
  honest negative extension of 40_CONCLUSION.md (now covering intraday,
  time-of-day, events, H1 ML, daily price+macro ML) in a 43_* terminal doc.
  No demo deployment of anything: nothing has passed a gate.

## (history) Phase 15 header below

## RESEARCH-LAB-001 (2026-06-17, owner directive): STOP building trading bots.
Repo pivoted to an XAU/USD edge-discovery research lab. No live orders; trading
service not run; repo is infrastructure only. Built `research/` package
(data_loader, metrics+frozen classification, causal forward-fill simulator with
spread/slippage stress grid + session breakdown, report renderer + cross-setup
RANKING) and **all 5 candidate setups** (versioned, mechanical, each with a
positive detection test): (1) Asian-low sweep→reclaim→displacement→FVG long;
(2) Asian-high sweep→rejection→bearish CHOCH→FVG short; (3) NY sweep of London
high/low→failed continuation→reversal; (4) H1-BOS trend continuation→M5 FVG
retest; (5) post-spike chop NO-TRADE filter (measured as expectancy uplift).
Reuses MarketStructureEngine (CHOCH/BOS) + ZoneEngine FVG semantics. Added
scripts/export_mt5_history.py (Windows-side, DATA-FETCH ONLY — never order_send)
and scripts/research_run.py. Self-test: tests/test_research_lab.py (14 pass;
834 collected). Design: 29_RESEARCH_LAB.md.
Classification gate: ≥100 filled trades + expectancy ≥+0.10R + PF ≥1.30 + holds
under cost grid ⇒ Proven Edge Candidate (only then may automation be proposed).

EDGE SEARCH ITERATION 1 (2026-06-18, autonomous — owner granted full autonomy):
Got real data (scripts/fetch_yahoo_history.py → GC=F proxy, ~60d M5 / ~2y H1).
Systematic edge scan (scripts/edge_scan.py): only real signal is H1 trend/breakout
(+0.60 ATR/24h, 55.5%, n=1478); H1 reversion loses; M5 reverts short-horizon.
Built donchian_breakout_trend (H1), momentum_continuation, mean_reversion_m5;
added MARKET entry + time-stop to the harness. ALL 7 setups = No Edge /
Insufficient Data. Donchian edge is NON-STATIONARY: train(2024-25) negative,
test(2026) positive → fails the train/test gate (scripts/donchian_tune.py). NO
Proven Edge Candidate; automation NOT justified; nothing deployed. Writeup:
30_RESEARCH_FINDINGS.md. NEXT: (1) broker-feed multi-year M5 export for real
stationarity testing on the trade timeframe; (2) regime-filtered H1 breakout as
the top hypothesis — must be validated train/test before it counts. Do NOT
forward-test for "edge" (can't create one that isn't there). 22 tests pass.

REGIME-BET DEMO DEPLOY (owner choice 2026-06-18, eyes-open): owner chose to run
the vol+trend-filtered breakout on demo as an explicit BET (not a proven edge).
Runner generalized: exec_tf param (H1/D1) + MARKET entry fires immediately
through the gateway. Run: `py -3.12 scripts\research_forward_runner.py --regime-bet
[--regime-tf H1|1D] [--risk-pct 0.01] [--dry-run]`. Banner labels it a BET;
no new entries when vol/trend regime is off; wide daily ATR stops may not size
on a ~$2k account (use H1 or a larger demo balance). Still demo-locked. This is
NOT a reversal of the no-edge verdict — it is a labeled regime bet the owner
opted into. 23 tests pass.

DEMO FORWARD-TEST RUNNER (owner directive 2026-06-17): src/execution/research_forward.py
(ResearchForwardRunner) + scripts/research_forward_runner.py forward-test the
UNPROVEN setups on the demo account. Detects fresh M5 signals, manages pending
mitigation entries (invalidation-first/expiry/next-bar fill = backtest mirror),
routes every fill through the existing ExecutionGateway (real-money refusal,
kill switch, demo preflight, RiskGovernor, stops-level all apply). Demo-locked
(ctor raises on real flags). Market-on-touch fill. Runs ONLY on the Windows MT5
host (refuses elsewhere with ENVIRONMENT_ISSUE). Tests: tests/test_research_forward.py
(4 pass; 18 with the lab; full suite collects clean). NOT evidence of an edge —
no backtest exists yet. To run demo: `python scripts/research_forward_runner.py
--dry-run` first, then without --dry-run to send demo orders.

NEXT EXACT STEP: get data. On the Windows MT5 terminal, in the venv, run
`python scripts/export_mt5_history.py --years 3` → writes data/raw/XAUUSD_*.csv;
sync those CSVs to this env; then `python scripts/research_run.py` produces
reports/research/london_sweep_reclaim_long_v1.md (the first real evidence table).
After that: implement Setups 2–4 as separate versioned modules under
research/setups/. Do NOT propose any execution model until a setup reaches
Proven Edge Candidate.

## (history) Phase 14: From-scratch profit model — gold_alpha (GOLD-ALPHA-001)

## GOLD-ALPHA-001 (2026-06-16, owner-directed): built from scratch; all prior
profiles retired/deleted. One profile `gold_alpha` (EV-scored setups,
protected SL, exit/trail, post-trade attribution loop). 820 tests pass.
Commit 5abf550. REPLAY: -15.93R/10d, 17% win -> SHIP: NO (uncalibrated p_win +
inflated far targets; EV-bar sweep flat at -15.91R). NOT run live (failed the
validate-before-live gate; account flat $2000). Read
reports/runtime/OVERNIGHT_STATUS.md. Next: owner picks — restore the proven
day-narrative edge under the gold_alpha path, OR build a calibrated p_win model.
Run command (only if a future build SHIPs): py -3.12 scripts\trading_service.py
--profile gold_alpha --stdout-progress

## (history below) Phase 13: liquidity_intel (LIQUIDITY-INTEL-001)

## Current Task ID:
LIQUIDITY-INTEL-001 (owner-directed, 2026-06-15): full rebuild into ONE
clean autonomous XAU/USD model. All prior profiles (demo_challenge,
smc_challenge, smc_v2) and the dual execution paths RETIRED. One account
source (.env), one execution path, one journal, one accounting source
(MT5), one trading service, one decision engine. DEMO-ONLY and all risk
anchors absolute. IMPLEMENTED on branch rebuild/liquidity_intel; 810
tests pass; all modules compile. See 27_LIQUIDITY_INTEL_DESIGN.md.

State at handoff (2026-06-15):
- AGGRESSIVE GROWTH MODE (decision 2026-06-15-02, owner-directed, DEMO):
  throttles removed (daily/weekly loss stops, cooldown, open cap->5,
  per-day cadence relaxed to 3); per-trade size 8%/5% (cap 10%),
  compounding. KEPT: mandatory SL, no martingale/averaging, MT5 truth,
  kill switch, demo-only. Cadence pinned at 3/day by the entries sweep
  (positive to 3/day: +2.30R; negative at 4+/day) — overtrading kills the
  edge. 03_RISK_POLICY.md updated; 864 tests pass.
- OPTION 1 SHIPPED: the from-scratch posture engine FAILED its replay
  ship gate (-27R/10d, 92 trades, 18% win). The liquidity_intel ENGINE is
  now the proven smc_v2 day-narrative brain on the same single path
  (LiquidityIntelEngine subclasses SmcV2Pipeline; smc_execution/smc_v2/
  day_narrative are internal, not profiles). Re-run ship gate (10d real
  history): +2.43R / 23 trades / 39% win / DD 6.3R -> SHIP: YES. 864
  tests pass. Report: reports/runtime/liquidity_intel_replay.md.
- NEW PLANNER src/execution/intel_planner.py (IntelTradePlanner; the one
  equity-scaled, fully-gated planner; never sends).
- SINGLE PATH: scripts/trading_service.py builds only the
  liquidity_intel engine + IntelTradePlanner (fork removed);
  session_profiles.py has ONE profile + a RETIRED-name guard; the four
  old decision modules and the v2 scripts + demo_session_run.py deleted.
- CHASSIS reused unchanged (MT5 truth, gateway, governor, kill switch,
  journal, reconciliation, trailing).
- VALIDATION pending on the Windows host: run the replay ship gate
  (below) over real history before any live trading.

## SINGLE RUNBOOK (Windows PowerShell, repo root) —
1. Verify no kill switch:   Test-Path control\KILL_SWITCH   (False)
   If True: Remove-Item control\KILL_SWITCH
2. REPLAY SHIP GATE (decides go/no-go; reads real MT5 history, sends
   nothing):  py -3.12 scripts\decision_replay.py --days 25
   -> reports/runtime/liquidity_intel_replay.md. SHIP only if net R
   positive, DD <= 12R, >= 10 trades. Otherwise stay FLAT (do not trade).
3. Preflight (13 gates):    py -3.12 scripts\demo_preflight.py
4. Start (only if the ship gate passed):
   py -3.12 scripts\trading_service.py --profile liquidity_intel --stdout-progress
5. Watch per cycle: accounting line (mt5_balance/equity/free_margin,
   realized_daily_pnl, floating_pnl, accounting_verified), htf_context
   (all six TFs), posture + narrative, liquidity_map + sweep_status,
   structure_state + fvg_ob + premium_discount + orderflow,
   smc_anchor/entry_trigger, tactical_stop + stop_logic (SL beyond the
   pool) + sl_tp_trail, reentry_plan/waiting_for on every NO_TRADE.
   Verify each CLOSE_DETECTED vs the MT5 history tab (source=MT5_HISTORY).
6. Stop any time: New-Item -ItemType File control\KILL_SWITCH (remove
   before the next start). Self-stops: daily 5% pause, weekly 10% stop,
   kill switch, Ctrl+C.
7. Do NOT pass --profile smc_v2 / smc_challenge / demo_challenge /
   continuous (RETIRED — get_profile refuses them).

Previously (RETIRED by this rebuild): SMC-V2-001 day-narrative brain.

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

SUPERSEDED by LIQUIDITY-INTEL-001 (2026-06-15): smc_v2 (and the whole
SMC/challenge family) is RETIRED. The runbook is now the SINGLE RUNBOOK
above (--profile liquidity_intel, gated by the decision_replay ship bar).
smc_v2's prior result (+7.0R/8.5mo longhaul, +8.16R unseen validation)
is recorded for history only; the new engine is from-scratch and must
re-earn its edge on the real-history replay before any live trading.

Previously: SMC-EXECUTION-008/b/c (H8 family) and
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
