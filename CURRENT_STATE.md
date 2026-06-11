# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 12: Live Demo Readiness — continuous service operational

## Current Task

SMC-EXECUTION-002: IMPLEMENTED — live-evidence fix from the first
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
