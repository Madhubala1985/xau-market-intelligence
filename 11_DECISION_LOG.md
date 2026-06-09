# 11_DECISION_LOG.md

## Purpose

This file records important project decisions.

Claude must update this file whenever architecture, risk, execution, model logic, or validation policy changes.

---

# Decision Entry Template

## Decision ID:
YYYY-MM-DD-NN

## Date:
YYYY-MM-DD

## Area:
Architecture / Risk / Execution / Data / Strategy / Testing / Adaptation / Broker / Other

## Decision:
Describe the decision clearly.

## Reason:
Why this decision was made.

## Evidence:
What evidence supports it.

## Alternatives Considered:
List alternatives and why they were rejected.

## Risk:
What can go wrong.

## Mitigation:
How risk is controlled.

## Files Affected:
List files.

## Status:
Proposed / Accepted / Rejected / Superseded

---

# Initial Decisions

## Decision ID:
INIT-001

## Area:
Instrument Scope

## Decision:
The system trades XAU/USD only.

## Reason:
Single-instrument focus improves specialization, reduces complexity, and prevents architecture drift.

## Status:
Accepted

---

## Decision ID:
INIT-002

## Area:
Execution

## Decision:
MT5 demo execution through Exness demo account is the first broker execution path.

## Reason:
User has an Exness demo account connected through MT5.

## Status:
Accepted

---

## Decision ID:
INIT-003

## Area:
Risk

## Decision:
Risk governor has final authority over all trades.

## Reason:
Capital protection is more important than signal confidence.

## Status:
Accepted

---

## Decision ID:
INIT-004

## Area:
Adaptation

## Decision:
Live self-mutation is forbidden.

## Reason:
Uncontrolled live adaptation can destroy the account.

## Status:
Accepted

---

## Decision ID:
INIT-005

## Area:
Order Flow

## Decision:
MT5 volume, CVD, and delta are treated as proxies unless proven otherwise.

## Reason:
XAU/USD CFD/OTC data is not guaranteed centralized institutional order flow.

## Status:
Accepted

---

## Decision ID:
INIT-006

## Area:
Futures Confirmation

## Decision:
Gold futures data may support confidence but cannot trigger trades alone.

## Reason:
Futures can add context, but spot XAU/USD remains the execution instrument.

## Status:
Accepted

---

## Decision ID:
INIT-007

## Area:
Demo Risk

## Decision:
Demo risk profile allows 0.50% risk per trade, 2.00% daily loss, 5.00% weekly loss, 3 trades per day, and 1 open trade.

## Reason:
Demo mode should stress-test gold volatility while remaining controlled.

## Status:
Accepted

---

## Decision ID:
INIT-008

## Area:
Real Risk

## Decision:
Initial real risk, if approved later, starts lower than demo risk.

## Reason:
Small real capital requires capital survival before scaling.

## Status:
Accepted

---

## Decision ID:
2026-06-08-01

## Date:
2026-06-08

## Area:
Data

## Decision:
Core data schemas (P1-001) are Pydantic v2 models that are frozen (immutable)
and reject unknown fields (extra="forbid"). Candle/Tick preserve both the
original broker timestamp and a UTC-normalized timestamp; naive (timezone-
unaware) datetimes are rejected. Impossible OHLC and inconsistent bid/ask are
rejected at construction. TradeDecision enforces that an actionable LONG/SHORT
requires a thesis and an invalidation price. No schema in the data layer carries
credential fields.

## Reason:
Enforces 06_DATA_POLICY.md (single internal timezone, preserved timestamps,
rejection of malformed data) and the CLAUDE.md credentials rule at the type
boundary, so bad data and credentials cannot enter the pipeline silently.

## Evidence:
tests/test_schemas.py — 29 tests covering valid acceptance, invalid rejection,
timestamp normalization, immutability, and absence of credential fields. All
pass (30 total with the structure test).

## Alternatives Considered:
- Plain dataclasses: rejected — weaker validation, no built-in constraint checks.
- Storing a precomputed spread field on SpreadSnapshot: rejected in favor of a
  derived property to avoid redundant-but-inconsistent data.

## Risk:
Schema-level guardrails could be too strict for some upstream feeds.

## Mitigation:
Validation rules mirror documented policy; the P1-002 adapter is responsible for
mapping/localizing broker data into these schemas.

