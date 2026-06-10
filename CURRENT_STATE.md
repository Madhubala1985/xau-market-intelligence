# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 12: Live Demo Readiness — continuous service operational

## Current Task

SIZING-001: IMPLEMENTED — the "invalid lot size 0.0" Proven Defect is fixed
with milestone-aware adaptive lot sizing (min-lot promotion bounded by the
phase ceiling, full sizing diagnostics, threshold profiles). Restart the
continuous service and collect evidence (user-started)

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
- 709 tests pass; pre_demo_safety_check.sh passes.

## Next Task

User restarts the continuous service on the Windows MT5 host (PowerShell):
1. Stop the running service if any: New-Item -ItemType File control\KILL_SWITCH
   then Remove-Item control\KILL_SWITCH once stopped.
2. py -3.12 scripts\trading_service.py --profile continuous --stdout-progress
   (or --dry-run first to watch the new reasoning without orders)
3. Collect evidence over full London+NY sessions:
   - MTF row shows all six frames + sources (no "degraded" lines expected on
     the Windows host), vol=/asian= lines, conflict lines when mixed,
   - adaptive risk lines show phase-based budgets (0.10%-0.80% typical),
   - any ORDER SENT tickets vs MT5 Toolbox/Trade tab,
   - opportunity_audit_* verdicts on no-trade stretches,
   - daily service_eval_* / service_reflection_* reports.
4. Run the calibration replay on real history (Windows):
   py -3.12 scripts\calibration_replay.py --fetch --count 4000
   Review reports/runtime/calibration.md; threshold changes only via a
   reviewed task with walk-forward (BACKTEST-001).
5. Honest backlog: NEWS-001 (real calendar), MACRO-001 (DXY/yields),
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
