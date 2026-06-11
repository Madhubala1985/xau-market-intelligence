# 24_INTELLIGENCE_AUDIT_ROADMAP.md

## Purpose

Intelligence-level audit of the XAU/USD Adaptive Liquidity Intelligence System
against the ultimate mission: an institutional-grade, patience-first,
risk-governed, evidence-gated autonomous trading brain growing a small account
through survival-first compounding — never by weakening risk.

Audit date: 2026-06-10. Audited at commits up to DEMO-001.
Classifications: Proven Defect / High-Confidence Defect / Hypothesis /
Observation / Market Artifact / Design Improvement.

---

# 1. What Is Already Strong

- **Safety architecture is genuinely layered.** Order sending requires ALL of:
  demo env flags, Risk Governor approval, ExecutionGateway checks (symbol,
  stop-loss, take-profit, broker state, duplicates), kill switch disengaged,
  and `demo_send_enabled`. Defaults send nothing. Real-trading requests are
  refused outright (REAL_FORBIDDEN). Shadow mode refuses sending-enabled
  gateways and aborts if anything ever reports sent=True.
- **No retail failure modes found.** Audited for martingale, grid, averaging
  down, forced entries, fixed-lot risk bypass, leverage-driven sizing: none
  exist. Adding to losers is structurally blocked (PyramidingGuard) and there
  is no code path that increases size after losses.
- **Patience-first is real.** The pipeline produces WAIT/NO_TRADE by default;
  an actionable decision requires HTF bias + tradeable regime + a confirmed
  aligned sweep-reclaim + thesis + invalidation (schema-enforced: no thesis or
  no invalidation cannot even construct an actionable TradeDecision).
- **Data honesty.** Live validation was never faked (WSL runs report
  ENVIRONMENT_ISSUE); stale live feeds become journaled NO_TRADE; candle
  validation rejects bad OHLC, duplicates, non-monotonic series.
- **Broker specifics proven live.** XAUUSDm (exact case preserved end-to-end),
  contract_size=100, digits=3, point=0.001, volume_min/step=0.01 — verified
  against the real Exness demo terminal (WINMT5-LIVE-001 PASS).
- **Evidence discipline.** 463 tests; evidence pack generator refuses
  unclassified modules; pre-demo safety check guards .env and real-trading
  enablement; every decision (including no-trades) is journaled restart-safe.

---

# 2. Findings

## 2.1 Fixed in this audit cycle

### F-1. Risk-limit enforcement inputs were permanently zero in the live loop
- **Class:** High-Confidence Defect (FIXED)
- **Root cause:** RiskGovernor checks daily/weekly loss, trades/day, and
  consecutive losses from RiskContext inputs — but nothing computed them.
  LiveShadowSession passed PipelineInput defaults (all zeros), so 03_RISK_POLICY
  shutdown rules (daily 2%, weekly 5%, streak limits) could never trigger in a
  live or demo session.
- **Impact:** In DEMO-002 the account could keep trading straight through its
  loss limits. In shadow mode, journaled "approved" decisions overstate what a
  policy-compliant system would approve.
- **Fix:** `src/risk/state_tracker.py` (RiskStateTracker) derives
  daily_loss_pct, weekly_loss_pct, trades_today, consecutive_losses, and
  open_symbols from journaled TradeRecords; LiveShadowSession now feeds these
  into every PipelineInput.
- **Safety risk of fix:** None — read-only over the journal; tighter, not looser.
- **Tests:** tests/test_risk_state_tracker.py (9) + wiring test in
  tests/test_live_shadow.py.

### F-2. Execution-quality scoring used a points spread scale on price-unit data
- **Class:** High-Confidence Defect (FIXED)
- **Root cause:** `_score_components` hard-coded `1 - spread/50.0` (points
  scale). The live loop feeds spread in price units (~0.15–0.30 USD), so
  execution quality was a constant ~0.996 — spread could never degrade
  confidence in live, only the governor's hard max could act.