## Files Affected:
src/data/schemas.py, src/data/enums.py, src/data/__init__.py, src/utils/time.py,
tests/test_schemas.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-01

## Date:
2026-06-09

## Area:
Broker

## Decision:
The MT5 demo data adapter (P1-002) is read-only and takes an injected MT5 client
(lazy-importing MetaTrader5 only when none is provided). It never calls
order_send / order_check. Settings are loaded from environment variables, the
password and login are masked in repr/str, missing variables are reported by
NAME only, and a DEMO-only configuration is enforced before any connection.
MT5 server epochs are normalized using an optional MT5_SERVER_UTC_OFFSET_MINUTES
(default 0 == treat epoch as UTC).

## Reason:
MetaTrader5 is Windows-only, so dependency injection keeps the adapter testable
on Linux/WSL and lets tests prove no order function is ever invoked. Masking and
name-only error reporting enforce the CLAUDE.md Credentials Rule; the demo gate
enforces the Trading Safety Rule.

## Evidence:
tests/test_mt5_data_adapter.py — 21 tests covering settings validation, demo
enforcement, connect/fetch, timestamp normalization, symbol rejection, credential
masking, and order_send-never-called. All pass (51 total).

## Alternatives Considered:
- Hard import of MetaTrader5 at module load: rejected — breaks import/tests on
  non-Windows hosts.
- Adding MetaTrader5 to requirements.txt: rejected for now — not installable on
  Linux/WSL; to be installed on the Windows MT5 host at runtime.

## Risk:
The default server-time offset (0) may not match a given broker's server clock.

## Mitigation:
broker_time preserves the raw server wall-clock and the offset is configurable;
session/aggregation tasks (P2) can set it explicitly.

## Files Affected:
src/broker/errors.py, src/broker/mt5_settings.py, src/broker/mt5_data_adapter.py,
src/broker/__init__.py, tests/test_mt5_data_adapter.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-02

## Date:
2026-06-09

## Area:
Data

## Decision:
The Data Validation Engine (P1-003) validates a series of already-constructed
Candle objects and returns a ValidationReport whose status is NO_TRADE whenever
any BLOCKING issue is present. It detects empty input, mixed/mismatched symbols,
mixed timeframes, duplicate timestamps, non-monotonic/misaligned intervals,
missing candles, bad OHLC (defensive), spread-too-high, zero volume, stale data,
and look-ahead. Zero-volume is a WARNING by default. Stale/look-ahead checks
require an explicit `now` reference and are skipped otherwise.

## Reason:
Schema-level construction already rejects impossible OHLC and inconsistent
bid/ask, so the engine focuses on series-level and freshness properties the
schema cannot see. Enforces 06_DATA_POLICY.md: bad data must never produce a
trade.

## Evidence:
tests/test_data_validation.py — 17 tests covering valid-passes, malformed-
rejected, and NO_TRADE on each detection. All pass (68 total).

## Alternatives Considered:
- Validating raw dict rows before schema construction: rejected — duplicates
  the schema's guarantees; the adapter already emits validated Candles.
- Treating weekend/session gaps here: rejected — that belongs to the P2 session
  engine; gap detection is configurable (detect_gaps).

## Risk:
Strict gap detection could false-positive across legitimate weekend/session
breaks for XAU/USD.

## Mitigation:
detect_gaps is configurable and freshness checks require an explicit `now`;
session-aware handling is deferred to P2.

## Files Affected:
src/data/validation.py, src/data/__init__.py, tests/test_data_validation.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-03

## Date:
2026-06-09

## Area:
Data

## Decision:
Timeframe aggregation (P2-001) groups source candles into aligned UTC windows
[start, start+step). open=first open, high=max, low=min, close=last close,
tick_volume=sum, real_volume=sum (None if any source bar lacks it), spread=None.
Daily aligns to UTC midnight; intraday aligns to the UTC epoch grid. The bar is
labeled by the window start, and the still-forming trailing bar is withheld by
default (drop_incomplete=True): with a `now` reference, buckets whose end is
after `now` are dropped; without `now`, the most recent bucket is dropped.

## Reason:
Prevents future leakage (06_DATA_POLICY.md): each bar uses only data inside its
own window and is only emitted once the window has fully elapsed. UTC alignment
matches the single-internal-timezone policy.

