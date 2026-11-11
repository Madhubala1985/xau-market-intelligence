# 10_TASK_QUEUE.md

## Purpose

This file defines the ordered implementation roadmap.

Claude must complete tasks in order unless explicitly instructed otherwise.

---

# Phase 13: Single-model rebuild

## Task LIQUIDITY-INTEL-001: ONE clean autonomous model (liquidity_intel)

Status: IMPLEMENTED (branch rebuild/liquidity_intel; 810 tests pass).
Live-trading gated by the real-history replay ship bar.

Goal:
Rebuild into one decision engine, one execution path, one trading
service, one account source, one accounting source. Retire every prior
profile and dual path. Profit-seeking posture model with protected stops.

Expected output (done):
- src/strategy/liquidity_intel.py (posture engine) + intel_planner.py,
- single profile + retired-name guard (session_profiles.py),
- fork removed from scripts/trading_service.py,
- tests (liquidity_intel / intel_planner / single_path) + retargets,
- single-engine ship gate (scripts/decision_replay.py),
- 27_LIQUIDITY_INTEL_DESIGN.md.

Tests: pytest (810 pass); tests/test_single_path.py enforces invariants.

Stop condition / next step:
- On the Windows MT5 host: run scripts/decision_replay.py --days 25; if
  the ship bar passes, run --profile liquidity_intel; else stay FLAT.
- commit LIQUIDITY-INTEL-001.

---

# Phase 0: Project Foundation

## Task P0-001: Create Project Control Pack

Goal:
Create and verify all control-pack files.

Expected output:
- all control-pack files completed,
- CLAUDE.md completed,
- CURRENT_STATE.md completed,
- verification script passes.

Tests:
- scripts/verify_control_pack.sh

Stop condition:
- commit P0-001.

---

## Task P0-002: Create Repository Structure

Status:
Completed in commit P0-002.

Expected folders:
- src/data
- src/broker
- src/execution
- src/risk
- src/structure
- src/regime
- src/liquidity
- src/orderflow
- src/strategy
- src/trade_management
- src/journal
- src/reflection
- src/backtest
- src/utils
- tests
- configs
- data/raw
- data/processed
- logs
- reports
- scripts

---

# Phase 1: Data Foundation

## Task P1-001: Define Core Data Schemas

Goal:
Create schemas for Candle, Tick, SpreadSnapshot, SessionState, BrokerState, TradeDecision, TradeRecord.

Allowed files:
- src/data
- src/utils
- tests

Tests:
- schema validation tests.

Stop condition:
- schemas pass tests.

---

## Task P1-002: MT5 Demo Data Adapter

Goal:
Connect to MT5 demo terminal and fetch XAU/USD candles safely.

Rules:
- demo credentials loaded from .env,
- no real trading,
- order sending disabled unless explicit demo execution task,
- symbol must be XAU/USD mapped carefully.

Tests:
- adapter initializes,
- fetches latest candles,
- rejects wrong symbols,
- does not print credentials.

Stop condition:
- validated sample candle output.

---

## Task P1-003: Data Validation Engine

Goal:
Detect missing candles, duplicate candles, stale data, bad OHLC, spread anomalies, timestamp issues.

Tests:
- malformed data is rejected,
- valid data passes,
- invalid data produces NO_TRADE status.

---

# Phase 2: Session and Timeframe Context

## Task P2-001: Timeframe Aggregation

Goal:
Build reliable 1M to 5M/15M/1H/4H/Daily aggregation.

Tests:
- aggregation correctness,
- no future leakage.

---

## Task P2-002: Session/Kill-Zone Engine

Goal:
Classify Asian, London, New York, London-New-York overlap, low-liquidity periods.

Tests:
- timestamp-to-session mapping,
- session highs/lows tracking.

---

# Phase 3: Market Structure and Liquidity

## Task P3-001: Swing and Structure Engine

Goal:
Detect swing highs/lows, BOS, CHOCH.