- **Impact:** Confidence/uncertainty scoring ignored a gold-critical input
  (spread widening at rollover/news is exactly when entries should be doubted).
- **Fix:** DecisionPipeline takes `max_spread` (default 50.0 keeps backtest
  behavior); `make_live_pipeline` passes its price-unit max (1.0 USD), making
  scoring and governor consistent.
- **Tests:** price-unit scale test + non-positive guard in test_live_shadow.py.

### Previously fixed this phase (for the record)
- Case-sensitive broker symbols destroyed by `.upper()` — Proven Defect, fixed
  (WINMT5-001), proven live.
- Default validator/governor configs rejected all live data (session gaps ->
  MISSING_CANDLES; expected_symbol XAUUSD vs XAUUSDM) — High-Confidence Defect,
  fixed (LIVE-001, `make_live_pipeline`).
- `.gitignore` negation un-ignored all runtime journals — Proven Defect, fixed
  (DEMO-001).

## 2.2 DEMO-002 blockers — status update 2026-06-10 (second pass)

Windows proof received: live_shadow_run (5 cycles) COMPLETED, live_shadow_session
(5 min) COMPLETED, demo_preflight Ready: True. F-3/F-4/F-5 below are now
IMPLEMENTED (commit DEMO-002-BLOCKERS); what remains before order_send is the
supervised demo session loop itself (DEMO-002) plus the operator steps listed
in the gate map.

- **F-3 RESOLVED:** DemoTradePlanner wires ConfidenceResult -> tier ->
  LeverageAwareSizer (tier cap TIGHTENED by the governor per-trade budget;
  margin can only block) -> PyramidingGuard (one base position + at most one
  protected add-on) -> RiskGovernor (final authority; protected_addon flag in
  RiskContext is the only — explicit, guard-gated — path past the duplicate
  check). Policy contradiction 03-vs-20 resolved tightest-rule-wins; see
  decision log 2026-06-10-03.
- **F-4 RESOLVED (proposal layer):** MT5DataAdapter.fetch_positions (read-only);
  PositionReconciler (ticket/attribute matching; ANY orphan -> planner blocks,
  fail closed); PositionProtectionManager (BE/trailing STOP PROPOSALS via
  TrailingStopEngine; never widens; flags missing stop-loss as a violation;
  uses the journaled original stop for R math). Applying proposals to MT5 is
  DEMO-002's gateway-gated job.
- **F-5 RESOLVED (fail-closed):** NewsRiskGuard — manual block file
  (control/NEWS_BLOCK) + optional static calendar (configs/news_windows.json).
  No source -> state UNKNOWN -> DemoTradePlanner blocks. Malformed calendar
  reads as unknown, never as "no news". No fake calendar feed is pretended.

### F-3. RISK-001 sizing/pyramiding engines are not wired into any decision path (original finding)
- **Class:** High-Confidence Defect (integration gap)
- **Evidence:** `LeverageAwareSizer` and `PyramidingGuard` are implemented and
  tested but referenced nowhere outside their own modules. The pipeline sizes
  with the simpler PositionSizer (balance x risk%; no margin feasibility, no
  demo confidence tiers, no add-on protection).
- **Impact:** DEMO-002 would trade without margin-feasibility checks and
  without enforcement of protected-pyramiding rules at runtime. (Shadow mode is
  unaffected: nothing is sent.)
- **Required fix (DEMO-002 scope):** a DemoExecutionSession that, per signal:
  confidence tier <- ConfidenceResult; LeverageAwareSizer for lot + margin
  check; PyramidingGuard for any add-on; THEN governor + gateway. Tests must
  cover 0.01/0.05/0.10 lots, margin-block, add-on block on unprotected trades.