## Evidence:
tests/test_aggregation.py — 22 tests covering OHLCV correctness, alignment
(intraday + daily), volume rules, broker-offset preservation, and no-future-
leakage (forming bar withheld, bars exclude next-window data). All pass (90 total).

## Alternatives Considered:
- Carrying a spread on aggregated bars (avg/last): rejected — an aggregated bar
  has no single spread; None avoids inventing data.
- Session/broker-day daily boundaries: deferred — UTC-midnight daily bars now;
  session-aware boundaries belong to P2-002 and can be layered on later.

## Risk:
UTC-midnight daily boundaries may not match a broker's trading day, and a None
`now` drops a possibly-complete last bar.

## Mitigation:
Daily boundary choice is documented; callers pass `now` (or drop_incomplete=False)
for precise control. Session engine (P2-002) will own session-relative windows.

## Files Affected:
src/data/aggregation.py, src/data/__init__.py, tests/test_aggregation.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-04

## Date:
2026-06-09

## Area:
Data

## Decision:
The Session/Kill-Zone engine (P2-002) tiles the UTC day into ordered,
non-overlapping segments covering [00:00, 24:00). The London-New-York overlap is
its own segment between London-only and New-York-only, so each UTC timestamp maps
to exactly one SessionType with exact [start, end) bounds and no gaps. Default
tiling: 00-08 ASIAN, 08-13 LONDON, 13-16 LONDON_NY_OVERLAP, 16-21 NEW_YORK,
21-22 ROLLOVER, 22-24 LOW_LIQUIDITY. Market is closed Saturday all day, Friday
from 21:00 UTC, and Sunday before 22:00 UTC. is_kill_zone and is_tradeable are
flags only and never trigger trades. Session highs/lows are tracked per
occurrence and as running (no-look-ahead) values via annotate().

## Reason:
A tiling model gives unambiguous, gap-free timestamp->session mapping with exact
bounds, satisfying 06_DATA_POLICY.md (classify on normalized UTC time) and
14_SESSION_KILLZONE_POLICY.md (distinct overlap and low-liquidity classes; kill
zone cannot trigger trades).

## Evidence:
tests/test_sessions.py — 27 tests covering hour mapping, half-open boundaries,
UTC normalization, weekend/closed handling, flags/bounds, and per-occurrence +
running level tracking. All pass (117 total).

## Alternatives Considered:
- Overlapping session windows (London 08-16, NY 13-21) with precedence: rejected
  in favor of explicit tiling for exact bounds and no ambiguity.
- DST-aware session shifts: deferred — windows are configurable; fixed UTC
  defaults now, broker/DST nuances later.

## Risk:
Fixed UTC windows may drift from real session opens under DST.

## Mitigation:
All windows and weekend thresholds are configurable via SessionConfig (validated
to tile the day); defaults documented.

## Files Affected:
src/data/sessions.py, src/data/__init__.py, tests/test_sessions.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-05

## Date:
2026-06-09

## Area:
Strategy

## Decision:
The swing & market-structure engine (P3-001) detects swings as fractal pivots
(strict extreme vs `strength` candles each side, default 2) that are CONFIRMED
only at index i + strength. BOS/CHOCH are decided from candle closes breaking the
most recent confirmed swing level: a break continuing the prevailing bias is BOS;
the first break against it is CHOCH (flips bias); the first break overall is
reported as BOS. Broken levels are consumed until a new swing of that type
confirms. Equal highs/lows produce no swing (strict comparison).

## Reason:
Mechanical, deterministic detection per 13_XAUUSD_SMC_PLAYBOOK.md, with strict
no-look-ahead: confirmation lag plus close-based breaks make results prefix-
stable, so live and backtest see identical structure.

## Evidence:
tests/test_market_structure.py — 8 tests on fixed candle examples covering swing
detection, confirmation lag, equal-high suppression, a full BOS/BOS/CHOCH
narrative, ranging (no events), short series, and prefix stability (no look-ahead).
All pass (125 total).

## Alternatives Considered:
- Wick-based breaks: rejected for now in favor of close-based breaks (fewer false
  breaks); can be made configurable later if needed.
- Treating equal highs/lows as swings: rejected — they are liquidity (equal
  highs/lows) and belong to the P3-002 liquidity engine.

## Risk:
Close-based detection may lag wick-driven breaks; fractal strength affects
sensitivity.

