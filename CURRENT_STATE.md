# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 16: ALPHA-HUNT-001 — project REOPENED (owner directive 2026-07-05)

## Current Task

ALPHA-HUNT-001 (owner directive, 2026-07-05): owner reopened the project with
full authority granted to Claude: make the model profitable, any changes
allowed, high trade counts fine. Interpretation recorded in 11_DECISION_LOG.md
(2026-07-05-01): process gates removed; statistical honesty gates KEPT;
demo-only/mandatory-SL/no-martingale/kill-switch absolute. Program:
42_ALPHA_HUNT.md.

DAY-1 RESULTS (2026-07-05, decisions 2026-07-05-01/02):
- Phase A DONE: 7.5y Dukascopy M1 × 4 instruments (XAU/XAG/EUR/DXY),
  validated (GLD same-instant corr 0.9997; filler bars filtered).
  scripts/fetch_dukascopy.py + dukascopy_to_lab.py. data/raw/XAUUSD_1M.csv.
- Phase B DONE (intraday_scan.py, 212 cells, Bonferroni): gold's entire
  intraday drift sits in the COMEX-reopen hour (ET18, t=4.7 hourly / t=9.3
  first 10 min); M5 mean reversion real but ~0.07 bps (sub-spread); calm-
  regime continuation z≈3.2 sub-threshold.
- OVERNIGHT-DRIFT v1 (the reopen anomaly, pre-close entry 16:50→18:20 ET):
  gross +3.09 bps/trade t=+11.1, positive 6/6 train years — but FAILED its
  pre-registered gate (criteria 1/4/5): tick-measured net through the 2.29
  bps spread is +0.13 bps (t=0.22, n=157). The anomaly lives inside the
  spread. Protocol + verdict: reports/research/overnight_drift_protocol.md.
  CONDITIONAL REVIVAL: scripts/measure_venue_spread.py (Windows, READ-ONLY)
  measures real Exness XAUUSDm spread at 16:50/18:20 ET; if round-trip
  ≤ 2.6 bps over ≥8 days → v1 re-enters at criterion 2 (2025 validation,
  then 2026 holdout, then demo forward). 2025/2026 remain unexamined.
- Phase C DONE (ml_walkforward.py): purged expanding walk-forward, Ridge +
  HistGradientBoosting × horizons 4/12/24 H1 bars, cross-asset features —
  ALL 6 combos No Edge (best IC +0.043, t=1.24; bar was t≥2.64).
- Phase B2 DONE (event study, reports/research/event_study.md): no post-
  announcement drift after 533 × 08:30 ET drops, 82 FOMC, 539 × 10:00 ET
  events. Gold digests macro prints in minutes.
- STANDING LESSON: at ~2 bps retail half-turn, tradeable XAU effects need
  edge >> 5 bps/trade; nothing in the free intraday space clears it.
- PHASE C2 DONE (2026-07-07, decision 2026-07-07-01): daily-horizon ML with
  JOINT price + macro features (the one untested daily combination). Protocol
  frozen pre-run (reports/research/daily_ml_protocol.md): D1 2011-2025,
  Ridge + HGB × 1/5/20-day horizons, purged expanding walk-forward, pooled
  non-overlapping OOS IC, Bonferroni t>=2.64, 4.5 bps cost bar. ALL 6 combos
  No Edge (best hgb h=5 IC +0.097 t=+2.18; all ICs positive = the same weak
  long-tilt as the June macro model, never provable at the bar).
  reports/research/ml_daily_macro.md.
- NEXT: (1) owner/Windows runs measure_venue_spread.py ~2 weeks (the ONLY
  live thread left); (2) if it fails too, close ALPHA-HUNT-001 as an honest
  negative extension of 40_CONCLUSION.md — the negative result then covers
  intraday, time-of-day, events, H1 ML, and daily price+macro ML.

## (history) Phase 15 task text

RESEARCH-LAB-001 (owner directive, 2026-06-17): **Stop building trading bots.**
Pivot the repo to an XAU/USD edge-discovery research lab. No live orders; the
trading service is not run; the repo is infrastructure only. Goal: prove ONE
repeatable setup with positive expectancy on ≥100 occurrences before ANY
automation is allowed. Built `research/` package: data_loader (CSV from
data/raw/, M1-aggregation), metrics + frozen classification thresholds
(Insufficient Data <100 trades / No Edge / Weak Edge / Proven Edge Candidate),
a strictly-causal forward-fill simulator with a spread/slippage stress grid,
session breakdown, a report renderer + cross-setup RANKING, and **all FIVE
candidate setups** (versioned, fully mechanical, each with a positive detection
test): (1) London sweep of Asian low→reclaim→displacement→FVG long;
(2) London sweep of Asian high→rejection→bearish CHOCH→FVG short;
(3) NY sweep of London high/low→failed continuation→reversal; (4) H1-BOS trend
continuation→M5 FVG retest; (5) post-spike chop NO-TRADE filter measured as
expectancy uplift. Plus `scripts/export_mt5_history.py` (Windows-side, data-fetch
only) and `scripts/research_run.py`. Self-test: tests/test_research_lab.py
(14 pass; 834 total collected). Design: 29_RESEARCH_LAB.md.

DEMO FORWARD-TEST RUNNER (owner directive, 2026-06-17): per owner direction to
forward-test on the DEMO account, built `src/execution/research_forward.py`
(`ResearchForwardRunner`) + `scripts/research_forward_runner.py`. Detects fresh
M5 signals, manages pending mitigation entries (invalidation-first / expiry /
next-bar fill — mirrors the backtest), and routes every fill through the
existing ExecutionGateway so ALL safety applies (real-money refusal, kill
switch, demo preflight, RiskGovernor final authority, broker stops-level,
demo-only send). Demo-locked (ctor raises on real flags); PositionSizer refuses
sub-minimum lots. Windows-only (refuses elsewhere). Tests:
tests/test_research_forward.py (4 pass). NOTE: this is live DEMO observation,
NOT proof of an edge — no backtest exists yet (data/raw empty).