### F-4. No open-trade management loop
- **Class:** High-Confidence Defect (missing component for DEMO-002)
- **Evidence:** StopPlacementEngine runs at entry; TrailingEngine
  (structure/volatility trailing, partials) is implemented + tested but
  unwired; no module reconciles MT5 open positions against the journal
  (orphan-position detection); no break-even protection driver.
- **Impact:** DEMO-002 could open a position and then nothing manages it.
  Pyramiding protection depends on stops being trailed to BE — currently
  nothing trails them.
- **Required fix:** position manager in the supervised demo loop: read open
  positions read-only, drive TrailingEngine, modify stops via gateway-gated
  calls only, flag orphans, journal every change.

### F-5. News/volatility protection is unfed
- **Class:** High-Confidence Defect (dead input)
- **Evidence:** `PipelineInput.news_risk` exists and Regime.NEWS_RISK blocks
  hypotheses — but the live loop always passes news_risk=False. No calendar
  source exists. 14_SESSION_KILLZONE_POLICY mandates blocking major news
  windows "unless news module is validated".
- **Impact:** Gold's most violent moves (CPI/NFP/FOMC) would be traded as
  normal regimes in DEMO-002.
- **Required fix:** minimal validated news-window module (static weekly
  calendar file is acceptable initially: UTC windows -> news_risk=True), wired
  into the live loop; tests for window edges. Until then DEMO-002 must be
  supervised-only with the operator as the news filter (runbook rule).

## 2.3 Open: design improvements (validation-gated, not blockers)

### F-6. Implemented intelligence not yet in the decision flow
- **Class:** Design Improvement
- FVG/order-block/supply-demand zones (P3-004) and premium/discount (P3-005)
  engines exist + are tested but do not contribute to setup confluence or
  scoring. The only setup family is HTF-aligned sweep-reclaim.
- 1H/15M timeframes are unused in the live config (D1/H4 bias + M5 exec);
  the aggregation engine supports them.
- Confidence tiers (NORMAL/HIGH_CONFLUENCE/ELITE) are never derived from
  ConfidenceResult — needed by F-3 anyway.
- **Path:** extend `_find_setup`/scoring behind a config flag; prove on
  backtest + walk-forward (P10) BEFORE enabling in shadow; never change live
  behavior without replay evidence (04_ADAPTATION_POLICY).

### F-7. Reflection loop is not closed
- **Class:** Design Improvement
- Reflection/mistake-classification engines exist but no runtime hook produces
  post-session reviews from the live journal, and nothing tracks missed
  opportunities or false-positive rates per setup type.
- **Path:** after LIVE-002 sessions, generate reflection report from the
  journal; add no-trade quality review (were rejections correct in hindsight?).
  Parameter-change proposals remain manual + replay-validated.

### F-8. AMD (accumulation/manipulation/distribution) phase model absent
- **Class:** Hypothesis
- Trap detection currently equals false-sweep classification. A session-phase
  model (Asian range -> London manipulation -> NY distribution) could improve
  entry timing. Unproven for this dataset; requires backtest evidence first.

## 2.4 Observations (no action required now)

- Hypothesis decision_id is symbol+epoch-seconds: collision-safe at poll
  cadence; would need a sequence suffix if cycles ever run sub-second.
- Governor max_open_trades=1 + duplicate checks make duplicated orders
  structurally hard; DEMO-002 must still pass open_symbols from the tracker
  (now available) into its context builder.
- Session scoring (0.0 outside kill zones/Asian) reduces-not-blocks off-hours
  trades; 14_SESSION policy says "reduce or block" — compliant, and the
  governor's spread gate independently bites at rollover. Watch in shadow.
- `Candle.symbol` canonicalizes to uppercase by design; only MT5 API calls
  need exact case (enforced + tested at the adapter boundary).
- Demo risk_pct default 0.005 with $2,000 -> $10 risk/trade; tighter than the
  $40 demo tier cap. Conservative-by-default is correct; tiers arrive with F-3.

---

# 3. Gate Map