## Mitigation:
strength is configurable; break basis can be extended later. Detection is
documented and deterministic.

## Files Affected:
src/structure/market_structure.py, src/structure/__init__.py,
tests/test_market_structure.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-06

## Date:
2026-06-09

## Area:
Strategy

## Decision:
The liquidity map engine (P3-002) builds a map of resting-liquidity levels only:
swing highs/lows (reusing P3-001), equal highs/lows (clusters of near-equal
swings within equal_tolerance, default 0.1), session highs/lows (reusing P2-002,
main sessions only), and previous day/week highs/lows. High-type levels are
classified BUY_SIDE (rest above price), low-type SELL_SIDE. Equal-cluster price =
top for highs / bottom for lows; previous day/week = the period immediately
before the latest candle's period. Sweep/manipulation detection is deliberately
excluded (it is task P3-003).

## Reason:
Matches the P3-002 goal exactly and 15_LIQUIDITY_ENGINEERING.md liquidity types,
while keeping scope tight (map only). Reuses existing swing and session engines
to stay consistent and DRY. No look-ahead: levels derive only from supplied
candles.

## Evidence:
tests/test_liquidity_map.py — 9 tests on known examples covering swing levels +
sides, equal highs (and the outside-tolerance negative), session highs/lows,
previous day and previous week levels, single-period (no prev), empty input, and
a no-look-ahead prefix check. All pass (134 total).

## Alternatives Considered:
- Including round-number and breakout zones (in the policy): deferred — not in the
  P3-002 goal; avoid scope creep.
- Basing equal highs/lows on raw candle highs instead of swing pivots: rejected —
  swing-based clustering reduces noise.

## Risk:
equal_tolerance and swing strength affect which clusters/levels appear; round
numbers and breakout liquidity are not yet mapped.

## Mitigation:
Both are configurable; remaining liquidity types can be added later without
changing the level model.

## Files Affected:
src/liquidity/liquidity_map.py, src/liquidity/__init__.py,
tests/test_liquidity_map.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-07

## Date:
2026-06-09

## Area:
Strategy

## Decision:
The liquidity sweep engine (P3-003) classifies sweeps against known liquidity
levels in three states: a CANDIDATE forms when a level is taken (wick beyond)
and price closes back across it with a rejection wick >= rejection_ratio of the
candle range; it becomes TRUE_SWEEP when, within confirm_window, both a
displacement candle (range >= displacement_factor * baseline) and a structure
event (BOS/CHOCH, reusing P3-001) appear in the rejection direction; it is
FALSE_SWEEP if the window elapses without both, and PENDING while the window is
still open. A taken-but-closed-through level (breakout) and an untouched level
produce no event. Buy-side sweep -> bearish rejection; sell-side -> bullish.

## Reason:
Encodes 15_LIQUIDITY_ENGINEERING.md mechanically ("a wick alone is not enough";
sweep requires take-out + close-back + displacement + structure). Reuses the
structure engine for confirmation. A sweep is not a trade by itself, so the
engine only classifies.

## Evidence:
tests/test_sweep.py — 8 tests covering true sweep (buy- and sell-side), false
sweep (no confirmation), no sweep (clean breakout / untouched level), level
formed after the candle ignored, PENDING before the window elapses, and a level
consumed by its first sweep. All pass (142 total).

## Alternatives Considered:
- Self-contained "follow-through past sweep candle" instead of reusing the
  structure engine: rejected — reusing P3-001 is more faithful and DRY.
- Marking unconfirmed open candidates as FALSE immediately: rejected — would be
  look-ahead-unsafe; PENDING until the window elapses is correct for live use.

## Risk:
Thresholds (rejection_ratio, displacement_factor, confirm_window) affect
sensitivity; structure confirmation depends on swing strength.

## Mitigation:
All thresholds and requirement flags are configurable; detection is deterministic
and documented.

## Files Affected:
src/liquidity/sweep.py, src/liquidity/__init__.py, tests/test_sweep.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-08

## Date:
2026-06-09

## Area:
Strategy

## Decision:
The zone engine (P3-004) detects three zone categories from candles: FVG
(3-candle imbalance, created at the third candle), ORDER_BLOCK (the last opposing
candle before a structure-breaking move, reusing P3-001 structure events,
created at the break), and SUPPLY_DEMAND (the base candle before a displacement
candle, no structure break required). Bias BULLISH = demand/support, BEARISH =
supply/resistance. Mitigation is set when a later candle overlaps the zone range
and is evaluated only from candles after the creation index. The engine lives in
src/structure/zones.py alongside the market-structure engine.