**Blocked on data:** MT5 is Windows-only/unavailable here and data/raw/ is empty,
so no real occurrences exist yet — every result reads *Insufficient Data* until
the one-time Windows export runs. Anti-curve-fit rules binding: no look-ahead,
versioned rules, no tiny-sample claims, mandatory cost stress.

## PROJECT CLOSED (2026-06-27): successful negative result — terminal docs written
The repo is closed as a finished research project. Terminal documents:
40_CONCLUSION.md (the question, full Phase 1-11 + isolation-battery evidence
chain, verdict, the one shipped artifact) and 41_METHODOLOGY.md (the reusable,
market-agnostic edge-falsification harness). Verdict: no isolated or composite
price-based edge in free daily/H1 XAU/USD survives a random baseline + OOS
replication; the only real effects (vol-regime, real-yields, COT) are
non-tradeable, risk-overlay only. Shipped artifact: the regime risk dial
(research/regime.py + scripts/gold_regime.py, advisory). Also: edge audit
(31_EDGE_AUDIT.md) + single-factor isolation battery (0/6 factors a hit). No
further strategy work warranted on free-data XAU/USD price patterns. 32 tests pass.

## RESEARCH ARC CONCLUDED (2026-06-18, full discretion): no daily edge; ship risk dial
After price-pattern + macro tracks (real data, 15y, multi-regime, walk-forward),
the verdict is final: NO tradeable daily edge in gold beats buy-and-hold on free
public data. Documented negative result. Shipped the one defensible artifact:
research/regime.py + scripts/gold_regime.py — an ensemble macro regime RISK DIAL
(advisory, not auto-trading; cuts drawdown in real-yield+dollar tightening
regimes; NOT alpha). Current reading: TIGHTENING (~33% suggested exposure). No
trading model deployed. Active-alpha search closed unless new data/resources.
Full arc: 30_RESEARCH_FINDINGS.md. Macro model: scripts/macro_model_run.py.
Tests pass (incl. tests/test_regime_signal.py).

## EDGE SEARCH ITERATION 1 (2026-06-18, autonomous): real-data backtest verdict
Pulled real gold history (GC=F Yahoo proxy: ~60d M5, ~2y H1) via
scripts/fetch_yahoo_history.py. Ran a systematic edge scan
(scripts/edge_scan.py): H1 trend persists (20-bar Donchian breakout +0.60 ATR/24h,
55.5%, n=1478); H1 mean-reversion loses; M5 is short-horizon mean-reverting.
Built + backtested 7 setups (4 SMC FVG, momentum_continuation, donchian_breakout_trend,
mean_reversion_m5). RESULT: NONE is a Proven Edge Candidate — all No Edge /
Insufficient Data. Critically, Donchian's edge is NON-STATIONARY (train ~2024-25
negative, test ~2026 positive) so it fails the train/test gate
(scripts/donchian_tune.py). Harness gained MARKET entry + time-stop exits.
Full writeup: 30_RESEARCH_FINDINGS.md; reports in reports/research/. Verdict:
automation NOT justified; do not deploy. Next: broker-feed multi-year M5 for
stationarity testing + a regime-filtered breakout hypothesis (validated train/test).
22 lab+forward tests pass.

## (history) Phase 14: From-scratch profit model — gold_alpha (GOLD-ALPHA-001)

GOLD-ALPHA-001 (owner-directed, 2026-06-16): built a brand-new from-scratch
XAU/USD profit-maximisation model; ALL prior profiles retired (liquidity_intel/
smc_v2/smc_execution/day_narrative deleted). One profile `gold_alpha`, one path,
one MT5 source, one planner, one journal. Engine = expected-value scorer over
enumerated setups (sweep-reclaim/trend-continuation/range-fade/BOS-retest);
protected SL beyond engineered liquidity; draw-on-liquidity targets; BE+ATR
trail + fast CHOCH-against exit; post-trade attribution loop
(src/strategy/trade_attribution.py) that down-weights failing setups. Full
per-cycle evidence terminal output. 820 tests pass. Design: 28_GOLD_ALPHA_DESIGN.md.
Commit 5abf550.

REPLAY VERDICT (10d real history): net -15.93R, 17% win, DD 16.77R -> SHIP: NO.
Root cause: the EV objective's p_win is uncalibrated (assumes ~35% vs realised
17%) AND far liquidity targets inflate target_R; an EV-bar sweep (0.15..0.85)
was identical -15.91R, so selectivity cannot rescue it. Per the owner's own
process (validate before live) and "don't run a model that loses", it was NOT
run live. Account confirmed flat ($2000, 0 positions). Honest morning report:
reports/runtime/OVERNIGHT_STATUS.md. Only the (now-retired) day-narrative brain
ever measured positive (+2.43R/10d). Recommendation pending owner: restore that
edge under the gold_alpha path, or build a calibrated p_win model.

Previously: LIQUIDITY-INTEL-001 — UPDATE 2026-06-15 (AGGRESSIVE GROWTH MODE,
owner-directed): owner directed removal of the throttling risk engine to
chase $2k->$10k on DEMO. Implemented + evidence-checked:
- REMOVED (throttles): daily-loss pause, weekly-loss stop, loss cooldown,
  open-position cap (->5), per-day entry throttle relaxed.
- AGGRESSIVE SIZE: per-trade risk 8% STRONG / 5% NORMAL (cap 10%),
  compounding (was 1.5%/1.0%). This is the real $2k->$10k lever.