## Before demo trading (DEMO-002) — all REQUIRED
1. LIVE-002 supervised shadow session evidence on the Windows MT5 host
   (COMPLETED outcome, orders_sent=0, clean decision log).
2. DEMO-001 preflight PASS on the Windows MT5 host (all 12 gates).
3. F-3 wired: LeverageAwareSizer + PyramidingGuard in the execution path.
4. F-4 wired: position manager + orphan reconciliation + BE protection.
5. F-5 mitigated: news module validated OR explicit operator-as-news-filter
   runbook rule acknowledged for supervised sessions.
6. Kill switch verified at session start (runbook step).
7. User manually starts supervised demo mode. Claude never starts it.

## Before real money — all REQUIRED (in addition)
- Sustained multi-week demo evidence: risk limits never breached, no orphan
  positions, no duplicated orders, journal/state intact across restarts.
- Walk-forward validation on unseen periods (P10-002) for any strategy change
  made since the last validation.
- Reflection reports demonstrating mistake classification works on real
  decisions (F-7 closed).
- News protection validated (F-5 closed properly, not runbook-mitigated).
- Real-mode limits verified active: risk 0.25%/trade, daily 0.5%, weekly 1.5%,
  2-loss shutdown (03_RISK_POLICY) — and manual approval per CLAUDE.md.

# 4. Next Highest-Impact Task

## Status update — DEMO-002 session loop implemented

SupervisedDemoSession + scripts/demo_session_run.py complete (529 tests).
Additional integration defects found and fixed during implementation:
- gateway duplicate pre-check ignored protected_addon (add-ons could never
  execute) — fixed, governor still re-checks independently;
- append-only journal poisoned open_symbols after the first close (permanent
  block) — fixed with latest-per-record_id collapse semantics;
- no close detection (stopped-out positions deadlocked reconciliation and
  losses never reached the loss tracker) — fixed via deal-history P&L close
  records; unknown P&L stays OPEN and fails closed;
- order volume could leave the broker lot grid under a size_factor — fixed
  (snap down); sizing reduction now applied exactly once.

**Next: user produces first supervised demo evidence (Windows PowerShell):**
1. `python scripts/demo_preflight.py` (13 gates; needs configs/news_windows.json)
2. `python scripts/demo_session_run.py --dry-run --duration-minutes 10`
3. `python scripts/demo_session_run.py --confirm "START SUPERVISED DEMO" --duration-minutes 60 --max-orders 1`

**Implementation after evidence:** reflection report from the demo journal
(F-7), partial take-profits, richer close classification, multi-session
aggregation — all validation-gated.

# 5. Audit Method Note

This audit reviewed: pipeline, hypothesis, scoring, governor, position sizing,
leverage sizing, pyramiding, gateway, shadow, live shadow, preflight, kill
switch, journal, validator, settings/adapter/connectivity, and policies 03/13/
14/20-23, plus integration greps for unwired modules and forbidden patterns
(martingale/grid/averaging/fixed-lot bypass: none found). Engine-internal
correctness (structure/liquidity/sweep math) was accepted on the strength of
existing unit tests; replay validation on real XAUUSDm data (LIVE-002 +
backtest replay) is the designated proving ground for those.

---

# 6. DEMO-EVAL audit — 2026-06-10 (third pass)

Scope: turn DEMO-002 from a one-order toy test into a serious demo evaluation
engine without weakening risk; audit the gold-movement intelligence honestly.

## 6.1 Fixed in this pass

### F-8. The one-order cap was wired as the system's design center
- **Class:** Design defect (FIXED)
- **Evidence:** SupervisedDemoSession defaulted max_orders=1 and the runner
  hardcoded RiskLimits; no configuration layer existed.
- **Fix:** policy-bounded session profiles (smoke/evaluation/london/newyork/
  full_day); max_orders=None (policy-governed) is the serious default; the
  artificial cap survives only in the smoke profile. Profiles can tighten
  03_RISK_POLICY, never loosen it (construction-time validation + tests).