Tests:
- fixed candle examples.

---

## Task P3-002: Liquidity Map Engine

Goal:
Detect buy-side liquidity, sell-side liquidity, equal highs/lows, session highs/lows, previous day/week highs/lows.

Tests:
- known examples.

---

## Task P3-003: Liquidity Sweep Engine

Goal:
Detect sweep, rejection, reclaim, displacement confirmation.

Tests:
- true sweep,
- false sweep,
- no sweep.

---

## Task P3-004: FVG / Order Block / Supply-Demand Engine

Goal:
Detect FVGs, order-block-like zones, supply/demand zones, mitigation status.

Tests:
- valid/invalid zones.

---

## Task P3-005: Premium/Discount Engine

Goal:
Mark premium/discount areas using selected swing ranges and optional Gann-box-style segmentation.

Tests:
- correct zone mapping.

---

# Phase 4: Regime and Bias

## Task P4-001: Daily and 4H Bias Engine

Goal:
Classify higher-timeframe bias as bullish, bearish, neutral, or no-trade.

Tests:
- bias cases.

---

## Task P4-002: Regime Engine

Goal:
Classify trend, range, compression, expansion, choppy, news-risk, no-trade.

Tests:
- regime cases.

---

# Phase 5: Order-Flow Proxy and Futures Context

## Task P5-001: Order-Flow Proxy Engine

Goal:
Use MT5 tick volume, spread behavior, tick movement, and optional delta/CVD proxy cautiously.

Tests:
- proxy values calculated,
- no direct trade signal from proxy alone.

---

## Task P5-002: Gold Futures Confirmation Layer

Goal:
Add optional gold futures confirmation context.

Rules:
- no look-ahead bias,
- futures confirms confidence only,
- futures cannot trigger trade alone.

Tests:
- confirmation boosts/reduces confidence,
- missing futures data does not break core system.

---

# Phase 6: Trade Hypothesis and Scoring

## Task P6-001: Trade Hypothesis Engine

Goal:
Generate LONG, SHORT, WAIT, NO_TRADE hypotheses with thesis, invalidation, target logic.

Tests:
- no thesis = no trade,
- no invalidation = no trade.

---

## Task P6-002: Confidence and Uncertainty Engine

Goal:
Score structure, liquidity, regime, volatility, session, order-flow proxy, futures confirmation, execution quality.

Tests:
- high uncertainty blocks/reduces trade,
- confidence alone cannot bypass risk.

---

# Phase 7: Risk and Execution

## Task P7-001: Risk Governor

Goal:
Implement full risk checks.

Tests:
- all risk-blocking cases.

---

## Task P7-002: Position Sizing

Goal:
Calculate lot size from risk, stop distance, broker contract rules, spread/slippage buffer.

Tests:
- correct lot calculation,
- excessive risk blocked.

---

## Task P7-003: MT5 Demo Execution Gateway

Goal:
Place MT5 demo trades only after risk approval.

Tests:
- wrong symbol blocked,
- no SL blocked,
- duplicate blocked,
- order state logged,
- no credentials printed.

---

# Phase 8: Trade Management

## Task P8-001: Stop Placement Intelligence

Goal:
Place stop beyond thesis invalidation using volatility and liquidity buffer.

Tests:
- obvious stop rejected,
- logical stop accepted.

---

## Task P8-002: Trailing Stop Engine

Goal:
Implement structure-based, volatility-based, and liquidity-target trailing.

Tests:
- no premature trailing,
- no widening stop,
- valid partial/runners.

---

# Phase 9: Journal and Reflection

## Task P9-001: Trade Journal

Goal:
Log every trade and no-trade decision.

Tests:
- decisions persisted,
- restart-safe.

---

## Task P9-002: Reflection Engine

Goal:
Classify mistakes and generate daily review.

Tests:
- mistake categories assigned.

---

# Phase 10: Backtest and Validation

## Task P10-001: Backtesting Engine