## Reason:
Encodes 02_ARCHITECTURE.md section 7 and 13_XAUUSD_SMC_PLAYBOOK.md mechanically.
Reuses the structure engine for order blocks (DRY). Mitigation after creation
keeps results no-look-ahead and prefix-stable. Co-locating with market structure
keeps structural concepts together (no new top-level package needed).

## Evidence:
tests/test_zones.py — 11 tests on valid/invalid zones: bullish/bearish FVG, no-gap
negative, FVG mitigation, bullish order block, no-OB-without-break, demand/supply
zones, no-supply-demand-without-displacement, build() combining kinds, and a
no-look-ahead prefix mitigation check. All pass (153 total).

## Alternatives Considered:
- A new top-level package for zones: rejected — structural zones belong with
  src/structure.
- Modeling supply/demand identically to order blocks: rejected — supply/demand is
  displacement-origin based (no structure break) and kept distinct.

## Risk:
min_gap, displacement_factor, swing strength, and order-block lookback affect
which zones appear; OB uses full candle range rather than body.

## Mitigation:
All thresholds are configurable; detection is deterministic and documented.
Body-based OB can be added later without changing the Zone model.

## Files Affected:
src/structure/zones.py, src/structure/__init__.py, tests/test_zones.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-09

## Date:
2026-06-09

## Area:
Strategy

## Decision:
The premium/discount engine (P3-005) models a DealingRange (swing high/low) with
equilibrium at the 50% midpoint. classify() returns DISCOUNT below equilibrium,
PREMIUM above, and EQUILIBRIUM within a configurable band around 50% (default 0).
segments() produces Gann-box-style bands at configurable fractions (default
quartiles 0/25/50/75/100%), each classified premium/discount/equilibrium.
range_from_candles() auto-selects the most recent confirmed swing high and low
(reusing P3-001). Lives in src/structure/premium_discount.py.

## Reason:
Encodes premium/discount location (13_XAUUSD_SMC_PLAYBOOK.md) mechanically and
deterministically. Reuses confirmed swings so range selection is no-look-ahead.
Decoupling DealingRange from selection lets callers supply explicit ranges.

## Evidence:
tests/test_premium_discount.py — 11 tests covering range geometry, degenerate
rejection, premium/discount/equilibrium classification (incl. outside-range and a
band), default quartile + custom segmentation, invalid segments, and auto range
selection from candles. All pass (164 total).

## Alternatives Considered:
- Fibonacci/OTE sub-zones: deferred — not required by P3-005; segmentation
  fractions are configurable so OTE bands can be added later.
- A new top-level package: rejected — premium/discount is a structural concept,
  kept in src/structure.

## Risk:
Range selection uses only the most recent swing high/low; multi-leg or
higher-timeframe range selection may be needed later.

## Mitigation:
DealingRange can be constructed explicitly by callers (e.g., the bias engine);
segmentation and equilibrium band are configurable.

## Files Affected:
src/structure/premium_discount.py, src/structure/__init__.py,
tests/test_premium_discount.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-10

## Date:
2026-06-09

## Area:
Strategy

## Decision:
The Daily/4H bias engine (P4-001) derives each timeframe's directional bias from
market-structure final_bias (P3-001) and combines them with Daily as the primary
authority: Daily None -> NO_TRADE; Daily NEUTRAL -> NEUTRAL; Daily directional
with an opposing 4H -> NO_TRADE (conflict); otherwise the Daily direction
(4H confirming or merely not opposing). Output enum HtfBias =
BULLISH/BEARISH/NEUTRAL/NO_TRADE. Lives in src/regime/htf_bias.py.

## Reason:
Encodes 02_ARCHITECTURE.md section 4. Reusing structure bias keeps HTF context
consistent with lower-timeframe analysis and prefix-stable (no look-ahead).
Treating conflict and missing-daily as NO_TRADE keeps the system safe when HTF
context is ambiguous.

## Evidence:
tests/test_htf_bias.py — 10 tests covering component biases and the full matrix:
aligned bull/bear, daily-leads-when-4H-neutral, both conflict cases -> NO_TRADE,
daily-neutral -> NEUTRAL, missing daily -> NO_TRADE, missing 4H -> daily leads.
All pass (174 total).