- KEPT ABSOLUTE (owner's own rebuild non-negotiables): mandatory SL, no
  martingale/averaging, MT5 truth, kill switch, demo-only.
- EVIDENCE that forced one keep: the entries/day sweep (10d real history)
  showed +2.43R (2/day), +2.30R (3/day), then NEGATIVE at 4+/day
  (-2.69R) and unlimited (-1.07R). Overtrading destroys the edge, so the
  per-day cadence is set to 3 (the most aggressive value that still makes
  money), NOT unlimited. Final config replay: see
  reports/runtime/liquidity_intel_replay.md. 864 tests pass.
- Governor daily/weekly block MECHANISM retained in code (off in this
  profile; covered by test_risk_governor) so it can be re-enabled.

LIQUIDITY-INTEL-001 — UPDATE 2026-06-15 (OPTION 1, owner-directed): the
first-pass FROM-SCRATCH posture engine FAILED its replay ship gate
(real history 10d: -27.05R, 92 trades ~9/day, 18% win — it overtraded and
lost at every selectivity). Per owner direction, the single liquidity_intel
ENGINE was rebuilt around the only logic with a positive replay record —
the smc_v2 day-narrative brain — on the SAME clean single path
(LiquidityIntelEngine now subclasses SmcV2Pipeline; smc_execution/smc_v2/
day_narrative are INTERNAL to the one engine, not selectable profiles; the
planner/profile/path/anchors are unchanged). RE-RUN ship gate (same 10d
real history): net R +2.43 over 23 trades (~2/day), 39% win, DD 6.3R ->
SHIP: YES (reports/runtime/liquidity_intel_replay.md). 864 tests pass.
Shipped knobs: quality_bar 0.70, 2 entries/day, 3R trend targets.
Honest caveat: small sample/one window under punitive fills; the broader
smc_v2 validation was +7.0R/8.5mo. Below the original Current-Task text
(the from-scratch posture description) is SUPERSEDED by this update.

LIQUIDITY-INTEL-001 (owner-directed, 2026-06-15): FULL REBUILD into ONE
clean autonomous XAU/USD model. Every prior decision profile
(demo_challenge, smc_challenge, smc_v2) and the dual/institutional
execution paths are RETIRED and CANNOT run (get_profile raises; the
modules are deleted; tests/test_single_path.py enforces it). There is
now exactly one account source (.env), one execution path, one journal,
one accounting source (MT5), one trading service, one decision engine.

NEW MODEL / PROFILE: liquidity_intel. Run:
  py -3.12 scripts\trading_service.py --profile liquidity_intel --stdout-progress

- ENGINE (src/strategy/liquidity_intel.py, from scratch): a market
  POSTURE model — each cycle reads D1/H4/H1/M15/M5/M1 + liquidity map +
  sweeps + structure + FVG/OB + premium/discount + orderflow and decides
  for itself: TREND (continuation, 3R) / LIQUIDITY_REVERSAL (sweep+reclaim
  fade, 2R, stop beyond the rejection extreme) / RANGE_SCALP (1.5R) /
  WAIT (explicit re-arm, never silent) / FLAT (dangerous vol/chop/news).
  A fixed-weight quality bar gates entries; STRONG=1.5% / NORMAL=1.0%
  equity risk.
- STOP DOCTRINE: SL placed BEYOND the engineered liquidity pool
  (_protect_stop_from_pool pushes a stop past any resting pool it would
  sit at); too wide => reduce size or WAIT; never widened into the trap;
  hard 8 USD ceiling.
- PLANNER (src/execution/intel_planner.py): the ONE planner —
  equity-scaled sizing, mandatory SL, protected add-ons only, no
  hedging/averaging-down/martingale; never sends (gateway is the only
  path).
- CHASSIS REUSED UNCHANGED: MT5 adapter (source of truth), gateway,
  governor, kill switch, journal, reconciliation, break-even/trailing.
- EXIT/REVERSE: no gateway market-close path (one order path; stops never
  widen) — protective exits via SL/TP + trailing; reverse = fresh entry
  once flat. Engine surfaces MANAGE/EXIT/REVERSE intent for transparency.
- ENVELOPE (single, anchors absolute): 3%/trade, daily 5% pause, weekly
  10% stop, max 3 open, 25/day survival ceiling (quality bar governs real
  cadence — no artificial fixed cap), spread <= 1.0; REAL accounts refused.
- TESTS: 810 pass. New test_liquidity_intel / test_intel_planner /
  test_single_path; retargeted accounting/broker/profiles/service/replay.
- VALIDATION GATE: scripts/decision_replay.py --days 25 on the Windows
  host -> reports/runtime/liquidity_intel_replay.md/.json. SHIP BAR: net R
  positive, DD <= 12R, >= 10 trades, else stay FLAT live. Design contract:
  27_LIQUIDITY_INTEL_DESIGN.md.

Previously: SMC-V2-001 (decision 2026-06-12-10 + ownership transfer): the
v2 day-narrative brain shipped Monday with maximum-selectivity knobs.
RETIRED by this rebuild. v1 (smc_challenge) was already retired by replay
evidence (-82.7R/25d).

Previously: SMC-EXECUTION-008 (decision 2026-06-12-07): IMPLEMENTED — H8 zone
consumption. An MT5-verified SL loss consumes its zone: for 30 min a new
same-direction entry whose tactical stop sits within 8 USD of the
violated stop level and does not clear it by max(ATR(M5), 1.0) is
refused (ZONE_CONSUMED) with a re-entry plan. Pre-registered live test:
trades 18/19 re-faded one zone 3 min apart, -34.90; winners 8/17
(which cleared the violated level) stay allowed; distant prior losses
(trade 6) are out of scope (D6 territory). Session notifies the
pipeline on CLOSE_DETECTED reason=SL. 821 tests pass; safety passes.
Service run 13 restarted 2026-06-12 ~13:3x UTC with SMC-EXECUTION-007
doctrine + 25/day cap + H8.

Previously: SMC-EXECUTION-003 (decision 2026-06-11-06, owner-directed): IMPLEMENTED.
- EQUITY-SCALED SIZING replaces fixed challenge lots: tier 0.10/0.05 in
  setup_type selects 1.5%/1.0% of balance risked to the tactical stop;
  lot = floor(budget / loss_per_lot, step) — size compounds with equity
  toward the $2k->$10k->$20k milestones. Unchanged: 3%/trade survival
  cap, broker min/max/step, margin shrinks the lot never the stop,
  min-lot promotion only inside the cap. Strategy demotions still arrive
  as 0.05 => 1.0%.
- TRADES/DAY now counts THIS account's MT5 entry deals
  (fetch_entry_count_since); journal count kept only when MT5 history is
  unavailable (fail closed). Live evidence: the fresh campaign account
  was blocked all evening by 10 journal trades from the retired account.
- Owner's "remove the cap" request PARTIALLY REFUSED: 10/day cap, daily
  5% pause, weekly 10% stop, 3%/trade, max 3 open, loss cooldown all
  remain.
- 803 tests pass (+2 count-scoping, sizing tests updated to the new
  spec, fake order_send now records an MT5-true IN deal);
  pre_demo_safety_check.sh passes.

Previously: SMC-EXECUTION-002: IMPLEMENTED — live-evidence fix from the first
smc_challenge run (2026-06-11, 61 cycles, clean KILL_SWITCH stop).
- LIVE RUN EVIDENCE: 1 order sent (SHORT 0.05 on FVG_RETEST +
  MITIGATION_REJECTION in the NY kill zone, tactical local-swing stop,
  rr=2.0), closed LOSS net -30.13 by SL during a ~14 USD/min spike (SL
  slipped 3.5 — Market Artifact, broker-side slippage). Journal matched
  MT5 history exactly (ORDER_SENT retcode=10009; CLOSE_DETECTED
  source=MT5_HISTORY); balance 1853.54 -> 1823.41; accounting_verified
  EVERY cycle; all six TFs in every cycle (D1/H4/H1/M15/M5 + M1
  refinement); killzone/liquidity/anchor gates active (SESSION_LIQUIDITY,
  ASIAN_HIGH_SWEEP at 5.15x displacement correctly refused without a
  local trigger); reentry_plan/waiting_for printed on every NO_TRADE;
  0 rejections, 0 violations; MAX_TRADES cap (10/10) enforced.
- D1 HIGH-CONFIDENCE DEFECT FIXED (decision 2026-06-11-04): the governor's
  daily/weekly loss inputs came from journal pnl only — the morning
  pre-fix run's fabricated WINs (+1158.62 etc.) hid the real MT5
  -176.59 day (-8.8%), so DAY_PAUSED never triggered (printed d=0.017).
  Now _mt5_tightened_risk_state() tightens the RiskStateSnapshot every
  verified cycle with max(journal_pct, -realized_net/(balance -
  realized_net)) from fetch_realized_pnl_since(day_start / ISO week
  start); tighten-only, never loosens; unverified accounting leaves it
  untouched (entries already blocked); feeds pipeline, exposure governor,
  planner, gateway RiskContext, and the service DAY_PAUSED/weekly
  RISK_SHUTDOWN checks.
- 798 tests pass (+6 D1 tighten tests in tests/test_smc_accounting.py);
  pre_demo_safety_check.sh passes.
- Tracked hypothesis (NOT acted on — sample of one): the lone loss had
  the stop just past the obvious local swing (retail pool) and was swept;
  candidate refinement = enter after sweep completion / stop beyond the
  engineered-liquidity extreme. Needs more session evidence.
- D1 FIX VALIDATED LIVE (run 2): restart printed risk=WEEKLY_LIMIT on
  cycle 1 and stopped cleanly (RISK_SHUTDOWN weekly loss 0.5172 >= 0.10).
  Verified against raw MT5 history: 30 trade deals since Mon 2026-06-08,
  net -1952.98. This account is policy-stopped until Monday 2026-06-15
  UTC; recommended: fresh demo account funded at exactly 2,000 (update
  .env) as the clean $2k->$10k campaign baseline.
- D1b (decision 2026-06-11-05): the owner's +176.59 top-up (balance back
  to exactly 2,000.00) proved deposits dilute the deposit-free loss
  denominator (8.11% shown vs true 8.83%). New
  MT5DataAdapter.fetch_balance_ops_since; tighten denominator is now
  balance - realized_net - balance_ops_net (withdrawals enlarge it;
  unknown ops fall back to the deposit-free tighten). True weekly loss
  on this account: 170.4% of the real 1,146.02 week start. 801 tests
  pass (+3 D1b); safety check passes.