Goal:
Backtest with spread, slippage, risk, stop logic, session logic.

Tests:
- no future leakage,
- realistic fills.

---

## Task P10-002: Walk-Forward Validation

Goal:
Validate on unseen periods.

Tests:
- train/test split,
- no leakage.

---

# Phase 11: Live Shadow and Real Readiness

## Task P11-001: Live Shadow Mode

Goal:
Run live market analysis without sending real-money orders.

Tests:
- live decisions logged,
- real orders not sent.

---

## Task P11-002: Real-Mode Readiness Review

Goal:
Verify all gates before real money.

Rules:
- no real execution without manual approval.

Stop condition:
- readiness report only.

---

# Phase 12: Live Demo Readiness

## Task RISK-001: Leverage-Aware Sizing and Protected Pyramiding

Goal:
Update risk/position-sizing logic so the system understands XAU/USD lot size, contract size, min lot, lot step, margin, leverage, stop distance, implied USD loss, total open risk, confidence-tiered demo sizing, and protected add-on trades.

Rules:
- Do not enable real trading.
- Do not place orders.
- Do not print credentials.
- Do not touch .env.
- Demo may allow higher loss caps than real mode.
- Real-money initial risk remains conservative.
- 0.05 and 0.10 lot may be allowed in demo only if calculated stop-loss risk is inside the demo tier cap.
- Fixed lot size must never bypass calculated risk.
- Leverage/margin availability must never bypass max-loss rules.
- Adding another same-direction trade is allowed only when the existing trade is protected at break-even or locked profit.
- Adding to a losing trade is forbidden.

Required tests:
- 0.01, 0.05, and 0.10 lot XAU/USD scenarios,
- leverage/margin cannot bypass max-loss rules,
- pyramiding allowed only into protected winning trades,
- averaging down / adding into loss is blocked,
- total open XAU/USD exposure enforced.

Stop condition:
- all tests pass,
- docs updated,
- commit RISK-001.

---

## Task LIVE-VERIFY-001: Generate Implementation Evidence Pack

Goal:
Create a compact report showing implemented modules, tested modules, stubbed/mocked modules, live-proven modules, and not-yet-live-proven modules.

Rules:
- No broad rewrite.
- No strategy changes.
- No order placement.

Stop condition:
- evidence report created under reports/runtime/,
- commit LIVE-VERIFY-001.

---

## Task WINMT5-001: Validate MT5 Demo Connectivity

Goal:
Validate MT5 demo terminal connectivity and XAU/USD read-only data.

Rules:
- No orders.
- No order_send.
- No credentials printed.
- If WSL cannot import MetaTrader5, create a Windows-side runner or safe bridge plan.

Required proof:
- MT5 init/login,
- demo account verified,
- XAU/USD symbol detected,
- symbol info read,
- candles fetched,
- spread read,
- account info read safely.

Stop condition:
- validation report created,
- commit WINMT5-001.

---

## Task LIVE-001: Connect Live/Replay Data to DecisionPipeline and ShadowRunner

Goal:
Feed real or replayed XAU/USD data into DecisionPipeline and ShadowRunner.

Rules:
- No orders.
- Pipeline may generate decisions.
- ShadowRunner may log would-trade decisions.
- ExecutionGateway must not send orders.

Stop condition:
- end-to-end shadow run works on replay/live data,
- tests pass,
- commit LIVE-001.

---

## Task LIVE-002: Run Live Shadow Session

Goal:
Run supervised XAU/USD live shadow mode with real market data.

Rules:
- No orders.
- Log every decision and no-trade.
- Produce session report.

Stop condition:
- shadow session report created,
- commit LIVE-002.

---

## Task DEMO-001: Demo Execution Preflight

Goal:
Verify all demo execution gates before order_send is allowed.

Rules:
- No real orders.
- Demo only.
- Check all env flags.
- Verify account is demo.
- Verify stop-loss enforcement.
- Verify risk governor.
- Verify journal/state persistence.