### F-9. Dry-run never rehearsed the entry path it claimed to validate
- **Class:** High-Confidence Defect (FIXED)
- **Evidence:** the runner forced max_orders=0 for --dry-run, so every cycle
  hit the session cap BEFORE the planner; sizing/pyramiding/governor/gateway
  logic was never exercised in rehearsal.
- **Fix:** dry-run keeps the profile limits; approved plans flow planner ->
  gateway, surface as ORDER_SIMULATED / orders_simulated, count against the
  cap like real sends, and (flags disabled) can never reach order_send.

### F-10. No post-session intelligence existed
- **Class:** Design gap (FIXED)
- **Fix:** CycleStats per cycle; SessionEvaluator + reflection builder
  (src/reflection/demo_evaluation.py); scripts demo_eval_report.py and
  demo_reflection.py. Findings use the standard classifications; untaken
  trades are HYPOTHESIS (no hindsight), routed to backtest-first. Offline
  only — no live self-mutation (04_ADAPTATION_POLICY).

## 6.2 Gold-movement intelligence factor map (honest status)

| Factor | Status | Where |
|---|---|---|
| XAU volatility | WIRED (regime classes + ATR in stops/trailing); no dedicated tradable-vs-dangerous volatility classifier beyond regime+spread | regime_engine, stop_placement, trailing |
| Spread | WIRED (governor price-unit max + execution-quality scoring, F-2) | governor, pipeline |
| Session behavior | WIRED (Asian/London/NY/overlap classification, kill-zone scoring) | sessions, pipeline |
| London/NY activity | WIRED (kill-zone confidence) + new london/newyork profiles | session_profiles |
| Liquidity sweeps | WIRED — the core setup driver (confirmed aligned sweep-reclaim) | sweep, pipeline |
| BOS/CHOCH | WIRED (structure bias feeds scoring) | market_structure |
| FVG / order blocks / premium-discount | **NOT WIRED** — implemented + tested (zones.py, premium_discount.py) but absent from DecisionPipeline | see F-11 |
| HTF bias | WIRED (daily/H4) | htf_bias |
| Regime | WIRED | regime_engine |
| News / macro risk | WIRED fail-closed; sources are manual block + static calendar only (no live feed — honest, F-5) | news_guard |
| Stop placement | WIRED (beyond invalidation, ATR + liquidity buffer) | stop_placement |
| Trailing / break-even | WIRED (proposals -> gateway.modify_stop, never widens) | position_manager, gateway |
| Risk state | WIRED (journal-driven daily/weekly loss, streaks, F-1) | state_tracker |
| Futures confirmation | Engine wired but EFFECTIVELY INACTIVE live: no futures feed exists, PipelineInput.futures_candles is always None (degrades gracefully by design) | see F-12 |

## 6.3 Open findings (recorded, not silently implemented)

### F-11. Zone/premium-discount intelligence is not in the live decision path
- **Class:** Design Improvement (backtest before changing)
- **Evidence:** src/structure/zones.py and premium_discount.py are referenced
  nowhere outside their tests; setups rely on sweep-reclaim + HTF bias only.
- **Why not fixed now:** wiring them changes live trade selection; the
  adaptation policy requires backtest evidence before strategy changes. The
  standing finding is emitted into every evaluation report so it cannot be
  forgotten.

### F-12. Futures confirmation has no live data source
- **Class:** Observation
- **Impact:** confidence never gets the futures boost/contradiction signal in
  live sessions; engine degrades to neutral as designed. Needs a data source
  decision before it can matter.

### F-13. No dedicated dangerous-volatility classifier
- **Class:** Hypothesis (backtest before changing)
- **Evidence:** 03_RISK_POLICY distinguishes tradable vs dangerous
  volatility; today this emerges implicitly from regime (CHOPPY/NEWS_RISK
  score 0) + spread gates + stop-distance sizing limits, not from an explicit
  classifier (erratic candles, feed instability, irrational stop distance).