Previously: SMC-EXECUTION-001: IMPLEMENTED — the retail momentum behavior is REMOVED
and replaced by the institutional SMC execution mode
(--profile smc_challenge; demo_challenge is now a deprecated alias of the
SAME behavior), and MT5 is the ONLY source of truth for P&L/accounting.
- PROVEN accounting root cause fixed: history_deals_get(dates, position=)
  drops the position filter (the API variants are mutually exclusive) and
  summed EVERY account deal in the window — that fabricated
  "CLOSE_DETECTED outcome=WIN pnl=1158.62" on a losing trade. Close
  detection now uses history_deals_get(position=ticket) with per-deal
  position_id checks and balance-deal exclusion; outcome = sign of the MT5
  net (profit+commission+swap); CLOSE_DETECTED prints net_pnl /
  source=MT5_HISTORY / close_price / reason=SL/TP/MANUAL.
- Per-cycle MT5 accounting: mt5_balance/equity/free_margin,
  realized_daily_pnl (from today's MT5 trade deals only), floating_pnl,
  consecutive_losses, accounting_verified; UNVERIFIED accounting blocks new
  entries (ACCOUNTING_UNVERIFIED_BLOCK_NEW_ENTRIES, positions still
  managed); LOSS_COOLDOWN pauses entries 30 min after 2 consecutive MT5
  losses; capital_phase/next_milestone/
  milestone_mode=compound_growth_not_single_trade_target printed.
- A trade now requires ALL FOUR gates every candle: (A) D1/H4/H1/M15 HTF
  context, (B) kill zone or Asian/session liquidity event/target, (C) an
  SMC anchor (SWEEP_DISPLACEMENT/FVG_RETEST/OB_RETEST/BREAK_RETEST/CHOCH/
  BOS) — M1/M5 momentum alone CANNOT trade (SMC_ANCHOR_MISSING), (D) an
  executable local trigger + structurally justified tactical stop
  (FVG/OB boundary, sweep extreme, local swing + buffer; stop_logic /
  invalidation_reason / risk_if_sl_hit printed).
- Anti-freeze: failed gates print reentry_plan/waiting_for (FVG_RETEST/
  OB_RETEST/LOCAL_SWING/SWEEP/BREAK_RETEST) and rescan next candle — the
  570-cycle STOP_TOO_WIDE freeze is structurally impossible.
- Add-ons only onto PROTECTED winners: stop at break-even or floating
  >= 0.5R (the live +0.21 add-on is now ADDON_BLOCKED_PROFIT_TOO_SMALL);
  ADDON_BLOCKED_NOT_PROTECTED / _SAME_CANDLE (300s) /
  _SMC_CONTEXT_WEAKENED; hedge/max-3/post-loss blocks unchanged.
- 792 tests pass (+24: SMC gates 14, MT5 accounting 10);
  pre_demo_safety_check.sh passes. Run:
py -3.12 scripts\trading_service.py --profile smc_challenge --stdout-progress

Previously: BROKER-EXECUTION-001: IMPLEMENTED — demo order rejections fixed and fully
diagnosable. Root causes (proven, request builder — NOT symbol case): the
market order carried the stale M5 candle close as price (outside the
deviation window exactly when momentum fires => REQUOTE/INVALID_PRICE) and
no type_filling (=> 10030 INVALID_FILL on brokers that reject the default).
Now: live-tick price (ask/bid), broker-supported filling mode from
symbol_info, ORDER_BLOCKED_STOPS_LEVEL guard, typed journal events
(ORDER_ATTEMPTED/SENT/REJECTED/BLOCKED/ERROR with retcode + comment + exact
XAUUSDm request + quotes + symbol conditions + margin), terminal
decision=ORDER_REJECTED_BY_BROKER with request details (no more
"BLOCKED: all risk checks passed"), runtime report live-refreshed with the
profile. Strategy/lot/stop logic unchanged. Restart:
py -3.12 scripts\trading_service.py --profile demo_challenge --stdout-progress

Previously: DEMO-CHALLENGE-001: IMPLEMENTED — FINAL LAST-CHANCE aggressive XAUUSDm
momentum profile `--profile demo_challenge` (DEMO ONLY): fixed lots
0.05/0.10, tactical M1/M5 local stops, fresh entry scan every candle,
add-ons only into floating profit, max 3 open, owner-directed survival
envelope (3%/trade worst case, daily 5% pause, weekly 10% stop). The
institutional model is untouched and remains the default. User starts the
service on the Windows MT5 host:
py -3.12 scripts\trading_service.py --profile demo_challenge --stdout-progress

Previously: OPERATIONAL-INTELLIGENCE-001: IMPLEMENTED — warmstart context
report, adaptive exposure governor, DIRECTIONAL_CHOP_BREAKDOWN,
raw-confluence threshold display, growth_evaluation profile.

## Last Completed Task

P0-P11 roadmap, INT-001, RISK-001, LIVE-VERIFY-001, WINMT5-001,
WINMT5-LIVE-001, LIVE-001, LIVE-002, DEMO-001, AUDIT-001,
DEMO-002-BLOCKERS, DEMO-002, DEMO-EVAL completed (see 11_DECISION_LOG.md).
CONTINUOUS-001 (2026-06-10, decision 2026-06-10-06):
- ONE continuous MT5 trading service (scripts/trading_service.py +
  src/execution/trading_service.py): starts once, connects to the MT5
  account configured in .env (currently Exness DEMO -> demo orders), runs
  the DecisionPipeline continuously, executes approved trades through the
  SAME planner -> governor -> gateway stack (TradingService drives
  SupervisedDemoSession.run_cycle(); zero duplicated execution logic),
  reconciles positions and detects closes from MT5 history every cycle,
  manages break-even/trailing stops continuously.
- No fixed duration, no artificial order cap: risk policy governs (3
  trades/day, 2% daily pauses entries until UTC rollover [DAY_PAUSED], 5%
  weekly STOPS the service [RISK_SHUTDOWN]). Stops cleanly on kill switch,
  weekly-loss shutdown, Ctrl+C, or fatal error.
- Market-closed handling: MarketSchedule (weekend Fri 21:00 -> Sun 22:05
  UTC + daily break 21:00 -> 22:05 UTC) plus tick-staleness ground truth;
  prints MARKET CLOSED / FEED STALE, heartbeats to
  logs/service_heartbeat.jsonl, resumes automatically.
- Terminal observability: startup banner (masked login, account type
  verified non-real, server, symbol, mode, risk limits, news, kill switch,
  paths, stop instructions) + per-cycle progress (market state, bid/ask/
  spread, regime, HTF bias, decision + exact no-trade reason, confidence,
  positions with floating P&L, orders sent/simulated, trades today, daily
  P&L, risk/news/kill state, next poll). Sent orders print their MT5
  ticket + Toolbox/Trade-tab hint.
- Daily rollover writes service_eval_YYYYMMDD + service_reflection_YYYYMMDD
  (same evaluator as DEMO-EVAL); trading_service.md/.json written on stop.
- PROVEN DEFECT F-14 FIXED before any live order: the gateway built
  order_send requests with the canonical symbol ("XAUUSDM") — MT5 symbols
  are case-sensitive, the terminal would have rejected it. Requests now
  carry the exact broker case ("XAUUSDm"); verify_demo_account is shared in
  src/broker/mt5_data_adapter.py (REAL accounts refused).

INTELLIGENCE-001 (2026-06-10, decision 2026-06-10-07) — live-evidence audit
of 170+ no-trade CHOPPY cycles found and fixed the root causes:
- PROVEN: regime classified the whole 25h M5 window (flips>=2 => CHOPPY
  almost always) — now classifies the recent ~5h window; PROVEN: the
  hypothesis engine hard-blocked CHOPPY — now a graded gate (tradeable chop
  subtype + confluence >= 0.65 may pass; NEWS_RISK/NO_TRADE never).
- ChopClassifier subtypes: DANGEROUS_CHOP / LOW_QUALITY_CHOP (hard block);
  LIQUIDITY_CHOP_WITH_SWEEP / TRAP_REVERSAL_FROM_CHOP /
  BREAKOUT_EXPANSION_FROM_CHOP / CONTINUATION_AFTER_CHOP (candidates).
- MtfAlignmentEngine: D1/H4/H1/M15/M5 (H1+M15 honest M5 aggregations) ->
  alignment score + direction; can direct when the old D1+H4 combo is
  neutral; never upgrades the NO_TRADE data-safety state.
- ConfluenceEngine: graded scoring of sweep, BOS/CHOCH, FVG, order blocks,
  premium/discount, displacement, session, spread, orderflow proxy, MTF —
  with per-component statuses and explicit missing-evidence reporting.
- Second setup type: sweepless BOS-continuation (displacement >= 1.5x +
  confluence >= 0.60 + swing invalidation). Sweep-reclaim remains primary.
- AdaptiveRiskEngine replaces static 0.5%: capital phases ($2k->10k->15k->
  25k+), expansion only on strong evidence (max x1.65 of base), multiplicative
  contraction on losses/drawdown/uncertainty/spread/exposure, zero budget on
  unclear news or untradeable regime, HARD-CLAMPED to the 0.5% policy cap.
  Budget feeds both the pipeline sizer and the planner hard cap (tighten-only).
- Terminal now shows per cycle: MTF row, intel row (sweep/BOS/FVG/OB/PD/
  displacement/flow), confluence + risk tier/% + chop subtype + regime
  reason, and for NO_TRADE the exact missing evidence.
- Opportunity audit: after 60 active-session cycles without an entry, a
  classified report (NO_TRADE_CORRECT / POSSIBLY_TOO_STRICT / MIXED) is
  written to reports/runtime/opportunity_audit_*.md/json.

INTELLIGENCE-002 (2026-06-10, decision 2026-06-10-08):
- WIRING MATRIX (25_WIRING_MATRIX.md): all 20 intelligence layers audited
  with evidence — 17 LIVE; news PARTIAL (manual/static fail-closed,
  NEWS-001); futures/macro PLACEHOLDER (honest MacroProvider interface,
  NullMacroProvider cannot fabricate; FUTURES-001/MACRO-001).
- TRUE MTF: the live cycle fetches M15/H1/M1 from MT5 (M5/H4/D1 already
  real); pipeline prefers native candles, degrades honestly to labelled
  "aggregated(M5)"/"missing" (sources printed when degraded); explicit
  conflict string on mixed alignment; M1 trigger state is display-only.
- Asian range + London/NY expansion (src/data/session_levels.py): Asian
  high/low, price position, sweep of Asian liquidity, expansion ratio —
  a confluence component (asian_range) and a terminal line; UNKNOWN when
  the feed lacks today's Asian session (never fabricated).
- Dangerous-volatility classifier (src/regime/volatility_classifier.py):
  DANGEROUS_SPIKE / NEWS_LIKE_SHOCK / SPREAD_MISMATCH / UNSTABLE_STOPS
  hard-gate the pipeline before hypothesis; EXPANSION never blocks alone.
- ADAPTIVE DEMO RISK POLICY (03_RISK_POLICY updated, owner-directed): flat
  0.5% demo cap replaced by per-phase evidence-gated bounds — P1 base
  0.40% ceiling 1.00%, P2 0.35%/0.80%, P3 0.30%/0.60%, P4 0.20%/0.50%;
  expansion x1.4 strong / x2.0 elite; daily 2% / weekly 5% / 3 trades/day
  UNCHANGED; real-money policy UNCHANGED; no martingale structurally.
- Opportunity-audit verdicts extended: MISSED_SWEEP_REVERSAL,
  MISSED_CONTINUATION, DATA_INSUFFICIENT.
- BACKTEST-001 readiness: src/backtest/calibration.py +
  scripts/calibration_replay.py (threshold variants scored in R on real
  history; recommendation only — never mutates live config).

FINAL-INTELLIGENCE (2026-06-10, decision 2026-06-10-09):
- NEWS-001 architecture: NewsProvider abstraction; calendar windows carry
  impact (HIGH/MEDIUM; unknown=HIGH) + gold category; 5 states NEWS_CLEAR /
  NEWS_BLOCK / NEWS_UNKNOWN / NEWS_HIGH_IMPACT_SOON / NEWS_ACTIVE. HIGH
  active blocks; MEDIUM active / HIGH soon reduce risk (x0.5 contraction);
  UNKNOWN fail-closed; open positions always managed. Real feed pending.
- MACRO-001/FUTURES-001 interim: FileMacroProvider reads the stale-aware
  operator file configs/macro_context.json (as_of + max_age; stale/missing
  => UNAVAILABLE, never guessed); gold_pressure (DXY+yields) + futures bias
  feed confluence confirmation components (0.04 each); macro conflict
  contracts adaptive risk x0.75. Live feeds pending.
- M1 refinement LIVE: veto/delay-only after a qualified setup (strong
  opposing rejection -> skip this cycle); proven unable to create trades.
- Calibration upgraded: max drawdown (R), false positives, missed
  sweep-reversal/continuation decomposition, volatility blocks, per-segment
  expectancies, KEEP/TIGHTEN/LOOSEN/NEED_MORE_DATA verdict + recommended
  thresholds. Recommendation-only.
- Executable wiring verification: scripts/verify_wiring.py (real pipeline
  decision + class introspection) -> reports/runtime/wiring_verification.md:
  16 LIVE / 1 PARTIAL / 2 UNAVAILABLE_BY_CONFIG / 0 MISSING.
- Terminal/banner: news 5-state label, external macro=/futures= line, m1=
  line, phase= in risk line, banner shows providers + thresholds + capital
  phase.
- 692 tests passed at FINAL-INTELLIGENCE.

SIZING-001 (2026-06-10, decision 2026-06-10-10):
- PROVEN DEFECT FIXED (live evidence): a qualified candidate (confluence
  0.70, MTF 0.90, sweep/FVG/OB, displacement 1.8x) died with "invalid lot
  size 0.0" — the DEFENSIVE 0.20% budget ($4 on $2,000) was below the
  broker minimum-lot loss (~$5 at a ~5 stop).
- src/risk/lot_sizer.py: explicit resolver — raw lot from loss-at-stop
  math; below the broker minimum, min-lot viability against the PHASE
  CEILING: MIN_LOT_PROMOTED_TO_0.01 / MIN_LOT_RISK_TOO_HIGH /
  STOP_TOO_WIDE_FOR_ACCOUNT; never a vague 0.0. Lot size is never fixed:
  scales with equity, adaptive budget, and stop distance; milestone context
  ($2k -> $10k -> $15k -> $25k) in every decision.
- Pipeline: SIZING_BLOCKED stage with the verdict in the reason; planner
  order path applies the same promotion (bounded by ceiling AND policy).
- Self-audit fix: stale RiskLimits default 0.5% -> 1.0% (Adaptive Demo Risk
  Policy absolute ceiling; live profiles already used 1.0%).
- Threshold profiles: "current" (0.65/0.60/1.5x, DEFAULT) and
  "demo_exploration" (0.55/0.50/1.3x) via --thresholds; active profile +
  values printed in the banner. Default unchanged (calibration sample was
  small and negative-expectancy).
- Terminal: per-candidate sizing lines (risk %/$, stop, min-lot risk,
  raw/rounded/final lot, verdict, phase -> milestone).
- 709 tests passed at SIZING-001.

OPERATIONAL-INTELLIGENCE-001 (2026-06-10, decision 2026-06-10-11):
- DISPLAY DEFECT fixed: gate messages and terminal show confluence_raw at
  4 decimals + threshold + signed margin + would_pass(demo_exploration) —
  no more "0.65 < 0.65" confusion (comparison was always >=).
- CLASSIFIER BLINDNESS fixed: the chop classifier now receives the MTF
  directional score; strong external evidence (>=0.75) with displacement
  >=1.3x classifies DIRECTIONAL_CHOP_BREAKDOWN (tradeable candidate) instead
  of LOW_QUALITY_CHOP. Dangerous states still always win.
- Adaptive Exposure Governor (src/risk/exposure_governor.py; 03_RISK_POLICY
  Adaptive Exposure Policy): LOCKDOWN/BLOCKED/DEFENSIVE/NORMAL/AGGRESSIVE
  decide 0/0/1/3/6 entries per day, hard-bounded by the profile (growth: 6;
  others: 3); printed per cycle with the reason; entries-only (management
  continues); adverse conditions only shrink the allowance.
- Startup WARMSTART: full multi-timeframe history analysis printed at
  service start (candle counts per TF, HTF/MTF direction, regime + reason,
  Asian levels, PD, volatility, displacement, market phase, candidate +
  raw confluence, active thesis). Failure-tolerant.
- growth_evaluation profile: continuous milestone campaign ($2k->$10k->
  $15k->$25k), exposure-governor-driven, hard max 6 trades/day, no
  duration/order caps; daily 2%/weekly 5% anchors unchanged.
- Macro/futures UNAVAILABLE proven neutral by test (0.5 component, never
  "missing", never blocking).
- 726 tests pass; pre_demo_safety_check.sh passes.

DEMO-CHALLENGE-001 (2026-06-11, decision 2026-06-11-01):
- WHY (live evidence): 570+ cycles, direction read correctly, ZERO trades;
  dominant blocker STOP_TOO_WIDE_FOR_ACCOUNT repeated for hours from a
  stale HTF/structural stop while fresh M1/M5 local structure formed every
  candle. Owner directed ONE final aggressive demo attempt as a SEPARATE
  profile; nothing institutional was rewritten or deleted.
- NEW decision layer behind the SAME safety stack (session -> gateway ->
  journal/reconciliation/trailing): src/strategy/challenge_momentum.py
  (momentum read M15/M5/M1, breakout / pullback-rejection / continuation
  triggers, TACTICAL stop from current local swings/rejection/pullback +
  ATR/spread buffer, 8 USD hard ceiling — no local stop => skip with the
  exact reason, never a structural stop) and
  src/execution/challenge_planner.py (fixed lots 0.05 NORMAL / 0.10 STRONG
  parsed from the journaled setup_type; low liquidity demotes 0.10->0.05;
  survival-cap demotion then skip; 0.01 ONLY on margin refusal; add-ons
  same-direction only while EVERY open trade is in floating profit; blocked
  after a losing trade, against direction, or beyond 3 open; NEWS_UNKNOWN
  neutral — only an actual news RISK blocks).
- Owner-directed demo_challenge envelope (session_profiles carve-out,
  construction-locked to the ONE profile named demo_challenge): 3.0% worst
  case per trade, daily 5% pauses entries (DAY_PAUSED), weekly 10% stops
  the service, 10 trades/day, 3 open max, spread cap 1.0. Real-money policy
  untouched; every other profile still validates against the standard demo
  bounds.
- Terminal per cycle: profile=demo_challenge, fresh_entry_scan,
  new_candle_detected, local_structure_updated, momentum candidate/state,
  m15/m5 bias + displacement, entry_plan, tactical_stop
  price/distance/source, lot_decision, first_trade_profit_state,
  add_on_allowed, challenge_why.
- 753 tests pass (+27: profile/envelope, fixed lots, low-liquidity demote,
  tactical-stop-or-skip, macro/futures/news-unknown neutrality, add-on
  rules, max 3 open, no hedge/martingale, kill switch, exact XAUUSDm case,
  full-session end-to-end 0.10-lot order); pre_demo_safety_check.sh passes.

BROKER-EXECUTION-001 (2026-06-11, decision 2026-06-11-02):
- Live evidence: demo_challenge found valid entries; the broker rejected
  every order; nothing was persisted; the terminal printed the
  contradictory "decision=BLOCKED reason: all risk checks passed".
- PROVEN root causes in the gateway request builder (symbol case was NOT
  the cause — the request already carried XAUUSDm per F-14; the journal's
  XAUUSDM is the canonical comparison form, never sent to the broker):
  (B1) price = analysed candle close (stale beyond deviation=20 the moment
  momentum fires) -> now the LIVE tick ask/bid with entry_price fallback;
  (B2) no type_filling -> now selected from symbol_info.filling_mode
  (IOC > FOK > RETURN; omitted only when symbol_info is unavailable).
- Diagnostics: every send attempt journals typed events ORDER_ATTEMPTED /
  ORDER_SENT / ORDER_REJECTED / ORDER_BLOCKED / ORDER_ERROR with retcode +
  retcode name + broker comment + exact request (XAUUSDm case, volume,
  type, price, sl, tp, deviation, type_filling) + live bid/ask + symbol
  conditions (trade_mode, volume min/max/step, stops/freeze level, filling
  mask) + margin check. Searchable:
  Select-String -Path logs\demo_trade_journal.jsonl
  -Pattern "ORDER_REJECTED","retcode","broker"
- ORDER_BLOCKED_STOPS_LEVEL: SL/TP inside the broker minimum stop distance
  block BEFORE sending (never silently widened; risk math unchanged).
- Terminal: decision=ORDER_REJECTED_BY_BROKER + reason=retcode/comment +
  request_symbol/volume/price/sl/tp + symbol conditions + broker quote.
- Runtime report: trading_service.json/.md carry the profile and refresh at
  startup (RUNNING) and after every SENT/SIMULATED/REJECTED/ORDER_ERROR.
- Strategy, lot rules, and tactical-stop rules UNCHANGED.
- 769 tests pass (+15 in tests/test_broker_execution.py: live-price
  request, filling-mode selection, degradation without symbol_info, full
  rejection diagnostics, exception diagnosis, stops-level block + pass,
  journal event roundtrip, session-level rejected/sent/error events,
  honest terminal wording); pre_demo_safety_check.sh passes.

## Next Task

User starts the SMC execution run on the Windows MT5 host (PowerShell):
1. Stop the running service if any: New-Item -ItemType File control\KILL_SWITCH
   then Remove-Item control\KILL_SWITCH once stopped.
2. Optional rehearsal (identical loop, nothing sent):
   py -3.12 scripts\trading_service.py --profile smc_challenge --dry-run --stdout-progress
3. Live demo run:
   py -3.12 scripts\trading_service.py --profile smc_challenge --stdout-progress
4. Watch per cycle: mt5_balance/equity/realized_daily_pnl/floating_pnl +
   accounting_verified, htf_context, killzone, liquidity_context,
   smc_anchor, entry_trigger, tactical_stop + stop_logic +
   risk_if_sl_hit, lot_decision 0.05/0.10, reentry_plan/waiting_for on
   every NO_TRADE, first_trade_profit_state/add_on_allowed.
5. Verify every CLOSE_DETECTED line against the MT5 history tab: outcome
   and net_pnl must match the broker exactly (source=MT5_HISTORY).
6. Stop any time: New-Item -ItemType File control\KILL_SWITCH

Institutional evidence collection (unchanged, optional):
1. py -3.12 scripts\trading_service.py --profile continuous --stdout-progress
   (or --profile growth_evaluation; --dry-run first to watch reasoning)
2. Collect evidence over full London+NY sessions:
   - MTF row shows all six frames + sources (no "degraded" lines expected on
     the Windows host), vol=/asian= lines, conflict lines when mixed,
   - adaptive risk lines show phase-based budgets (0.10%-0.80% typical),
   - any ORDER SENT tickets vs MT5 Toolbox/Trade tab,
   - opportunity_audit_* verdicts on no-trade stretches,
   - daily service_eval_* / service_reflection_* reports.
3. Run the calibration replay on real history (Windows):
   py -3.12 scripts\calibration_replay.py --fetch --count 4000
   Review reports/runtime/calibration.md; threshold changes only via a
   reviewed task with walk-forward (BACKTEST-001).
4. Honest backlog: NEWS-001 (real calendar), MACRO-001 (DXY/yields),
   FUTURES-001 (gold futures feed).

## Current Execution Mode

CONTINUOUS_SERVICE_READY (gated by .env flags + fresh preflight + kill
switch; user-started only)

## Real Trading

FORBIDDEN (REAL accounts refused at start; real flags abort the gateway)

## Demo Trading

ALLOWED via scripts/trading_service.py (continuous, MAIN mode) or
scripts/demo_session_run.py (bounded sessions) — both require a fresh READY
preflight, the .env execution flags for sending, an available news source,
and an absent kill switch.

## Paper / Shadow Trading

ALLOWED: scripts/live_shadow_run.py (journals only, never sends)

## Environment Status

- .env.example exists; .env is local only and ignored by git.
- The service trades the account configured in .env (currently Exness
  DEMO); credentials are never printed (login masked in the banner).
- WSL cannot import MetaTrader5; the service runs on the Windows MT5 host
  (off-Windows it reports an honest ENVIRONMENT_ISSUE, exit 2).
- Post-session report scripts run anywhere (offline file readers).

## Safety Notes

- Do not commit .env. Do not print credentials.
- Do not enable real trading (REAL_TRADING_ENABLED / ALLOW_REAL_ORDERS).
- ExecutionGateway remains the only order pathway; RiskGovernor final
  authority; profiles can only tighten 03_RISK_POLICY.
- Claude never starts the service; the user does.