## Alternatives Considered:
- Folding premium/discount location into the bias: deferred — bias is structural
  direction; premium/discount is for entry refinement (downstream).
- Treating conflict as NEUTRAL: rejected — NO_TRADE is safer for ambiguous HTF
  context.

## Risk:
Bias depends on swing strength and the structure model; only Daily+4H are used.

## Mitigation:
swing_strength is configurable; BiasResult exposes the component biases and a
reason for downstream confidence scoring.

## Files Affected:
src/regime/htf_bias.py, src/regime/__init__.py, tests/test_htf_bias.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-11

## Date:
2026-06-09

## Area:
Strategy

## Decision:
The regime engine (P4-002) classifies a candle window into exactly one Regime via
a priority-ordered decision: insufficient data -> NO_TRADE; external news_risk
flag -> NEWS_RISK; structure direction flips >= 2 -> CHOPPY; events with no flips,
>= 1 BOS and a directional final_bias -> TREND; volatility ratio (second-half /
first-half avg candle range) >= 1.5 -> EXPANSION; <= 0.67 -> COMPRESSION; no
structural breaks -> RANGE; otherwise NO_TRADE. Reuses P3-001 structure events.

## Reason:
Encodes 02_ARCHITECTURE.md section 10 mechanically and deterministically.
Priority ordering guarantees a single regime per window. Reusing structure
events keeps regime consistent with the rest of the analysis stack; volatility
ratio captures compression/expansion. No look-ahead (prefix-stable structure;
window-only volatility).

## Evidence:
tests/test_regime.py — 7 tests: uptrend -> TREND, alternating structure -> CHOPPY
(>=2 flips), widening -> EXPANSION, contracting -> COMPRESSION, bounded/stable ->
RANGE, news flag -> NEWS_RISK, too-few-candles -> NO_TRADE. All pass (181 total).

## Alternatives Considered:
- Multi-label regimes (e.g., trending + expanding): rejected for now — a single
  priority-ordered label is simpler for downstream consumers; can be enriched
  later via RegimeResult features.
- Internal news detection: deferred — NEWS_RISK is an external flag until a
  validated news module exists.

## Risk:
Thresholds (expansion/compression factors, choppy_flips, min_candles, swing
strength) affect classification; volatility ratio is a coarse two-window measure.

## Mitigation:
All thresholds are configurable; RegimeResult exposes the underlying features
(bos/choch counts, flips, volatility_ratio) for downstream scoring.

## Files Affected:
src/regime/regime_engine.py, src/regime/__init__.py, tests/test_regime.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-12

## Date:
2026-06-09

## Area:
Order Flow

## Decision:
The order-flow proxy engine (P5-001) computes broker-level PROXY metrics from
candles (volume ratio/state, spread behavior, candle aggression, delta/CVD proxy,
CVD divergence, abnormal activity) and emits a ProxyPressure descriptor plus
bounded confidence/uncertainty adjustments and a note. By construction it NEVER
emits a trade signal: OrderFlowProxy.is_trade_signal is always False, the result
has no direction/signal/order/entry field, and the engine has no
decide/trade/buy/sell method. An optional structural_bias triggers a conflict
flag and raises uncertainty when proxy opposes structure.

## Reason:
Enforces INIT-005 and 16_ORDERFLOW_PROXY_POLICY.md: MT5 volume/CVD/delta are
proxies, may only adjust confidence/uncertainty (and downstream risk/trailing),
and cannot trigger trades. Keeping the no-signal guarantee structural (fields +
tests) makes the rule impossible to bypass accidentally.

## Evidence:
tests/test_orderflow_proxy.py — 10 tests: bullish expansion values, exhaustion,
spread widening, CVD divergence, structure conflict, short-series inconclusive,
and four no-trade-signal guards (is_trade_signal False, no decision fields, no
decision methods, ProxyPressure != Direction). All pass (191 total).

## Alternatives Considered:
- Emitting a LONG/SHORT bias from the proxy: rejected — violates INIT-005;
  pressure is a proxy descriptor only.
- Tick-level (Tick schema) order flow: deferred — candle-based proxies cover the
  P5-001 inputs; tick-level can be added later.