- **Next:** evaluate on collected demo sessions whether the implicit gates
  block dangerous windows adequately before adding a classifier.

# 7. Updated gate map — before real money (unchanged in substance)

All previous real-money gates stand (multi-week demo evidence, walk-forward
validation, validated news protection, real-mode limits 0.25%/0.5%/1.5% with
2-loss shutdown, manual approval). DEMO-EVAL adds the evidence machinery:
serious policy-governed sessions + evaluation/reflection reports are now the
required artifacts for "sustained demo evidence".

---

# 8. CONTINUOUS-001 audit notes — 2026-06-10 (fourth pass)

## F-14. Order requests carried the canonical symbol, not the broker case
- **Class:** Proven Defect (FIXED — found by the new service tests, BEFORE
  any live order was attempted)
- **Evidence:** ExecutionGateway._build_request used decision.symbol
  (canonical "XAUUSDM"). MT5 symbols are case-sensitive; Exness lists
  "XAUUSDm", so the very first real demo order would have been rejected by
  the terminal (and the fake-broker test that asserted the canonical case
  encoded the defect as expected behavior).
- **Fix:** the gateway takes broker_symbol (exact case) for order requests;
  all checks still compare canonical forms; both runners pass
  settings.symbol. modify_stop already used the position's exact case.
- **Lesson recorded:** every value sent TO the terminal must use the exact
  broker case; canonical forms are for internal comparison only.

## Service-level status
- The system's MAIN mode is now the continuous service
  (scripts/trading_service.py): no fixed duration, no artificial order cap,
  market-closed pausing with heartbeats, daily evaluation/reflection
  rollover, weekly-loss shutdown, kill-switch + Ctrl+C clean stops, full
  terminal observability with masked account data.
- One execution stack confirmed: the service drives
  SupervisedDemoSession.run_cycle(); there is no demo-only or live-only
  duplicate path. Real mode remains refused (flags + account verification);
  the future transition is configuration + readiness gates, not a rewrite.
- F-11 (zones/premium-discount unwired), F-12 (no futures feed), F-13 (no
  dedicated dangerous-volatility classifier) remain open and backtest-gated.

---

# 9. INTELLIGENCE-001 audit — 2026-06-10 (fifth pass)

Trigger: 170+ continuous live cycles, zero trades, every cycle
"regime=CHOPPY ... decision=NO_TRADE", while the 5M chart showed a clean
bearish expansion through London/NY.

## 9.1 Answers to the critical audit questions

- Was regime classification correct? NO — Proven Defect: flips counted over
  the whole 25h window (choppy_flips=2) made CHOPPY near-permanent. Regime
  now classifies the recent ~5h window.
- Was CHOPPY too dominant? YES — and it was also a blind hard block in the
  hypothesis engine (Proven Defect, fixed with the graded gate).
- Wrong timeframe? Partially — regime used the full M5 history; H1/M15 did
  not exist at all in the live path (now honest aggregations of M5).
- Ignoring London/NY expansion / bearish HTF / directional 5M movement /
  sweep+continuation / MTF? YES on all counts: there was no MTF engine, no
  continuation setup, no displacement input, and CHOPPY blocked before any
  of it could matter. All wired now.
- Were conf=0.66/unc=0.67 meaningful? Barely — stuck because the regime
  component pinned at 0 and disagreement saturated the uncertainty formula.
  Inputs now vary with graded regime/confluence.
- Should CHOPPY be decomposed? DONE: 6 subtypes; 2 hard-block, 4 candidate.

## 9.2 Gold-intelligence wiring status after this pass

WIRED INTO THE LIVE PATH: sweeps, buy/sell-side liquidity, BOS, CHOCH, FVG,
order blocks, supply/demand, premium/discount, displacement, session
behavior (kill zones + per-cycle session), volatility regime + chop
subtypes, spread regime, tick-volume/orderflow PROXY (clearly labelled,
never a signal), MTF alignment D1/H4/H1/M15/M5, structural invalidation,
stop placement, BE/trailing, journal-driven risk state, adaptive risk.

