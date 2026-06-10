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