## Risk:
Thresholds (expansion/spread/abnormal factors, aggression cutoffs, adjustment
step/cap) affect outputs; candle-based proxy is coarser than tick-level.

## Mitigation:
All thresholds configurable; adjustments are bounded; OrderFlowProxy exposes raw
metrics for downstream confidence/uncertainty scoring.

## Files Affected:
src/orderflow/proxy.py, src/orderflow/__init__.py, tests/test_orderflow_proxy.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-13

## Date:
2026-06-09

## Area:
Futures Confirmation

## Decision:
The gold futures confirmation layer (P5-002) derives futures directional bias
from futures candles via the P3-001 structure engine and compares it to the spot
thesis bias: ALIGNED -> confidence up; CONFLICT -> confidence down + uncertainty
up; NEUTRAL (either side neutral) -> no change; UNAVAILABLE (missing or
< min_candles) -> zero adjustment + note. By construction futures never triggers
a trade: FuturesConfirmation.is_trade_signal is always False, with no
direction/signal/order field and no decision method.

## Reason:
Enforces INIT-006 and 19_GOLD_FUTURES_CONFIRMATION_POLICY.md: spot is the
execution instrument; futures is context/confidence only and cannot trigger
trades; missing futures data must not crash the core. Reusing the structure
engine keeps the futures read consistent and prefix-stable (no look-ahead).

## Evidence:
tests/test_futures_confirmation.py — 11 tests: aligned (bull/bear) boosts,
conflict reduces + raises uncertainty, neutral futures / neutral spot no change,
missing (None/empty/too-short) -> UNAVAILABLE without crash, and three
no-trade-signal guards. All pass (202 total).

## Alternatives Considered:
- Price-momentum-only futures direction: rejected in favor of the same
  structure-based bias used elsewhere (consistency).
- COT / open-interest inputs: deferred — require dated external releases (COT
  look-ahead ban); can be added later as additional context.

## Risk:
Futures bias depends on swing strength and the structure model; only directional
alignment is used (not magnitude or divergence depth).

## Mitigation:
swing_strength and adjustment caps are configurable; FuturesConfirmation exposes
the component biases and a note for downstream scoring.

## Files Affected:
src/orderflow/futures_confirmation.py, src/orderflow/__init__.py,
tests/test_futures_confirmation.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-14

## Date:
2026-06-09

## Area:
Strategy

## Decision:
The trade hypothesis engine (P6-001) composes analysis context (HypothesisInput)
into a TradeDecision (status PROPOSED). Gates return WAIT/NO_TRADE and never an
invalid actionable decision: htf_bias NO_TRADE -> NO_TRADE; regime in {NO_TRADE,
NEWS_RISK, CHOPPY} -> NO_TRADE; htf_bias NEUTRAL -> WAIT. Direction follows bias
(BULLISH->LONG, BEARISH->SHORT). Hard rules: empty thesis -> NO_TRADE; missing
invalidation -> NO_TRADE; invalidation on the wrong side of entry -> NO_TRADE.
Target logic uses an explicit target if it sits in the trade direction, else a
default risk-reward target (default_rr=2.0); the stop is the invalidation level.

## Reason:
Implements 13_XAUUSD_SMC_PLAYBOOK.md "Valid Trade Hypothesis" and the P6-001 rule
"no thesis = no trade; no invalidation = no trade". Reuses the TradeDecision
schema, which enforces the same invariants structurally, so an invalid actionable
hypothesis cannot be constructed. Hypotheses are proposals only; the risk governor
(P7) decides permission. No look-ahead (composition only).

## Evidence:
tests/test_hypothesis.py — 11 tests: valid long/short, default-RR target,
no-thesis -> NO_TRADE, blank-thesis -> NO_TRADE, no-invalidation -> NO_TRADE,
wrong-side invalidation -> NO_TRADE, neutral bias -> WAIT, NO_TRADE bias,
blocking regimes, and proposed-only status. All pass (213 total).

## Alternatives Considered:
- Wiring the engine directly to every analysis engine: deferred — an orchestrator
  builds HypothesisInput from the engines; the hypothesis engine stays a pure
  composer, which is simpler and fully testable.
- Deriving invalidation from sweep/zone internally: deferred — provided via input
  for now; richer derivation can be added without changing the decision contract.

## Risk:
Quality of hypotheses depends on the upstream context passed in; default RR is a
placeholder until position sizing (P7-002).