PARTIAL / RECORDED, NOT FAKED:
- F-12 futures confirmation: still no live feed (engine degrades neutral).
- News/macro: manual block + static calendar only; terminal shows
  CLEAR/BLOCKED/UNKNOWN. Future task NEWS-001: real macro feed (CPI, NFP,
  FOMC, DXY, yields) — must not be faked until a real source exists.
- Asian-range-specific logic: session highs/lows flow through the liquidity
  map; an explicit Asian-range model is a Design Improvement (backtest).
- 1M execution refinement: not implemented (M5 remains the exec frame).
- Thresholds (chop override 0.65, continuation 0.60, displacement 1.5x)
  are reasoned defaults — Hypothesis until backtest-calibrated (BACKTEST-001
  candidate).

## 9.3 Risk redesign status

Static 0.5% risk removed as the brain: AdaptiveRiskEngine decides from
evidence + account state, capital-phase aware, hard-clamped to the policy
cap; contraction-only on adverse signals (no martingale structurally).
03_RISK_POLICY remains the ceiling and the authority; raising the cap
requires validated multi-week evidence and a manual policy change.

---

# 10. INTELLIGENCE-002 — 2026-06-10 (sixth pass)

Full wiring verification: see 25_WIRING_MATRIX.md (the per-layer matrix with
evidence is now a tracked doc). Summary: 17/20 layers LIVE; news PARTIAL
(manual/static, fail-closed, NEWS-001 pending); futures + macro PLACEHOLDER
(honest interface via MacroProvider/NullMacroProvider; FUTURES-001/MACRO-001
pending). Fixed this pass: TRUE MT5 M15/H1/M1 fetching with labelled
degradation (the H1/M15-from-M5 aggregation shortcut of INTELLIGENCE-001 is
now only the fallback), Asian range + London/NY expansion wired into
confluence, an explicit dangerous-volatility classifier hard-gating the
pipeline, the Adaptive Demo Risk Policy (per-phase ceilings replacing the
flat 0.5% demo cap; daily/weekly anchors unchanged), extended opportunity-
audit verdicts, and the BACKTEST-001 calibration replay tool.

Open (honest backlog): NEWS-001 real calendar feed; MACRO-001 DXY/yields;
FUTURES-001 gold futures stream; BACKTEST-001 actual data run + walk-forward
(tooling ready); M1 stays display-only until calibrated; F-11's deeper
zone-entry logic (zones currently gate confluence, not entries) remains a
Design Improvement.

---

# 11. FINAL-INTELLIGENCE — 2026-06-10 (seventh pass)

All previously-partial layers finished or honestly finalized:
- News: provider architecture, impact/category calendar, 5 graded states;
  HIGH blocks, MEDIUM/soon reduce; UNKNOWN fail-closed. NEWS-001 (real HTTP
  feed) remains the only open piece.
- Macro/futures: stale-aware operator file (configs/macro_context.json) via
  FileMacroProvider; gold-pressure confirmation in confluence + adaptive
  contraction on conflict. MACRO-001/FUTURES-001 (live feeds) remain open.
- M1: live as a veto/delay refinement layer; cannot create trades (tested).
- Calibration: drawdown/false-positive/missed-decomposition/segments +
  KEEP/TIGHTEN/LOOSEN/NEED_MORE_DATA verdicts; awaiting the real-history run.
- Executable wiring verification (scripts/verify_wiring.py): 16 LIVE /
  1 PARTIAL / 2 UNAVAILABLE_BY_CONFIG / 0 MISSING.

The system is feature-complete for the demo evaluation campaign; remaining
work is external-feed integration (NEWS-001/MACRO-001/FUTURES-001), the
BACKTEST-001 data run, and evidence collection toward the real-money gates.