Stop condition:
- preflight report created,
- commit DEMO-001.

---

## Task DEMO-002: Supervised MT5 Demo Trading Run

Goal:
Run supervised MT5 demo trading with XAU/USD only.

Rules:
- Demo only.
- Real trading forbidden.
- Risk governor final authority.
- Stop-loss mandatory.
- Protected pyramiding only.
- Manual kill switch required.
- Session report required.

Stop condition:
- supervised demo session completed,
- journal and reflection report created,
- commit DEMO-002.

---

## Task DEMO-EVAL: Serious Demo Evaluation and Reflection Workflow

Goal:
Finish the supervised demo session as a serious performance-evaluation engine
on real Exness MT5 demo execution (XAUUSDm), with the same architecture that
will later support real mode through configuration and readiness gates.

Rules:
- Demo only; real trading forbidden.
- Order limits configurable by session risk profile, never hardcoded to one;
  profiles may tighten 03_RISK_POLICY demo limits, never loosen them.
- max_orders=1 survives only as the smoke-test profile.
- Dry-run must rehearse the full planner -> gateway path (simulated orders).
- Reports must separate shadow decisions, dry-run simulated orders, and real
  MT5 demo orders.
- Post-session evaluation + reflection reports required; findings classified
  Proven Defect / High-Confidence Defect / Hypothesis / Observation /
  Design Improvement; no live self-mutation.

Tests:
- profile policy bounds, no artificial cap in evaluation mode, policy-driven
  order limits, dry-run simulation, cycle stats, evaluation/reflection report
  correctness, performance metrics, credential hygiene.

Stop condition:
- all tests pass,
- docs updated (CURRENT_STATE, HANDOFF, DECISION_LOG, AUDIT ROADMAP, RUNBOOK),
- commit DEMO-EVAL.

Status:
Completed in commit DEMO-EVAL.

---

## Task CONTINUOUS-001: Continuous MT5 Trading Service

Goal:
One continuous XAU/USD MT5 trading service as the MAIN mode: start once,
connect to the .env account, run the DecisionPipeline continuously, execute
approved trades through planner -> governor -> gateway, reconcile positions,
manage stops, pause while the market is closed, resume on open, and report
daily — until kill switch, risk shutdown, fatal error, or Ctrl+C.

Rules:
- ONE execution stack (no demo-only/live-only duplication); .env decides the
  account (currently Exness DEMO), execution flags decide sending.
- No fixed 1-hour duration, no artificial one-order cap; the risk policy
  governs trade frequency. Smoke/dry-run remain optional tools.
- Full terminal observability: startup banner + per-cycle progress; no
  credentials printed (login masked); orders print MT5 tickets.
- Daily evaluation + reflection reports at UTC rollover.

Tests:
- no fixed duration / no artificial cap, market-closed wait + resume,
  restart reconciliation + close detection, kill switch / weekly-loss
  shutdown / Ctrl+C clean stops, daily-loss pause, rollover reports, banner
  and progress output, dry-run cannot send, credential hygiene.

Stop condition:
- all tests pass, docs updated, commit CONTINUOUS-001.

Status:
Completed in commit CONTINUOUS-001.

---

## Task INTELLIGENCE-001: Wire Gold Confluence, MTF Alignment, and Adaptive Risk

Goal:
Turn the continuous runner into an adaptive trading intelligence: graded
CHOPPY subtypes instead of a blind hard block, real D1/H4/H1/M15/M5
alignment, FVG/order-block/premium-discount/displacement wired into the live
DecisionPipeline, an evidence-driven adaptive risk budget (policy-capped),
full per-cycle terminal reasoning, and an automatic opportunity audit after
long no-trade stretches.