## Mitigation:
default_rr is configurable; the TradeDecision schema guards the invariants; risk
governor has final authority.

## Files Affected:
src/strategy/hypothesis.py, src/strategy/__init__.py, tests/test_hypothesis.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-15

## Date:
2026-06-09

## Area:
Strategy

## Decision:
The confidence/uncertainty engine (P6-002) aggregates six component scores
(structure, liquidity, regime, volatility, session, execution_quality, each in
[0,1]) into confidence = clamp(mean + proxy/futures confidence adjustments) and
uncertainty = clamp((1-mean)*0.5 + component-spread*0.5 + proxy/futures
uncertainty adjustments). It recommends BLOCK (uncertainty >= 0.7 or confidence <
0.3), REDUCE (uncertainty >= 0.4), else ALLOW, with a size_factor. The result
always carries authorizes_trade=False and risk_governor_required=True.

## Reason:
Implements 02_ARCHITECTURE.md section 12 and the P6-002 rules: high uncertainty
blocks/reduces; confidence alone cannot bypass risk. Component disagreement
(spread) raises uncertainty so conflicting evidence cannot be masked by a high
mean. Reuses the P5-001/P5-002 adjustment outputs. The engine is eligibility-only
and defers to the Risk Governor (P7) — enforced structurally and by tests.

## Evidence:
tests/test_scoring.py — 10 tests: strong-aligned ALLOW, clamping, out-of-range
rejection, disagreement -> BLOCK via uncertainty, elevated uncertainty -> REDUCE,
proxy+futures conflict raises uncertainty/lowers confidence, low confidence ->
BLOCK, max confidence still requires risk governor, no authorization field, no
authorization method. All pass (223 total).

## Alternatives Considered:
- uncertainty = 1 - confidence: rejected — too coupled; would let a high mean hide
  conflict. Using component spread keeps uncertainty independent and meaningful.
- Letting high confidence override uncertainty/risk: rejected — violates the risk
  policy; scoring never authorizes a trade.

## Risk:
Equal component weights and fixed thresholds are simplifications.

## Mitigation:
Thresholds and reduce_factor are configurable; ConfidenceResult exposes
confidence/uncertainty/size_factor for the risk governor (P7) to use.

## Files Affected:
src/strategy/scoring.py, src/strategy/__init__.py, tests/test_scoring.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-16

## Date:
2026-06-09

## Area:
Risk

## Decision:
The Risk Governor (P7-001) evaluates a TradeDecision against a RiskContext
(BrokerState + spread, lot, intended_risk_pct, loss %, counts, open symbols,
scoring hint) and the RiskLimits (demo profile defaults from INIT-007). It
accumulates every failing check and returns BLOCK if any fails, else REDUCE (when
the scoring size hint < 1) or APPROVE. It never places orders. RiskCheck codes
cover the nine mandatory blocks plus exposure, trades/day, consecutive losses,
non-actionable, and scoring-veto.

## Reason:
Implements 03_RISK_POLICY.md and INIT-003 (risk has final authority). Accumulating
all failures gives complete diagnostics. intended_risk_pct is an input because
position sizing is P7-002; the governor validates it against the per-trade limit.
Confidence/scoring can never bypass a hard block.

## Evidence:
tests/test_risk_governor.py — 19 tests: clean APPROVE, scoring REDUCE/BLOCK, all
nine mandatory blocks (no stop-loss, too much risk, daily/weekly loss, spread too
high, invalid lot, broker unknown, duplicate, wrong symbol), exposure, trades/day,
consecutive losses, non-actionable, accumulated multi-failure, high-confidence
cannot bypass, and no-execution-method guard. All pass (242 total).

## Alternatives Considered:
- Computing position size inside the governor: rejected — sizing is P7-002; the
  governor consumes intended_risk_pct/lot_size and validates them.
- Short-circuiting on the first failure: rejected — accumulating all failures is
  better for diagnostics and audit.

## Risk:
Governor depends on accurate context (loss %, counts, spread, risk %) supplied by
upstream state; max_consecutive_losses is off by default in demo.

## Mitigation:
All limits are configurable via RiskLimits; checks are deterministic and fully
tested; the execution gateway (P7-003) will re-verify before any order.

## Files Affected:
src/risk/governor.py, src/risk/__init__.py, tests/test_risk_governor.py

## Status:
Accepted