---

# 12. SIZING-001 — 2026-06-10 (eighth pass)

## F-15. Adaptive budget below the broker minimum lot died as "invalid lot size 0.0"
- **Class:** Proven Defect (FIXED — caught by live evidence on the first
  qualified candidate)
- **Evidence:** confluence 0.70 / MTF 0.90 / TRUE_SWEEP / FVG / OB /
  displacement 1.8x produced DEFENSIVE 0.20% = $4 on $2,000; min-lot loss at
  the ~5 stop was ~$5; sizers blocked; governor reported a vague invalid lot.
- **Fix:** milestone-aware lot resolver (src/risk/lot_sizer.py) with explicit
  verdicts (SIZED / MIN_LOT_PROMOTED_TO_0.01 / MIN_LOT_RISK_TOO_HIGH /
  STOP_TOO_WIDE_FOR_ACCOUNT) bounded by the phase ceiling; the same
  promotion in the DemoTradePlanner order path; full terminal/journal
  diagnostics. Also fixed the stale RiskLimits default (0.5% -> 1.0% per the
  Adaptive Demo Risk Policy).
- **Lesson:** every sizing refusal must state its dollar math; a 0.0 volume
  may only exist together with an explicit verdict.

Threshold profiles added ("current" default, "demo_exploration" optional via
--thresholds; active profile printed at startup). The calibration replay's
looser recommendation had negative expectancy on a small sample — default
unchanged until real-history evidence justifies otherwise.

---

# 13. OPERATIONAL-INTELLIGENCE-001 — 2026-06-10 (ninth pass)

Live evidence (all-bearish MTF 1.00, FVG/OB aligned, disp 1.5-1.7x, still
NO_TRADE) audited; fixed: (R1) misleading 2-decimal threshold display (raw
4-decimal + signed margin + would-pass-alt everywhere); (R2) chop classifier
blindness to external MTF evidence -> DIRECTIONAL_CHOP_BREAKDOWN subtype;
(R3) static 3/day exposure -> AdaptiveExposureGovernor with policy-bounded
states (0/0/1/3/6); (R4) startup warmstart context report from real MT5
history; (R5) macro/futures UNAVAILABLE proven neutral by test. New
growth_evaluation profile for the milestone campaign. Survival anchors
(2%/5%, protected add-ons, stop mandatory, contraction-only) unchanged.

---

# 14. DEMO-CHALLENGE-001 — 2026-06-11 (tenth pass)

## F-16. The institutional model froze on stale structural-stop verdicts
- **Class:** Proven Defect of the operational posture (ADDRESSED by a
  separate profile, not by weakening the institutional model)
- **Evidence:** 570+ live cycles across strong XAUUSDm movement; direction
  repeatedly read correctly (bearish MTF, aligned intel); zero trades. The
  dominant blocker STOP_TOO_WIDE_FOR_ACCOUNT repeated for hours because the
  candidate stop came from HTF/warmstart structure while fresh M1/M5 local
  swings formed every candle and were never consulted for a tactical stop.
- **Response:** `--profile demo_challenge` (decision 2026-06-11-01): a
  DEMO-ONLY aggressive momentum decision layer (fixed lots 0.05/0.10,
  tactical M1/M5 local stops with an 8 USD ceiling, fresh entry scan every
  cycle, add-ons only into floating profit, max 3 open) behind the SAME
  session/gateway/journal safety stack. The institutional pipeline remains
  intact and default.
- **Lesson:** every new candle is a new execution opportunity check; a
  warmstart thesis must inform context, never lock the entry plan or the
  stop source for hours.

Survival guards for the experiment: 3% worst-case per trade, daily 5%
entry pause, weekly 10% shutdown, mandatory tactical stop, kill switch,
no martingale/grid/averaging/hedging structurally. Real-money gates are
unaffected; nothing from this experiment approves real trading.