Rules:
- Selective aggression only: graded confluence gates, never forced trades.
- DANGEROUS/LOW_QUALITY chop, NEWS_RISK, NO_TRADE keep hard-blocking.
- Stop-loss and structural invalidation stay mandatory.
- Adaptive risk can only stay under the 03_RISK_POLICY cap; contraction-only
  on losses/drawdown/uncertainty (no martingale structurally).
- No fake data: missing timeframes/feeds read as absent, never invented.

Status:
Completed in commit INTELLIGENCE-001.

---

## Task INTELLIGENCE-002: Verify Wiring, True MTF, Session Logic, Adaptive Demo Risk

Goal:
Prove every intelligence layer is truly live-wired (25_WIRING_MATRIX.md),
fetch real MT5 M15/H1/M1 candles with honest degradation, wire Asian range +
London/NY expansion into confluence, add the dangerous-volatility safety
classifier, replace the flat 0.5% demo cap with the evidence-gated Adaptive
Demo Risk Policy (per-phase ceilings; daily/weekly anchors unchanged),
extend opportunity-audit verdicts, and ship the BACKTEST-001 calibration
replay tool.

Status:
Completed in commit INTELLIGENCE-002.

---

## Task FINAL-INTELLIGENCE: Complete News, Macro, Futures, Calibration, M1, Wiring

Goal:
Finish the remaining intelligence layers honestly: NewsProvider architecture
with graded states and severity-based block/reduce; stale-aware operator
macro/futures file feeding confluence confirmation; M1 veto/delay refinement;
calibration verdicts (KEEP/TIGHTEN/LOOSEN/NEED_MORE_DATA) with drawdown and
missed-opportunity decomposition; executable wiring verification; terminal
and banner upgrades.

Status:
Completed in commit FINAL-INTELLIGENCE.

---

## Task SIZING-001: Adaptive Lot Sizing and Milestone-Aware Risk Diagnostics

Goal:
Fix the Proven Defect where a defensive adaptive budget below the broker
minimum lot produced "invalid lot size 0.0": explicit min-lot viability
(promotion within the phase ceiling, or a fully-diagnosed block), dynamic
never-fixed lot sizing from loss-at-stop math, planner-path promotion,
threshold profiles (current/demo_exploration), and full terminal sizing
diagnostics with milestone context.

Status:
Completed in commit SIZING-001.

---

## Task OPERATIONAL-INTELLIGENCE-001: Warmstart Context and Adaptive Exposure

Goal:
Startup multi-timeframe warmstart report; 4-decimal raw-confluence threshold
display with margin and alt-profile answer; DIRECTIONAL_CHOP_BREAKDOWN for
MTF-backed moves; AdaptiveExposureGovernor (condition-driven 0-6 entries/day
bounded by profile); growth_evaluation profile; macro/futures neutrality
verified.

Status:
Completed in commit OPERATIONAL-INTELLIGENCE-001.

---

## Task DEMO-CHALLENGE-001: Aggressive Fixed-Lot Momentum Profile (DEMO ONLY)

Goal:
One final aggressive demo attempt as a SEPARATE profile
(--profile demo_challenge) without touching the institutional model:
simplified momentum execution (M15/M5 alignment or displacement), fixed
lots 0.05/0.10, tactical M1/M5 local stops instead of structural stops,
fresh entry scan every candle, same-direction pyramiding only into floating
profit (max 3 open), macro/futures/news-unknown neutral, full per-cycle
terminal reasoning.

Rules:
- DEMO ONLY; the owner-directed demo_challenge envelope (3%/trade worst
  case, daily 5% pause, weekly 10% stop) is construction-locked to this
  one profile (decision 2026-06-11-01).
- Stop-loss mandatory (tactical local structure); skip when no local stop.
- No martingale, grid, averaging down, or opposite-direction hedging.
- Kill switch, gateway-only sending, and demo-only flags unchanged.
- The institutional pipeline remains intact and default.

Status:
Completed in commit DEMO-CHALLENGE-001.

---

## Task SMC-EXECUTION-001: Institutional SMC Execution Mode + MT5 Accounting Truth

Goal:
Stop the retail momentum behavior of demo_challenge and replace it with the
institutional SMC execution mode (--profile smc_challenge; demo_challenge
becomes a deprecated alias), and make MT5 the only source of truth for
P&L/accounting.

Rules:
- A trade requires ALL gates per candle: HTF context (D1/H4/H1/M15),
  session/liquidity context (kill zone / Asian or session sweep /
  liquidity target), an SMC anchor (sweep+displacement, FVG/OB retest,
  break-retest, BOS/CHOCH), and an executable M5/M1 trigger with a
  structurally justified tactical stop. M1/M5 momentum alone never trades.
- Failed gates produce re-entry plans (waiting_for=...), never silent
  multi-hour blocks.
- Closed P&L only from MT5 deal history (position= variant, per-deal
  position_id checks, balance deals excluded); daily realized P&L only
  from today's MT5 trade deals; unverified accounting blocks new entries;
  2 consecutive MT5 losses pause entries (cooldown).
- Add-ons only onto protected winners (break-even stop or >= 0.5R
  floating), never in the same M5 candle, never with weakened SMC context.
- Envelope, fixed lots, kill switch, gateway-only sending, and all
  forbidden behaviors unchanged. Real trading remains forbidden.

Status:
Completed in commit SMC-EXECUTION-001.

---

## Task SMC-V2-001: Day-Narrative Decision Brain + Replay Validation Gate

Goal:
Rebuild the DECISION LAYER per 26_SMC_V2_DESIGN.md (decision
2026-06-12-10): DayNarrative state machine, conviction ledger, per-state
playbooks with trade memory, quality scoring — as a new pipeline behind
the UNCHANGED execution chassis, plus scripts/decision_replay.py for the
head-to-head historical validation gate.

Rules:
- Chassis untouched: gateway, MT5 accounting, sizing, stops, trailing,
  brakes, kill switch. Envelope shared with smc_challenge, never widened.
- v2 trades live demo ONLY after beating v1 on >= 10 days of replayed
  real MT5 history (net R, max DD, no edge destruction on v1's win days).
- smc_challenge remains the fallback profile.

Tests:
- state machine transitions on constructed days (trend/range/trap/spike),
- conviction accumulation/decay and sign-flip lockout,
- playbook permissions per state + probe limits + playbook day-cooldown,
- replay harness: conservative fills (SL-first ambiguity, spread+slippage),
  deterministic on fixed candles,
- full safety suite stays green.

Stop condition:
- replay report committed with the verdict; v2 enabled only on a PASS.

Status:
In progress (started 2026-06-12).

---

## Task ALPHA-HUNT-001: Reopened edge search on the never-tested space

Goal:
Owner directive 2026-07-05 — make the model profitable; full authority; high
trade counts fine. Attack ONLY the space 40_CONCLUSION.md never tested, with
new data. Program and phase gates: 42_ALPHA_HUNT.md.

Rules:
- Statistical honesty gates kept (decision 2026-07-05-01): causal sim, cost
  stress, walk-forward, random baseline (Bonferroni), untouched 2026 holdout.
- Demo-only, mandatory SL, no martingale, MT5 truth, kill switch: absolute.
- Do NOT re-test falsified factors (31_EDGE_AUDIT.md) except as controls.

Phases:
A. Data — Dukascopy M1 2019-2026: XAUUSD/XAGUSD/EURUSD/DOLLARIDXUSD (running).
B. Map — conditional-return grid scan (time-of-day, DOW, sessions, fixes,
   momentum/reversal horizons, vol conditioning) vs shuffled baselines.
C. Model — purged walk-forward ML on engineered features; OOS IC, then
   cost-stressed trade sim through the frozen classification gate.
D. Verify — 2026 holdout replication + random-entry z >= 2.39.
E. Deploy — survivors only, demo, via ResearchForwardRunner -> gateway.

Status:
In progress (started 2026-07-05). Phase A running.
