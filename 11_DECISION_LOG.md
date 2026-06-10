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

---

## Decision ID:
2026-06-09-17

## Date:
2026-06-09

## Area:
Risk

## Decision:
Position sizing (P7-002) computes lot = (balance * risk_pct) / (effective_stop *
contract_size), where effective_stop = |entry-stop| + spread + slippage buffer.
The lot is snapped DOWN to lot_step and clamped to max_lot so realized risk never
exceeds target. If the snapped lot is below min_lot the sizer BLOCKS
(STOP_TOO_WIDE) rather than shrinking the stop; a requested risk above the
per-trade limit BLOCKS (RISK_TOO_HIGH). contract_size defaults to 100 (XAU
oz/lot). The sizer never places orders; its lot_size/risk_pct feed the Risk
Governor.

## Reason:
Implements 03_RISK_POLICY.md Position Sizing Rule: size from balance/risk/stop/
contract/buffer, never reduce the stop to grow size, reduce-or-skip when the stop
is too wide. Snapping down and clamping guarantee realized risk <= target.

## Evidence:
tests/test_position_sizing.py — 10 tests: correct lot (0.02 @ 0.5% of 2000, stop
5), snap-down, buffer reduces lot, clamp to max_lot, excessive risk blocked,
stop-too-wide blocked (stop never shrunk), wider-stop-never-increases-lot,
invalid inputs, and a governor-integration APPROVE. All pass (252 total).

## Alternatives Considered:
- Silently capping a too-large requested risk: rejected — blocking is safer and
  explicit (RISK_TOO_HIGH).
- Rounding lot to nearest step: rejected — always floor so realized risk cannot
  exceed the target.

## Risk:
contract_size is broker/symbol dependent; pip/contract specifics for the live
demo symbol must be confirmed against MT5 symbol_info at runtime.

## Mitigation:
contract_size and all lot rules are configurable; the execution gateway (P7-003)
and live adapter can supply broker-accurate values; the Risk Governor re-validates
risk and lot independently.

## Files Affected:
src/risk/position_sizing.py, src/risk/__init__.py, tests/test_position_sizing.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-18

## Date:
2026-06-09

## Area:
Execution

## Decision:
The MT5 demo execution gateway (P7-003) sends an order only after a layered gate:
(1) hard real-money refusal (REAL_FORBIDDEN) if real is requested via
ALLOW_REAL_ORDERS, REAL_TRADING_ENABLED, or TRADING_MODE != DEMO; (2) execution
pre-checks (actionable, XAU symbol, stop-loss present, take-profit/exit present,
broker connected, no duplicate); (3) Risk Governor approval (final authority);
(4) a safe default that does nothing (DRY_RUN) unless demo_send_enabled
(TRADING_MODE=DEMO, REAL_TRADING_ENABLED=false, ALLOW_DEMO_ORDERS=true,
ALLOW_MT5_ORDER_SEND=true, ALLOW_REAL_ORDERS=false). Only then is order_send
called on an injected MT5 client. The order lifecycle is logged in
result.states; the gateway holds and logs no credentials.

## Reason:
Implements 05_EXECUTION_POLICY.md and the CLAUDE.md Trading Safety Rule. Default
ExecutionFlags() send nothing, so accidental sends are impossible without explicit
opt-in. Real money is refused before any work. Execution can never bypass the
risk governor. Dependency injection keeps the gateway testable off-Windows and
lets tests prove order_send is only called in the single allowed case.

## Evidence:
tests/test_execution_gateway.py — 14 tests: demo send when approved+enabled,
state-logged lifecycle, rejected-order logging, default-flags never-send,
real-orders/real-trading/non-demo refusal, wrong-symbol/no-SL/duplicate/risk
blocks (order_send never called), blocked-state logged, and no credentials in
request/result/flags loader. All pass (266 total). grep confirms a single gated
order_send and no credential literals in src/execution.

## Alternatives Considered:
- Sending by default and blocking on flags: rejected — the safe default must be
  no-send; sending requires explicit flags.
- Letting the gateway run analysis/sizing: rejected — the execution layer does
  not think; it validates and sends approved orders only.

## Risk:
Real MT5 retcodes/constants and symbol mapping must be confirmed on the Windows
demo terminal; the fake client approximates them.

## Mitigation:
Constants are read from the injected client via getattr with fallbacks; the live
adapter (src/broker) provides the real client; defaults remain no-send.

## Files Affected:
src/execution/gateway.py, src/execution/__init__.py,
tests/test_execution_gateway.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-19

## Date:
2026-06-09

## Area:
Risk

## Decision:
Stop placement intelligence (P8-001) places the stop beyond the thesis
invalidation by clearance = max(atr * atr_multiple, min_buffer), plus spread,
and pushes it beyond any liquidity pool within clearance. evaluate() rejects a
proposed stop as REJECTED_WRONG_SIDE, REJECTED_NOT_BEYOND_INVALIDATION,
REJECTED_OBVIOUS (on/too near the invalidation or a liquidity pool), or
REJECTED_TOO_TIGHT (distance from entry below the broker/min buffer); otherwise
ACCEPTED. Stop placement only (trailing is P8-002); no order placement.

## Reason:
Implements 17_STOP_AND_TRAILING_POLICY.md "be harder to kill": stops must sit
beyond invalidation with a volatility/liquidity buffer, never on obvious retail
pools and never fear-tight. A computed stop always passes its own evaluation.

## Evidence:
tests/test_stop_placement.py — 14 tests: obvious-on-invalidation and
obvious-on-pool rejected (long & short), logical accepted, wrong-side,
not-beyond-invalidation, too-tight, placement beyond invalidation (long/short),
push-beyond-pool, spread-widens-buffer, decision convenience, and bad-invalidation
guard. All pass (280 total).

## Alternatives Considered:
- Fixed pip buffer only: rejected — volatility (ATR) scaling adapts to gold's
  conditions; min_buffer is the floor.
- Auto-correcting an obvious stop silently: rejected here — placement computes a
  logical stop, evaluation reports the verdict; callers decide (reduce size/skip
  per policy).

## Risk:
ATR and liquidity levels are inputs; broker minimum stop distance is broker
specific.

## Mitigation:
atr_multiple, min_buffer, broker_min_stop are configurable; the live adapter
supplies broker minimums; the Risk Governor independently requires a stop.

## Files Affected:
src/trade_management/stop_placement.py, src/trade_management/__init__.py,
tests/test_stop_placement.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-20

## Date:
2026-06-09

## Area:
Risk

## Decision:
The trailing stop engine (P8-002) updates a stop via STRUCTURE (last swing ∓
buffer), VOLATILITY (price ∓ atr*multiple), LIQUIDITY (cleared level ∓ buffer),
or BREAK_EVEN (entry). Trailing is inactive until profit reaches be_trigger_r
(default 1R) -> no premature trailing. A candidate is applied only if it improves
the stop toward price and is on the correct side of price; it can NEVER widen.
partial_plan() returns take levels [1R, next liquidity beyond 1R] and a
runner_allowed flag (structure valid, no opposite displacement, spread safe).

## Reason:
Implements 17_STOP_AND_TRAILING_POLICY.md: be harder to kill, never widen a stop,
break-even/partials only after confirmation, hold runners only while structure
holds. Confirmation gating and the never-widen rule are the core safety
invariants.

## Evidence:
tests/test_trailing.py — 14 tests: no trailing before confirmation, break-even
only after confirmation, volatility/structure/liquidity trails after
confirmation, no-widening (long & short), candidate-wrong-side ignored, short
volatility trail, partial levels (1R + liquidity, skip liquidity below 1R), and
runner allowed/blocked cases. All pass (294 total).

## Alternatives Considered:
- Allowing trailing immediately from entry: rejected — premature trailing chops
  out winners; gate behind a confirmation R.
- A single fixed trailing method: rejected — structure/volatility/liquidity each
  suit different regimes; the caller selects.

## Risk:
Inputs (last swing, protect level, ATR, be_trigger_r) come from upstream; method
choice affects behavior.

## Mitigation:
atr_multiple, buffer, be_trigger_r are configurable; the never-widen and
confirmation invariants are enforced regardless of inputs; no order placement.

## Files Affected:
src/trade_management/trailing.py, src/trade_management/__init__.py,
tests/test_trailing.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-21

## Date:
2026-06-09

## Area:
Data

## Decision:
The trade journal (P9-001) is an append-only JSON Lines store. Each line wraps a
TradeDecision or TradeRecord (serialized via pydantic model_dump(mode="json"))
with a logged_at_utc timestamp and a kind tag. It logs both trades and no-trade
decisions and is restart-safe: a fresh TradeJournal on the same path reloads all
entries (entries / decisions / records). Only the credential-free schemas are
written. Default path is logs/trade_journal.jsonl (gitignored).

## Reason:
Implements 06_DATA_POLICY.md storage and 05_EXECUTION_POLICY.md TRADE_LOGGED.
JSONL is simple, append-friendly, and restart-safe. Reusing the existing schemas
guarantees round-trip fidelity and that no credentials are ever written.

## Evidence:
tests/test_journal.py — 8 tests: decisions persisted (trade + no-trade),
no-trade logged, record logged, round-trip equality, restart-safe reload, append
across instances, empty-when-absent, and no credentials in the file. All pass
(302 total).

## Alternatives Considered:
- SQLite/database: rejected for now — JSONL meets the restart-safe requirement
  with zero dependencies and is easy to inspect; can migrate later.
- Holding entries only in memory: rejected — not restart-safe.

## Risk:
Concurrent writers could interleave lines; large files reparse on each read.

## Mitigation:
Single-process append is sufficient for demo; a read cache / rotation can be
added later without changing the entry format.

## Files Affected:
src/journal/journal.py, src/journal/__init__.py, tests/test_journal.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-22

## Date:
2026-06-09

## Area:
Adaptation

## Decision:
The reflection engine (P9-002) classifies mistakes mechanically per TradeRecord
(NO_STOP_LOSS, NO_THESIS for executed trades; OVERCONFIDENCE for confidence>=0.7
on a loss; IGNORED_UNCERTAINTY for uncertainty>=0.5 on a loss) and builds a
DailyReview (counts, pnl, win rate, OVERTRADING when executed > max_trades_per_day,
aggregated mistakes, per-record breakdown, summary). NO_TRADE/CANCELLED records
carry no execution mistakes. It is offline only and exposes no
apply/update/mutate/adapt/execute methods.

## Reason:
Implements 02_ARCHITECTURE.md section 18 and the 04_ADAPTATION_POLICY.md
reflection step while honoring INIT-004 (live self-mutation forbidden): reflection
produces a report and never changes policy. Mechanical thresholds keep mistake
labels deterministic and testable.

## Evidence:
tests/test_reflection.py — 13 tests: clean winner, overconfidence, ignored
uncertainty, no-stop, no-thesis, no-trade has none, multi-category, daily review
counts/pnl/win-rate, overtrading flagged / within-limit, summary text, empty
review, and no-mutation-method guard. All pass (315 total).

## Alternatives Considered:
- Auto-adjusting parameters from reflection: rejected — forbidden live
  self-mutation; controlled offline updates are a later, evidence-gated step.
- Detecting missed opportunities / revenge from records alone: deferred — needs
  signal/timing context beyond a single TradeRecord.

## Risk:
Thresholds (overconfidence/uncertainty/max trades) are heuristics.

## Mitigation:
All thresholds are configurable; reflection output is advisory only and never
feeds back into live policy automatically.

## Files Affected:
src/reflection/reflection.py, src/reflection/__init__.py, tests/test_reflection.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-23

## Date:
2026-06-09

## Area:
Testing

## Decision:
The backtesting engine (P10-001) is an event-driven, strictly causal simulator.
The strategy is called with history = candles[:t+1] only (no future bars). A
decision at bar t fills at bar t+1's OPEN with cost = spread + slippage applied
adversely; exits apply slippage; commission_per_lot is optional. Stops/TPs are
checked bar-by-bar from each bar's high/low, and if a bar spans both the STOP is
assumed first (conservative). Lot sizing reuses the P7-002 PositionSizer unless
BacktestConfig.fixed_lot is set; sizing-blocked decisions are skipped. The engine
produces TradeRecords and a BacktestResult and never places real orders.

## Reason:
Implements 07_TEST_POLICY.md backtest requirements and the 06_DATA_POLICY.md
look-ahead ban. Passing only causal slices makes future leakage structurally
impossible; next-bar fills with spread/slippage and stop-first resolution avoid
optimistic results.

## Evidence:
tests/test_backtester.py — 9 tests: next-bar entry with costs, target exit with
slippage, stop-first when a bar spans both, pnl via lot*contract_size, spy
strategy receives exactly candles[:k+1], appending future bars does not change
past trades, end-of-data close, no-trade flat, and PositionSizer-based sizing.
All pass (324 total).

## Alternatives Considered:
- Same-bar (close) fills: rejected — unrealistic and look-ahead-prone; next-bar
  open is realistic.
- Assuming target-first within a bar: rejected — optimistic; stop-first is the
  conservative choice.

## Risk:
Intrabar path is unknown; stop-first is an approximation. Session rules and
trailing are not yet wired into the loop.

## Mitigation:
Conservative stop-first avoids overstating results; the strategy callback can add
session filtering; trailing/StopPlacement can be integrated in a later iteration
without changing the causal/fill model.

## Files Affected:
src/backtest/backtester.py, src/backtest/__init__.py, tests/test_backtester.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-24

## Date:
2026-06-09

## Area:
Testing

## Decision:
Walk-forward validation (P10-002) splits a candle series into ordered folds where
each test window immediately follows its train window (test_start == train_end),
in rolling (sliding train) or anchored (growing train) mode. run() evaluates the
strategy on each unseen test window via the P10-001 Backtester; an optional
optimizer is given the train candles ONLY and returns the strategy for that fold.
Results are aggregated across folds. No order placement.

## Reason:
Implements 07_TEST_POLICY.md walk-forward validation and the 06_DATA_POLICY.md
look-ahead ban: test is always strictly later than train, the optimizer never
sees test data, and the per-fold backtest is causal, so out-of-sample evaluation
has no leakage.

## Evidence:
tests/test_walk_forward.py — 9 tests: rolling and anchored split shapes, custom
step, size validation, test-strictly-after-train, optimizer-sees-only-train,
fold-backtest-equals-standalone-on-test-window, aggregation, and too-short series.
All pass (333 total).

## Alternatives Considered:
- Re-running the backtest over train+test and slicing results: rejected — risks
  leakage and double-counting; backtesting only the test window is cleaner.
- k-fold shuffling: rejected — time series must preserve order; only forward
  splits are valid.

## Risk:
The optimizer hook is a placeholder (real parameter fitting is future work);
fixed window sizes may not suit all regimes.

## Mitigation:
train/test/step and anchored mode are configurable; the optimizer contract
already restricts inputs to train data, ready for a real fitter later.

## Files Affected:
src/backtest/walk_forward.py, src/backtest/__init__.py, tests/test_walk_forward.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-25

## Date:
2026-06-09

## Area:
Execution

## Decision:
Live shadow mode (P11-001) is implemented by ShadowRunner: it consumes
live/replayed candles, calls the strategy with causal slices (candles[:t+1]),
journals every returned decision (including NO_TRADE), and NEVER sends orders. In
pure mode it holds no MT5 client. If an ExecutionGateway is provided it must have
demo_send_enabled == False (the runner raises otherwise) plus a context_builder,
and the gateway is used only to record a dry-run outcome; if any routed result
reported sent=True the runner raises. A read-only `flags` property was added to
ExecutionGateway so the runner can verify sending is disabled.

## Reason:
Implements 05_EXECUTION_POLICY.md live shadow mode and the CLAUDE.md Trading
Safety Rule: live analysis and logging with provably no real (or demo) order
sending. Refusing a sending-enabled gateway makes "no orders sent" a structural
guarantee, not just a convention.

## Evidence:
tests/test_shadow.py — 7 tests: decisions logged (incl. NO_TRADE) and restart-safe,
pure shadow sends nothing, routed gateway never calls order_send (fake client) and
all executions sent=False, runner refuses a sending-enabled gateway, gateway
requires a context_builder. All pass (340 total).

## Alternatives Considered:
- Routing through a demo-sending gateway: rejected — shadow must not send even
  demo orders; only dry-run evaluation is allowed.
- A standalone shadow without the gateway: kept as the default (pure) mode; the
  gateway hook is optional for dry-run records.

## Risk:
A live data source/clock and real strategy wiring are still needed for true live
operation (this provides the safe runner + logging).

## Mitigation:
The runner is data-source agnostic (takes candles); live adapters feed it later;
sending remains impossible by construction.

## Files Affected:
src/execution/shadow.py, src/execution/gateway.py, src/execution/__init__.py,
tests/test_shadow.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-26

## Date:
2026-06-09

## Area:
Execution

## Decision:
The real-mode readiness review (P11-002) is a report generator. ReadinessReview.
review(inputs) evaluates gates (tests passing, backtest/walk-forward/demo/shadow
validated, risk governor present, stop-loss enforced, journal restart-safe, and
real-currently-disabled derived from ExecutionFlags) and returns a ReadinessReport.
Verdict is NOT_READY by default and whenever any gate fails or manual approval is
absent; READY only when all gates pass AND manual_approval is explicitly granted.
The report NEVER authorizes execution: real_execution_allowed is always False and
the review has no execute/order/enable_real method.

## Reason:
Implements the P11-002 stop condition (readiness report only) and the
CLAUDE.md/03_RISK_POLICY.md rule that real-money execution is forbidden without
explicit manual approval. Making real_execution_allowed a constant False and
omitting any execution method keeps "report only" a structural guarantee.

## Evidence:
tests/test_readiness.py — 9 tests: default NOT_READY, single failing gate blocks,
real flags enabled fail the safety gate, all-gates-pass-but-no-approval NOT_READY,
all-gates+approval READY, report never authorizes execution (real_execution_allowed
False even when READY), no execution method, no execution field, summary text.
All pass (349 total). This completes the 10_TASK_QUEUE.md roadmap.

## Alternatives Considered:
- Letting READY enable real trading: rejected — readiness is advisory; enabling
  real is a separate, manual, out-of-scope step.
- A new top-level src/readiness package: rejected — placed in src/reflection
  (review/report concern) to avoid structural churn.

## Risk:
Gate inputs are supplied by the caller; a wrong input could mislabel readiness.

## Mitigation:
Default verdict is NOT_READY; the report never executes; real-money remains gated
behind manual approval and the execution gateway's flags regardless of this report.

## Files Affected:
src/reflection/readiness.py, src/reflection/__init__.py, tests/test_readiness.py

## Status:
Accepted

---

## Decision ID:
INT-001

## Date:
2026-06-09

## Area:
Architecture

## Decision:
A DecisionPipeline (src/strategy/pipeline.py) wires the engines into one flow:
data validation -> session / HTF bias / regime / structure / liquidity / sweeps ->
order-flow proxy + futures -> setup (an aligned confirmed sweep yields thesis +
invalidation) -> confidence scoring -> trade hypothesis -> stop placement ->
position sizing -> Risk Governor. Engines are dependency-injected via
PipelineEngines (defaults = real engines). The pipeline produces a TradeDecision
and a RiskDecision and NEVER executes orders.

## Reason:
Turns the independently-built and tested engines into a usable end-to-end decision
flow while preserving every safety boundary: the Risk Governor remains final
authority, scoring cannot bypass risk, and execution stays the separately gated
ExecutionGateway's job. DI keeps every stage testable/swappable. This is an
integration milestone, not a queued task (roadmap P0..P11 already complete).

## Evidence:
tests/test_pipeline.py — 7 tests: data-rejected short-circuit, flat market ->
non-actionable, full LONG setup approved (stub bias/regime/structure/sweep),
disconnected broker blocks, news-risk blocks, no execution method, and
high-risk-blocked-by-governor. All pass (356 total).

## Alternatives Considered:
- Hardcoding the real engines without injection: rejected — DI makes the full
  approve path deterministically testable and lets the live runner swap stages.
- Having the pipeline place orders: rejected — orchestration must not execute;
  the gated ExecutionGateway / ShadowRunner own that.

## Risk:
Component-score mapping is heuristic; the setup finder currently keys off
confirmed sweeps only; a live data adapter is still needed to feed it.

## Mitigation:
Heuristics are documented and isolated in _score_components; engines remain
swappable; downstream still defers to the Risk Governor and the gated gateway.

## Files Affected:
src/strategy/pipeline.py, src/strategy/__init__.py, tests/test_pipeline.py

## Status:
Accepted

---

## Decision ID:
PHASE12-001

## Date:
2026-06-09

## Area:
Live Demo Readiness / Risk / Execution

## Decision:
After P0-P11 and INT-001, the next phase is Phase 12: Live Demo Readiness.

## Reason:
The architecture and pipeline are implemented, but real MT5 demo connectivity, live shadow behavior, leverage-aware sizing, protected pyramiding, and supervised demo execution still require controlled validation.

## Risk:
Starting demo trading without these gates could create unsafe order behavior, over-risking, credential exposure, or false confidence.

## Mitigation:
Use staged gates: RISK-001, LIVE-VERIFY-001, WINMT5-001, LIVE-001, LIVE-002, DEMO-001, DEMO-002.

## Status:
Accepted

---

## Decision ID:
RISK-001

## Date:
2026-06-09

## Area:
Risk

## Decision:
Leverage-aware, confidence-tiered sizing (src/risk/leverage_sizing.py) and a
protected-pyramiding guard (src/risk/pyramiding.py) are added as NEW modules
alongside the stable P7-002 PositionSizer and P7-001 RiskGovernor (no rewrite of
those files). LeverageAwareSizer derives the lot from a dollar MAX-LOSS cap and
the STRUCTURAL stop distance (loss_per_lot = stop/tick_size * tick_value).
Leverage changes only margin_required, never the loss at stop, so leverage/margin
can only BLOCK (insufficient margin) and never enlarge the lot. Demo caps come
from a confidence tier table (NORMAL $40 / HIGH_CONFLUENCE $80 / ELITE $100);
real mode never inherits demo tiers (cap = balance * real_risk_pct, default
0.5%). Fixed lots (0.01/0.05/0.10) are assessed against the same cap and blocked
if their implied loss exceeds it. PyramidingGuard permits a same-direction add-on
only when every existing same-direction position is protected at break-even or
locked profit AND not in loss, the add-on carries its own thesis/invalidation/
stop/entry, a fresh setup and continuation are confirmed, and total combined
lots/dollar-risk stay within PyramidLimits. Neither component places orders; both
defer to the Risk Governor.

## Reason:
Implements 20_LEVERAGE_AND_PYRAMIDING_POLICY.md and the RISK-001 required
behavior: stop from structure, lot from allowed risk, fixed lots never bypass
the cap, leverage/margin never bypass max-loss, add to winners only, never to
losers, total exposure capped, real risk conservative. Building new modules keeps
the proven P7 sizing/governor untouched (Scope Rule) while the orchestrator can
adopt the leverage-aware path for demo.

## Evidence:
tests/test_leverage_sizing.py (19) — 0.01/0.05/0.10 lot scenarios, tier scaling,
snap-down within cap, stop-too-wide block, leverage does not increase lot/loss,
insufficient-margin block without resize, fixed-lot within/over cap, fixed-lot
leverage-cannot-bypass, real-mode conservative cap, and no order method.
tests/test_pyramiding.py (12) — allow into protected winner, block when not
protected, block adding to a loser (long & short), fresh-setup / continuation /
existing-trade / direction-mismatch / missing-risk-plan guards, total lot and
dollar exposure caps, BE zero-open-risk allow, and no order method. Full suite:
387 passed.

## Alternatives Considered:
- Extending PositionSizer/RiskGovernor in place: rejected — would rewrite stable,
  fully-tested files without need (Scope Rule); new modules are additive.
- Sizing from free margin / leverage headroom: rejected — violates the core rule;
  margin is a feasibility check only and can never grow the lot.
- Letting real mode reuse demo tier caps: rejected — real risk must stay
  conservative and tier-independent (INIT-008 / policy "Real Risk Separation").

## Risk:
SymbolSpec defaults (contract 100, tick 0.01 = $1) and PyramidLimits caps are
broker/account dependent; the open-risk proxy uses contract_size on OpenTrade.

## Mitigation:
SymbolSpec, DemoTierTable, real_risk_pct, and PyramidLimits are all configurable;
runtime values are confirmed against MT5 symbol_info (WINMT5-001) before any demo
order; the Risk Governor re-validates risk/lot independently and keeps final
authority; no orders are placed by these modules.

## Files Affected:
src/risk/leverage_sizing.py, src/risk/pyramiding.py, src/risk/__init__.py,
tests/test_leverage_sizing.py, tests/test_pyramiding.py

## Status:
Accepted

---

## Decision ID:
LIVE-VERIFY-001

## Date:
2026-06-09

## Area:
Testing / Execution

## Decision:
The implementation evidence pack (LIVE-VERIFY-001) is produced by a read-only
generator script, scripts/generate_evidence_pack.py, not by hand. It performs
filesystem introspection only (it does NOT import or execute src modules, never
calls order_send, never trades, never reads/prints credentials). It discovers
every non-trivial src module, joins each to a curated classification (layer,
summary, tested-by, external-mock boundary, live-proven, shadow-ready,
demo-order-ready, needs-Windows-MT5), auto-counts test functions per mapped test
file (deduped for the total), and renders reports/runtime/evidence_pack.md +
.json. build_evidence() RAISES if any discovered module is unclassified, so the
report can never silently omit a module. By policy the table hard-codes
live_proven=False for all modules (WINMT5-001 not run) and ready_for_demo_order=
False for all modules (DEMO-001 gates not passed). The evidence output is written
under reports/runtime/, which is git-ignored; the committed deliverable is the
generator + its test + doc updates, and the artifact is regenerated on demand.

## Reason:
A generator keeps the evidence pack honest, deterministic, and refreshable as the
codebase evolves, rather than a stale hand-written snapshot. Read-only
introspection (no imports/execution) guarantees the report itself cannot trade or
touch the broker. Treating reports/runtime/ as a runtime artifact matches the
existing .gitignore policy (like logs/), avoiding a forced override of project
config. Hard-coding the two safety invariants (no live-proven, no demo-order-ready)
makes the report structurally unable to over-claim readiness.

## Evidence:
tests/test_evidence_pack.py — 8 tests: every src module classified (report set ==
discovered set), all implemented, live_proven total == 0, ready_for_demo_order
total == 0, MT5-boundary modules need Windows validation + external-mock, core
modules have positive test counts, all required markdown sections render, and the
generator contains no order_send call / no real-trading enablement. Full suite:
395 passed. Generated pack: 34 modules, 368 test functions across 30 mapped test
files, 5 modules requiring WINMT5-001, 0 live-proven, 0 demo-order-ready.

## Alternatives Considered:
- Hand-writing a static markdown report: rejected — goes stale and is unverifiable;
  a tested generator stays accurate.
- Importing src modules to introspect them: rejected — unnecessary and risks
  side effects; filesystem introspection is sufficient and provably inert.
- Force-committing the artifact into git-ignored reports/runtime/: rejected — would
  override project .gitignore policy without evidence; commit the generator instead.

## Risk:
The classification table is curated judgment; if a new src module is added it must
be classified or the generator (and its test) will fail.

## Mitigation:
That failure is intentional and surfaced by build_evidence() + the coverage test,
forcing the table to stay complete and honest as the code grows.

## Files Affected:
scripts/generate_evidence_pack.py, tests/test_evidence_pack.py
(output: reports/runtime/evidence_pack.md + .json — git-ignored runtime artifact)

## Status:
Accepted

---

## Decision ID:
WINMT5-001

## Date:
2026-06-09

## Area:
Broker / Execution

## Decision:
MT5 demo connectivity validation (WINMT5-001) is split into (a) a reusable,
read-only validator src/broker/connectivity.py (MT5ConnectivityValidator) that
runs the 10 required proofs against an INJECTED MT5 client, and (b) a Windows-side
runner scripts/winmt5_validate.py that loads .env safely, classifies the host
environment, and either runs the validator (MetaTrader5 available) or writes an
honest ENVIRONMENT_ISSUE report (MetaTrader5 not importable, e.g. WSL/Linux). The
validator reuses the existing read-only MT5DataAdapter for init/login/candles,
verifies the account is demo/contest (REAL is refused), reads symbol_info and
spread, and NEVER references any trade function (no order_send). It records only
non-secret facts; the account login number is never written to the report. The
runner loads .env via python-dotenv if present else a builtin KEY=VALUE parser,
never printing any value, and reports missing variables by NAME only. Output goes
to reports/runtime/winmt5_validation.md + .json (git-ignored). On this WSL host the
runner produced outcome ENVIRONMENT_ISSUE; the LIVE proof (checks 3-9) remains
PENDING a Windows MT5 host and is NOT marked complete (22_MT5_WINDOWS_VALIDATION.md
"validation is not complete until real demo terminal data is proven").

## Reason:
MetaTrader5 is Windows-only; dependency injection keeps the validator testable on
Linux and lets tests prove no order function is ever called, while the runner
honestly classifies the environment instead of faking live results (the explicit
ban in 22_MT5_WINDOWS_VALIDATION.md). Reusing MT5DataAdapter avoids duplicating
connection logic and inherits its no-order guarantee. Splitting validator (src)
from runner/IO (scripts) keeps the proof logic unit-testable and the IO thin.

## Evidence:
tests/test_winmt5_connectivity.py — 13 tests: full validation PASS (all 10
checks), order_send/order_check never called, REAL account refused, CONTEST
accepted, missing symbol -> FAIL + symbol_info SKIPPED, connect failure skips
dependent checks, report contains no password and no login number, and runner
environment classification (ENVIRONMENT_ISSUE on a no-MT5 host, honest skips of
checks 3-9, missing-credential names, markdown sections, no order_send in source).
Full suite: 408 passed. Live runner output on WSL: outcome ENVIRONMENT_ISSUE.

## Alternatives Considered:
- Hard-importing MetaTrader5 in the validator: rejected — breaks import/tests off
  Windows; injection + lazy import in the runner is testable and safe.
- Marking WINMT5-001 live-proven from the WSL run: rejected — would fake live
  validation; the WSL outcome is explicitly ENVIRONMENT_ISSUE, live proof pending.
- Putting the runner's IO logic in src: rejected — src stays pure/testable; the
  thin IO + env classification lives in scripts/.

## Risk:
The validator's account/symbol field reads assume MT5 named-tuple shapes; real
terminal field names/retcodes are only confirmed on the Windows host. Live proof
is still outstanding.

## Mitigation:
Field access is defensive (attr-or-mapping with fallbacks); the runner records the
real environment outcome and a bridge plan; the live proof is tracked as a
carry-forward blocker in CURRENT_STATE.md / 12_HANDOFF.md until run on Windows.

## Files Affected:
src/broker/connectivity.py, src/broker/__init__.py, scripts/winmt5_validate.py,
scripts/winmt5_runner_README.md, tests/test_winmt5_connectivity.py,
scripts/generate_evidence_pack.py (classify the new module)
(output: reports/runtime/winmt5_validation.md + .json — git-ignored runtime artifact)

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
Broker symbol names from MT5_SYMBOL are passed to MT5 API calls (symbol_select,
symbol_info, copy_rates_from_pos, symbol_info_tick) with their EXACT case
preserved. Uppercasing is used only for canonical XAU/USD validation and for
case-insensitive symbol comparison — never for an actual MT5 API argument.

## Reason:
WINMT5-LIVE-001 surfaced a real bug: Exness uses the case-sensitive symbol
"XAUUSDm". The loader uppercased it to "XAUUSDM", which the terminal does not
recognize, so symbol detection failed. MT5 symbol names are case-sensitive at
the broker, so the exact case must reach every API call.

## Evidence:
tests/test_mt5_data_adapter.py — settings preserve "XAUUSDm" (canonical_symbol
== "XAUUSDM"); fetch_candles calls symbol_select/copy_rates_from_pos with
"XAUUSDm"; a canonical-case caller ("XAUUSDM") still drives MT5 with "XAUUSDm".
tests/test_winmt5_connectivity.py — validator drives symbol_select/symbol_info/
symbol_info_tick/copy_rates_from_pos with "XAUUSDm" and report.symbol == "XAUUSDm".
Full suite: 412 passed.

## Alternatives Considered:
- Keep uppercasing the symbol everywhere: rejected — that is the bug; it breaks
  case-sensitive brokers like Exness.
- Also preserve case in the Candle.symbol data field: rejected — the schema
  canonicalizes symbols to uppercase as the internal representation; that field
  is never used as an MT5 API argument, so it is left unchanged (out of scope).

## Risk:
Downstream code that builds an MT5 API argument from a canonical (uppercased)
symbol string instead of MT5Settings.symbol could reintroduce the mismatch.

## Mitigation:
The adapter's _resolve_symbol always returns MT5Settings.symbol (exact case) for
API calls; MT5Settings.canonical_symbol is documented as validation-only; tests
assert the exact broker case reaches every read-only MT5 call.

## Files Affected:
src/broker/mt5_settings.py, src/broker/mt5_data_adapter.py,
scripts/winmt5_validate.py, tests/test_mt5_data_adapter.py,
tests/test_winmt5_connectivity.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-02

## Date:
2026-06-09

## Area:
Execution / Data

## Decision:
LIVE-001 wires live read-only MT5 demo data into DecisionPipeline and
ShadowRunner via a new LiveShadowSession. The live pipeline is built by
make_live_pipeline, which (a) disables candle gap detection and adds a
30-minute staleness gate in the DataValidator, and (b) configures the
RiskGovernor with the CANONICAL broker symbol (XAUUSDM for Exness XAUUSDm) and
a price-unit max_spread of 1.0. The runner script requires a mandatory stop
condition (--cycles or --duration-minutes) and verifies the account is
demo/non-real before any cycle.

## Reason:
Default engine configs block live data: gap detection treats normal XAU
session/trading-break gaps as BLOCKING MISSING_CANDLES (the validator's own
docstring defers session gaps to the session engine), and the governor's
default expected_symbol XAUUSD rejects canonicalized XAUUSDM decisions.
Without these two fixes every live cycle would be DATA_REJECTED or
risk-blocked WRONG_SYMBOL. The staleness gate replaces gap detection as the
liveness defence: a frozen feed yields an honest NO_TRADE. max_spread=1.0 in
price units is stricter than the points-oriented default of 50 (live spread is
fed as ask-bid in price terms).

## Evidence:
tests/test_live_shadow.py — 13 tests: cycles journal every decision; session-
gapped data accepted; stale feed -> DATA_REJECTED journaled as NO_TRADE; exact
XAUUSDm case in every MT5 call; live spread read; no order_send across full
session; sending-enabled gateway refused; unbounded run refused; report and
journal credential-free; runner refuses REAL account, accepts DEMO/CONTEST;
honest ENVIRONMENT_ISSUE off-Windows. Adapter tests for fetch_tick /
fetch_broker_state (read-only, credential-free). Full suite: 431 passed.
pre_demo_safety_check.sh passed. WSL smoke run: ENVIRONMENT_ISSUE, exit 2.

## Alternatives Considered:
- Feeding spread in broker points to match the governor default: rejected —
  the pipeline and sizer consume price-unit spread; converting at the governor
  boundary invites unit bugs.
- Keeping detect_gaps=True with a session-aware whitelist: rejected — the
  validator explicitly scopes session gaps to the session engine; a whitelist
  duplicates that logic.
- Letting LiveShadowSession run unbounded with external kill: rejected — a
  mandatory stop condition is a hard safety property.

## Risk:
Disabling gap detection could mask a genuinely broken feed that delivers
sparse candles.

## Mitigation:
The 30-minute max_staleness gate rejects a frozen/stale feed; duplicate,
non-monotonic, bad-OHLC, and symbol-mismatch checks remain BLOCKING; every
rejection is journaled as an explicit NO_TRADE.

## Files Affected:
src/broker/mt5_data_adapter.py, src/execution/live_shadow.py,
src/execution/__init__.py, scripts/live_shadow_run.py,
scripts/generate_evidence_pack.py, tests/test_live_shadow.py,
tests/test_mt5_data_adapter.py

## Status:
Accepted

---

## Decision ID:
2026-06-09-03

## Date:
2026-06-09

## Area:
Execution

## Decision:
LIVE-002 supervised live shadow sessions reuse the LIVE-001 runner rather than
a second script. LiveCycleResult now carries confidence, uncertainty, and the
Risk Governor's action + reasons, so the journal AND the session report record
the full decision evidence. The supervised session writes its own artifact via
--report-name live_shadow_session. The session itself is run manually by the
user on the Windows MT5 host; Claude does not run live sessions.

## Reason:
LIVE-002 requires logging decisions, no-trade reasons, confidence, uncertainty,
and risk decisions. The cycle results previously dropped the scoring and risk
verdicts. One runner with a report-name parameter avoids duplicated safety
logic (demo-account verification, stop conditions, no-send guards).

## Evidence:
tests/test_live_shadow.py — cycles carry confidence/uncertainty in [0,1];
DATA_REJECTED cycles have no scores but always a reason; report dict includes
all evidence fields; full suite 434 passed; pre_demo_safety_check.sh passed.

## Alternatives Considered:
- A separate LIVE-002 script: rejected — duplicates safety gates.
- Logging evidence only in the journal: rejected — the session report is the
  reviewable artifact for the supervised run.

## Risk:
None new; the report stays credential-free (tested).

## Mitigation:
Credential-scan tests cover report payload and journal content.

## Files Affected:
src/execution/live_shadow.py, scripts/live_shadow_run.py,
tests/test_live_shadow.py

## Status:
Accepted

---

## Decision ID:
2026-06-10-01

## Date:
2026-06-10

## Area:
Execution / Risk

## Decision:
DEMO-001 preflight verifies 12 gates without placing any order: the 5 demo env
flags, demo/non-real account, exact-case broker symbol on the terminal, Risk
Governor blocking a no-stop-loss probe, ExecutionGateway stop-loss enforcement,
journal writability, restart-safe state persistence, and a manual kill switch.
The kill switch is a file at control/KILL_SWITCH (engage = create, release =
delete) and is wired into ExecutionGateway as a BLOCKING check evaluated before
pre-checks and the order path. SKIPPED gates (no MT5 client on the host) block
readiness — preflight can only pass on the Windows MT5 host. Additionally a
.gitignore defect was fixed: the `!logs/` negation re-included the entire logs
directory, so runtime journals were NOT actually git-ignored; now `logs/*` +
`!logs/.gitkeep` (same fix for data/ dirs), and `control/` is ignored.

## Reason:
DEMO-002 requires a manual kill switch; none existed. A file-based switch works
from any terminal on the host without touching the running process, and wiring
it into the gateway makes it effective at the only order pathway. Functional
probes (no-SL decision blocked by governor AND gateway) prove the safety rules
are active rather than merely configured. The .gitignore fix prevents runtime
journals (which include decision histories) from being accidentally committed.

## Evidence:
tests/test_demo_preflight.py — 17 tests: all gates PASS in a ready demo env;
each wrong env flag fails its gate; REAL account fails; CONTEST accepted;
missing symbol fails; exact XAUUSDm case used; no client -> SKIPPED gates block
readiness; kill switch engage/release cycle; gateway blocks while engaged;
preflight leaves a user-engaged switch untouched; report credential-free;
journal probe round-trips; order_send/order_check never called. Existing
gateway/shadow tests unaffected. Full suite: 451 passed.
pre_demo_safety_check.sh passed. WSL preflight run: Ready False, exit 2.

## Alternatives Considered:
- Env-var kill switch: rejected — cannot be flipped for an already-running
  process from another terminal.
- Treating SKIPPED MT5 gates as PASS off-Windows: rejected — would fake
  readiness; preflight must only pass against the real terminal.
- Leaving the kill switch out of the gateway (runbook-only): rejected — a
  halt that the order pathway does not enforce is not a halt.

## Risk:
The kill-switch file could be deleted accidentally, silently re-enabling
sending in a future DEMO-002 session.

## Mitigation:
DEMO-002 will require the supervised operator to verify kill-switch state at
session start (runbook); the gateway still enforces governor approval,
stop-loss, and all demo flags independently of the switch.

## Files Affected:
src/execution/kill_switch.py, src/execution/preflight.py,
src/execution/gateway.py, src/execution/__init__.py,
scripts/demo_preflight.py, scripts/generate_evidence_pack.py,
tests/test_demo_preflight.py, .gitignore

## Status:
Accepted

---

## Decision ID:
2026-06-10-02

## Date:
2026-06-10

## Area:
Risk / Strategy / Architecture

## Decision:
AUDIT-001: full intelligence audit recorded in 24_INTELLIGENCE_AUDIT_ROADMAP.md
with classified findings and a DEMO-002 / real-money gate map. Two
High-Confidence Defects fixed immediately: (1) the Risk Governor's loss-limit
inputs (daily/weekly loss, trades today, consecutive losses, open symbols)
were permanently zero in the live loop — a new journal-driven RiskStateTracker
now computes them from TradeRecords and LiveShadowSession feeds them into
every PipelineInput; (2) execution-quality scoring divided spread by a
hard-coded 50 (points scale) while the live loop supplies price-unit spread —
DecisionPipeline now takes max_spread (default 50 preserves existing
behavior) and make_live_pipeline passes its price-unit governor limit (1.0).

## Reason:
03_RISK_POLICY mandates trading stops at daily/weekly/consecutive-loss limits;
checks existed but their inputs were never computed, so the rules were dead in
the live/demo path. The spread unit mismatch made execution quality a constant
~0.996 live, silencing a gold-critical confidence input (spread widening at
rollover/news). Both fixes tighten behavior; neither can loosen any limit.

## Evidence:
tests/test_risk_state_tracker.py — 9 tests (daily/weekly windows, win does not
offset losses, streak break/reset, open symbols, unknown-balance safety,
restart-safe from disk, naive-now rejected). test_live_shadow.py — journaled
losses flow into PipelineInput (2 x -20 on $2000 -> 2% daily/weekly, streak 2);
price-unit quality scale (0.5 spread -> 0.5 quality live vs 0.99 default).
Full suite: 463 passed. pre_demo_safety_check.sh passed.

## Alternatives Considered:
- Computing loss state inside the governor: rejected — the governor is a pure
  evaluator; history derivation belongs to a tracker over the journal.
- Tracking net P&L (wins offsetting losses) for the daily cap: rejected — the
  policy caps LOSS, and netting would let a streak ride behind early wins.
- Converting live spread to points to fit the old scale: rejected — price
  units are the native unit of the live loop and the governor limit.

## Risk:
The tracker reads the same journal the session writes; a corrupted journal
line would raise during snapshot and halt the cycle.

## Mitigation:
Halting on corrupted state is the intended fail-closed behavior
(08_ERROR_POLICY); journal entries are schema-validated on read.

## Files Affected:
24_INTELLIGENCE_AUDIT_ROADMAP.md, src/risk/state_tracker.py,
src/risk/__init__.py, src/execution/live_shadow.py, src/strategy/pipeline.py,
scripts/generate_evidence_pack.py, tests/test_risk_state_tracker.py,
tests/test_live_shadow.py

## Status:
Accepted

---

## Decision ID:
2026-06-10-03

## Date:
2026-06-10

## Area:
Risk / Execution

## Decision:
(1) Windows validation proof recorded: live_shadow_run (5 cycles) COMPLETED,
live_shadow_session (5 minutes) COMPLETED, demo_preflight Ready: True — run
manually by the user in PowerShell on the Windows MT5 host. LIVE-001/LIVE-002/
DEMO-001 Windows proof is cleared.
(2) DEMO-002 blockers F-3/F-4/F-5 implemented as one demo execution path:
DemoTradePlanner (tier -> LeverageAwareSizer -> PyramidingGuard ->
RiskGovernor), PositionReconciler + PositionProtectionManager + read-only
fetch_positions, and NewsRiskGuard (manual block file + static calendar,
fail-closed on unknown).
(3) Policy contradiction resolved tightest-rule-wins: 03_RISK_POLICY demo
profile (0.50%/trade, max 1 open trade) vs 20_LEVERAGE_AND_PYRAMIDING_POLICY
(tier caps $40/80/100, protected add-ons). The planner clamps the tier cap to
the governor per-trade budget (cap = min(tier cap, balance * 0.005)) via a
tightening-only hard_cap parameter on LeverageAwareSizer, and permits a second
position ONLY as a PyramidingGuard-approved protected add-on through a new
explicit RiskContext.protected_addon flag (default False) honored by the
governor's duplicate check while open positions stay below max_open_trades
(planner config: 2). A plain duplicate entry remains blocked; a third position
is never planned. If the user wants tier caps to govern fully, 03 must be
amended first — code will not weaken policy on its own.
(4) News policy: no calendar feed exists and none is faked. NewsRiskGuard
reports UNKNOWN without a source and the planner blocks; an empty calendar
file is an explicit operator all-clear; a malformed calendar reads as unknown.

## Reason:
The governor's duplicate check unconditionally blocked any same-symbol second
position, making protected pyramiding structurally impossible; the fix is an
explicit, auditable permission (guard ALLOW + flag + open-count headroom), not
a bypass. The 03-vs-20 contradiction would otherwise surface at runtime as
either permanent blocks or silent policy violation.

## Evidence:
tests/test_demo_planner.py (21), tests/test_positions.py (15),
tests/test_news_guard.py (11), extended governor/sizer behavior covered via
planner tests: governor-clamped cap sizes 0.08 lot at $9.60 implied loss on
$2000; tier cap binds on a $100k account; wide stop blocks instead of
shrinking; margin blocks but never enlarges; add-on into protected winner
allowed; unprotected/losing/no-fresh-setup add-ons blocked; third position
never; duplicate without guard approval blocked by governor; orphans block;
unknown/active news blocks; kill switch blocks an approved plan at the
gateway; planner source never references order_send. Full suite: 510 passed.
pre_demo_safety_check.sh passed.

## Alternatives Considered:
- Passing empty open_symbols to the governor for add-ons: rejected — lying to
  the final authority is a bypass.
- Letting tier caps govern outright: rejected — would weaken 03_RISK_POLICY
  without user approval.
- Skipping news handling until a feed exists: rejected — 14_SESSION policy
  requires blocking news windows; fail-closed unknown is the honest minimum.

## Risk:
The protected_addon flag could be set by future code without a real guard
approval.

## Mitigation:
The flag defaults False; the planner sets it only from a PyramidResult.allowed;
governor tests pin the default-blocked behavior; DEMO-002 review must check
any new setter of protected_addon.

## Files Affected:
src/execution/demo_planner.py, src/execution/positions.py,
src/execution/__init__.py, src/risk/news_guard.py, src/risk/governor.py,
src/risk/leverage_sizing.py, src/risk/__init__.py,
src/trade_management/position_manager.py, src/trade_management/__init__.py,
src/broker/mt5_data_adapter.py, src/broker/__init__.py,
src/execution/live_shadow.py, scripts/generate_evidence_pack.py,
24_INTELLIGENCE_AUDIT_ROADMAP.md, tests/test_demo_planner.py,
tests/test_positions.py, tests/test_news_guard.py

## Status:
Accepted

---

## Decision ID:
2026-06-10-04

## Date:
2026-06-10

## Area:
Execution / Risk / Architecture

## Decision:
DEMO-002 implemented: SupervisedDemoSession + scripts/demo_session_run.py.
Key design decisions:
(a) Hard preconditions at construction: exact confirmation token
    ("START SUPERVISED DEMO"), a READY DemoPreflight produced fresh on the
    same run, and a gateway that does not request real mode.
(b) Preflight gained gate 13 (news_source_available): a missing/unparseable
    news source fails preflight, so the fail-closed news rule is caught
    before the session, not during it.
(c) Stop management goes exclusively through a new gateway.modify_stop
    (TRADE_ACTION_SLTP): real refused, kill-switch aware, never widens,
    never removes; with sending disabled it is a DRY_RUN.
(d) Close detection: journal OPEN records whose broker position vanished are
    closed with realized P&L from history_deals_get (profit+commission+swap);
    unknown P&L keeps the record OPEN -> reconciliation fails closed.
(e) Journal lifecycle semantics: append-only streams collapse to the LATEST
    record per record_id (collapse_records) in the risk tracker and the
    reconciler — without this, the first closed trade would poison
    open_symbols and block trading forever.
(f) Gateway duplicate pre-check now honors RiskContext.protected_addon, so a
    guard-approved add-on can pass the gateway while a plain duplicate stays
    blocked (the governor re-checks independently).
(g) Sizing reduction applied exactly once: the session passes
    size_factor_hint=1.0 to the gateway context because the planner's lot
    already encodes the confidence tier; the gateway also snaps volume DOWN
    to the broker lot step so a factor can never produce an unaligned or
    enlarged volume.
(h) Session ceilings: max_orders (default 1) and an 8-hour hard duration cap.

## Reason:
The session loop is the last component before demo order_send. The integration
defects (e)(f) would have deadlocked or blocked the very first session; (d) is
required for loss limits to operate on real losses; (c) keeps every order-side
effect inside the single gated pathway.

## Evidence:
tests/test_demo_session.py — 18 tests covering: preflight/confirmation/real
refusals; full entry path (order_send called once, stop attached, ticket
journaled); max_orders; kill-switch halt; unknown news and orphan positions
block entries; no averaging down; journaled daily loss blocks entries via the
governor; close detection journals real P&L and reconciliation stays clean;
unknown close P&L is a violation and fails closed; break-even applied via
TRADE_ACTION_SLTP with exact symbol case; modify_stop never widens/removes and
respects the kill switch; dry-run never calls order_send; report credential-
free. Updated preflight tests (13 gates). Full suite: 529 passed.
pre_demo_safety_check.sh passed. WSL runner refusals exit 2.

## Alternatives Considered:
- Reusing ShadowRunner inside the demo session: rejected — shadow's no-send
  guard contradicts a sending session; a dedicated loop with its own
  fail-closed gates is clearer.
- Treating a vanished position as WIN/LOSS by last seen profit: rejected —
  dishonest; deal history is the source of truth, unknown stays OPEN.
- Rewriting journal lines in place for closes: rejected — the journal is
  append-only by design (restart-safe); collapse semantics preserve that.

## Risk:
The close-detection path depends on history_deals_get availability on the
Windows terminal; if history is disabled, every close becomes a violation and
the session stops trading (fail-closed but noisy).

## Mitigation:
First run is supervised with max ONE order; the operator reviews the session
report; the dry-run rehearses the full loop including close detection paths.

## Files Affected:
src/execution/demo_session.py, scripts/demo_session_run.py,
src/execution/gateway.py, src/execution/positions.py,
src/execution/preflight.py, src/risk/state_tracker.py,
src/broker/mt5_data_adapter.py, src/execution/__init__.py,
scripts/generate_evidence_pack.py, tests/test_demo_session.py,
tests/test_demo_preflight.py

## Status:
Accepted

---

## Decision ID:
2026-06-10-05

## Date:
2026-06-10

## Area:
Execution / Risk / Reflection / Architecture

## Decision:
DEMO-EVAL: the supervised demo session is now a serious, policy-governed
evaluation engine; the one-order session cap is demoted to an optional
smoke-test parameter.

(a) Session risk profiles (src/execution/session_profiles.py): smoke /
    evaluation / london / newyork / full_day. A profile configures duration,
    polling, session order cap, and the RiskLimits handed to the governor and
    planner. Construction-time validation guarantees a profile can TIGHTEN
    the 03_RISK_POLICY demo limits but never loosen them, so configurability
    cannot become a risk bypass.
(b) max_orders is now Optional: None (the serious-evaluation default) means
    NO artificial per-session cap — order count is governed by the risk
    policy (3 trades/day, 2% daily / 5% weekly loss, single position plus at
    most one protected add-on), confidence tiers, regime, and setup quality.
    max_orders=1 survives only in the smoke profile.
(c) Dry-run defect fixed: the runner previously forced max_orders=0, which
    blocked the entry path BEFORE the planner — a dry run never rehearsed
    the path it claimed to validate. Dry-run now keeps the profile limits;
    approved plans flow planner -> gateway, are counted as orders_simulated
    (ORDER_SIMULATED events), count against the session cap exactly like
    real sends, and never reach order_send (flags stay disabled).
(d) Mode separation is explicit and never mixed: DEMO_LIVE (real MT5 demo
    orders, tickets journaled) vs DRY_RUN (simulated approvals) in the
    session report; shadow analysis remains LiveShadowSession. The
    evaluation report separates trades_real / trades_simulated / decisions.
(e) Per-cycle CycleStats (regime, session, HTF bias, confidence, spread,
    news state, risk action, entry action) are recorded in the session
    report as the evidence base for post-session analysis.
(f) Post-session intelligence (src/reflection/demo_evaluation.py +
    scripts/demo_eval_report.py + scripts/demo_reflection.py): evaluation
    report (totals, distributions, no-trade reasons, news/risk blocks,
    realized P&L, max drawdown, win/loss, mistakes) with findings classified
    as PROVEN_DEFECT / HIGH_CONFIDENCE_DEFECT / HYPOTHESIS / OBSERVATION /
    DESIGN_IMPROVEMENT, and a reflection report (did well / too strict /
    too loose / missed opportunities / avoided correctly / backtest-first /
    fix-now). Both are offline file readers; no live self-mutation. Untaken
    trades are honestly HYPOTHESIS (no hindsight data), routed to "backtest
    before changing".
(g) Demo-to-real path stays configuration-shaped: the same session, planner,
    gateway, journal, reconciliation, and stop management run in every mode;
    real mode remains refused at construction/gateway/flags and would later
    arrive via approved configuration + readiness gates, not a rewrite.

## Reason:
The first supervised run was designed around max ONE order, which is correct
as a first-evidence step but useless for evaluating real demo performance.
The evaluation engine must produce statistically meaningful sessions while
keeping every risk rule intact — the cap moves into configuration, the risk
policy stays the authority.

## Evidence:
tests/test_session_profiles.py (12): registry, policy-bound construction and
overrides, smoke-only cap. tests/test_demo_evaluation.py (10): totals,
distributions, P&L/win-rate/max-drawdown, mode separation, classification
correctness, untradeable-market recognition, cap-too-strict surfacing,
hypothesis routing, credential-free rendering. tests/test_demo_session.py
(+5): policy governs order count with max_orders=None (exactly 3 fills, 4th
blocked by the GOVERNOR, not a cap), smoke cap intact, dry-run rehearses the
full entry path without order_send and respects the cap, cycle stats
recorded. Full suite: 559 passed. pre_demo_safety_check.sh passed.

## Alternatives Considered:
- Keeping max_orders=1 default and asking the operator to always pass a
  bigger number: rejected — the artificial cap would stay the system's
  design center and dry-runs would keep rehearsing nothing.
- Raising policy limits (trades/day) for evaluation sessions: rejected —
  03_RISK_POLICY is the authority; evaluation throughput comes from session
  length, not looser risk.
- Journaling simulated dry-run orders as TradeRecords: rejected — fake OPEN
  records would poison reconciliation (orphan_journal) and loss tracking;
  simulations live in the session report only.

## Risk:
Longer policy-governed sessions can take up to 3 real demo trades/day;
the operator supervises, the kill switch halts at the next cycle, and the
daily/weekly loss limits operate on real journaled P&L.

## Mitigation:
Smoke profile first; dry-run rehearsal of the same profile; news fail-closed;
preflight required fresh on every start; reflection/evaluation reports after
every session before any longer run.

## Files Affected:
src/execution/session_profiles.py (new), src/execution/demo_session.py,
src/execution/__init__.py, src/reflection/demo_evaluation.py (new),
src/reflection/__init__.py, scripts/demo_session_run.py,
scripts/demo_eval_report.py (new), scripts/demo_reflection.py (new),
scripts/generate_evidence_pack.py, tests/test_session_profiles.py (new),
tests/test_demo_evaluation.py (new), tests/test_demo_session.py,
10_TASK_QUEUE.md, 23_DEMO_TRADING_RUNBOOK.md, 24_INTELLIGENCE_AUDIT_ROADMAP.md

## Status:
Accepted

---

## Decision ID:
2026-06-10-06

## Date:
2026-06-10

## Area:
Execution / Architecture / Operations

## Decision:
CONTINUOUS-001: one continuous MT5 trading service is now the MAIN way to run
the system; bounded sessions and dry-runs are validation tools.

(a) ONE execution stack, no demo/live forks: TradingService owns only the
    OUTER loop; every cycle is SupervisedDemoSession.run_cycle() — the same
    data -> DecisionPipeline -> DemoTradePlanner -> RiskGovernor ->
    ExecutionGateway -> journal path as bounded sessions. Which account is
    traded is decided by .env (currently Exness DEMO, so orders are demo
    orders); whether orders are SENT is decided by the .env execution flags
    (without them, the identical loop runs as a dry-run with simulated plans).
(b) No fixed duration and no artificial order cap: the service runs until
    kill switch, weekly-loss risk shutdown, operator Ctrl+C, or a fatal
    error. Trade frequency is governed by the risk policy. The DAILY loss
    limit pauses entries until the next UTC day (DAY_PAUSED; the governor
    blocks, open positions remain managed) — only the WEEKLY limit stops the
    service (03_RISK_POLICY shutdown rule).
(c) Market-closed handling: schedule-based classification (MarketSchedule,
    weekend + daily break, UTC) plus tick-staleness as feed ground truth.
    Closed/stale states print clearly, heartbeat to
    logs/service_heartbeat.jsonl, and resume automatically. No crash, no
    journal spam.
(d) Terminal observability: a startup banner (service, profile, MASKED
    login, account type verified non-real, server, symbol, mode, risk
    limits, news, kill switch, journal/report paths, stop instructions) and
    per-cycle progress (cycle no, market state, bid/ask/spread, regime, HTF
    bias, decision + exact reason, confidence/uncertainty, positions with
    floating P&L, orders sent/simulated, trades today, daily P&L, risk/news/
    kill state, next poll). Orders print their MT5 ticket plus a Toolbox/
    Trade-tab hint.
(e) Daily rollover writes service_eval_YYYYMMDD and
    service_reflection_YYYYMMDD reports from the day's cycle stats + journal
    (same evaluator as DEMO-EVAL); a final service report is written on stop.
(f) PROVEN DEFECT found by the new tests and FIXED: ExecutionGateway built
    order_send requests from the CANONICAL symbol ("XAUUSDM"); MT5 symbols
    are case-sensitive, so the live terminal would have rejected the very
    first order. The gateway now takes broker_symbol (exact case, e.g.
    "XAUUSDm") for the request while checks keep comparing canonical forms.
    verify_demo_account moved to src/broker/mt5_data_adapter.py as the ONE
    shared readiness gate (REAL accounts refused until manual approval).
(g) Operator enablement model: the service requires a fresh READY preflight
    on every start; sending requires the .env execution flags; the DEMO-002
    confirmation token remains an internal construction invariant supplied by
    the runner after its own gating (per the explicit operational direction
    that the service starts once and keeps running).

## Reason:
A serious performance evaluation needs day-scale, unattended-capable runtime
with full observability — not hourly restarts. The risk policy, not session
plumbing, must decide how much the system trades.

## Evidence:
tests/test_trading_service.py (15): banner + per-cycle progress, runs past
the old 8h ceiling, governor (not a cap) limits orders to 3/day, market
closed waits + heartbeats + resumes, stale feed waits, restart reconciles a
journaled position and detects a close that happened while down (real P&L),
kill switch / weekly-loss shutdown / Ctrl+C stop cleanly with reports, daily
loss pauses without stopping, fatal errors reported, daily rollover writes
evaluation + reflection, dry-run cannot reach order_send, no credentials in
terminal/reports/heartbeat (login masked). tests/test_market_hours.py (6).
Full suite: 583 passed. pre_demo_safety_check.sh passed.

## Alternatives Considered:
- A separate "live service" implementation next to the session: rejected —
  duplicated execution logic is exactly what the architecture must avoid.
- Stopping the service at the DAILY loss limit: rejected — it forces a
  manual restart every losing day; the governor already blocks entries and
  open positions still need stop management. Weekly limit stops the service.
- Requiring a per-start confirmation token on the CLI: rejected for the
  continuous runner — enablement lives in .env flags + fresh preflight +
  kill switch; the token remains enforced at session construction.

## Risk:
Long unattended runs accumulate state; a wrong market schedule could pause
trading during open hours (opportunity cost, never a safety risk) or run
no-trade cycles while closed (validator rejects stale data anyway).

## Mitigation:
Tick staleness overrides the schedule on the open side; heartbeats and the
banner make state visible; kill switch halts at the next check; preflight is
fresh on every start; daily reports surface anomalies within one day.

## Files Affected:
src/execution/trading_service.py (new), src/execution/market_hours.py (new),
src/execution/demo_session.py, src/execution/session_profiles.py,
src/execution/gateway.py, src/execution/__init__.py,
src/broker/mt5_data_adapter.py, scripts/trading_service.py (new),
scripts/demo_session_run.py, scripts/live_shadow_run.py,
scripts/generate_evidence_pack.py, tests/test_trading_service.py (new),
tests/test_market_hours.py (new), tests/test_demo_session.py,
tests/test_session_profiles.py, 10_TASK_QUEUE.md, 23_DEMO_TRADING_RUNBOOK.md,
24_INTELLIGENCE_AUDIT_ROADMAP.md

## Status:
Accepted

---

## Decision ID:
2026-06-10-07

## Date:
2026-06-10

## Area:
Strategy / Regime / Risk / Reflection / Observability

## Decision:
INTELLIGENCE-001: wire gold confluence, MTF alignment, and adaptive risk into
the LIVE decision path; replace the blind CHOPPY hard block with graded logic.

Root causes found by the live-evidence audit (170+ no-trade cycles):
(R1) PROVEN: RegimeEngine counted structure flips over the WHOLE 300-candle
     (25h) M5 window with choppy_flips=2 — live markets were near-permanently
     CHOPPY. Fixed: regime classifies the RECENT window (regime_window=60,
     ~5h M5).
(R2) PROVEN: TradeHypothesisEngine hard-blocked CHOPPY with no grading.
     Fixed: graded gate — NO_TRADE/NEWS_RISK still always block; CHOPPY
     blocks unless the chop subtype is tradeable AND confluence >= 0.65.
(R3) HIGH-CONFIDENCE: conf=0.66/unc=0.67 were stuck because the regime
     component pinned at 0 and component disagreement saturated the
     uncertainty formula; with graded regime scoring the inputs now move.
(R4) PROVEN (wiring): zones (FVG/OB/supply-demand), premium/discount, and
     displacement existed but were absent from DecisionPipeline; H1/M15 did
     not exist in the live path; risk was statically 0.5%.

What was built:
(a) ChopClassifier (src/regime/chop_classifier.py): DANGEROUS_CHOP and
    LOW_QUALITY_CHOP hard-block; LIQUIDITY_CHOP_WITH_SWEEP,
    TRAP_REVERSAL_FROM_CHOP, BREAKOUT_EXPANSION_FROM_CHOP,
    CONTINUATION_AFTER_CHOP become candidates gated by confluence.
(b) MtfAlignmentEngine: D1/H4/H1/M15 structure bias + M5 execution state ->
    weighted alignment score + supported direction. H1/M15 are HONEST
    aggregations of the live M5 feed (None when insufficient — never faked).
(c) ConfluenceEngine: graded [0,1] scoring of mtf, sweep, BOS/CHOCH, FVG,
    order block, premium/discount, displacement, session, spread, orderflow
    proxy; reports component statuses AND what evidence is missing.
(d) AdaptiveRiskEngine (src/risk/adaptive_risk.py): evidence-driven budget
    with capital phases ($2k->10k->15k->25k+). Expands ONLY on strong
    combined evidence (max x1.65 on base), contracts multiplicatively on
    losses/drawdown/uncertainty/spread/exposure; news-unclear or untradeable
    regime = zero budget. HARD-CLAMPED to the 03_RISK_POLICY 0.5% cap — the
    cap is now a ceiling, not the default. No martingale is structurally
    possible (contractions are <= 1 multiplicative). The budget feeds BOTH
    the pipeline sizer and the DemoTradePlanner hard cap (min-ed in; can
    only tighten).
(e) Second setup type: sweepless BOS-continuation (aligned structural break
    + displacement >= 1.5x + confluence >= 0.60 + swing-based invalidation).
    Sweep-reclaim remains the primary setup. Stop-loss stays mandatory
    everywhere.
(f) Terminal reasoning per cycle: MTF row (d1/h4/h1/m15/m5 + score ->
    direction), intel row (sweep/BOS/FVG/OB/premium-discount/displacement/
    orderflow statuses), confluence + adaptive risk tier/% + chop subtype +
    regime reason, and for NO_TRADE the exact missing evidence ("needed:
    stronger fvg, order_block").
(g) Opportunity audit (src/reflection/opportunity_audit.py): after 60
    consecutive active-session cycles without an entry the service writes a
    classified report (verdict NO_TRADE_CORRECT / POSSIBLY_TOO_STRICT /
    MIXED; classifications now include MARKET_ARTIFACT).

## Reason:
The system was structurally passive: one regime label suppressed entire
trading sessions regardless of evidence, one setup type existed, and risk
ignored evidence quality entirely. The mission requires selective aggression:
graded evidence gates instead of binary blocks — without weakening any
safety layer (hypothesis invariants, governor, gateway, news fail-close all
unchanged or tightened).

## Evidence:
tests/test_chop_classifier.py (9), tests/test_confluence.py (12),
tests/test_adaptive_risk.py (14), tests/test_intelligence_pipeline.py (9),
tests/test_opportunity_audit.py (4), tests/test_trading_service.py (+3).
Full suite: 634 passed. pre_demo_safety_check.sh passed.

## Alternatives Considered:
- Tuning choppy_flips / window only: rejected as the sole fix — it reduces
  false CHOPPY but keeps the binary block; graded confluence is the design
  goal.
- Raising the 0.5% policy cap for the growth objective: rejected — the
  policy is the authority; faster compounding must come from opportunity
  quality and session length, and any cap change needs validated evidence.
- Letting confluence authorize trades directly: rejected — confluence gates
  candidates; hypothesis invariants and the Risk Governor remain the only
  authorities.

## Risk:
More entries will occur than before (that is the point). Heuristic
thresholds (0.65 chop override, 0.60 continuation, displacement 1.5x) are
reasoned but not yet backtest-calibrated.

## Mitigation:
Adaptive budget contracts on every adverse signal and on weak evidence;
demo-only execution; opportunity audits and daily evaluation/reflection
reports surface over/under-trading within a day; thresholds are constructor
parameters ready for backtest calibration (next task).

## Files Affected:
src/regime/chop_classifier.py (new), src/strategy/confluence.py (new),
src/risk/adaptive_risk.py (new), src/reflection/opportunity_audit.py (new),
src/strategy/pipeline.py, src/strategy/hypothesis.py,
src/execution/demo_session.py, src/execution/demo_planner.py,
src/execution/trading_service.py, src/reflection/demo_evaluation.py,
package __init__ files, scripts/generate_evidence_pack.py, tests (5 new
files + updates).

## Status:
Accepted

---

## Decision ID:
2026-06-10-08

## Date:
2026-06-10

## Area:
Risk Policy / Strategy / Data / Observability

## Decision:
INTELLIGENCE-002: full wiring verification, true MTF, gold session logic,
volatility safety layer, and the Adaptive Demo Risk Policy.

(a) Wiring matrix (25_WIRING_MATRIX.md, new tracked doc): all 20
    intelligence layers audited with evidence; 17 LIVE, news PARTIAL
    (honest manual/static, fail-closed), futures/macro PLACEHOLDER (honest
    interface, NullMacroProvider cannot fabricate availability — enforced
    by construction and tests).
(b) TRUE multi-timeframe data: the live cycle now fetches M15/H1/M1 from
    MT5 (M5/H4/D1 were already real). The pipeline prefers native candles
    and degrades honestly to labelled M5 aggregation ("aggregated(M5)") or
    "missing" — sources are carried in MtfAlignment and printed when
    degraded. M1 contributes a display-only trigger state (no weight until
    calibrated). Mixed alignment now reports an explicit conflict string.
(c) Asian range + London/NY logic (src/data/session_levels.py): today's
    Asian high/low, price position, sweep of Asian liquidity, post-Asian
    expansion ratio — wired as a confluence component (asian_range, weight
    0.05; weights re-normalized) and a terminal line. Unknown context is
    UNKNOWN, never fabricated.
(d) Dangerous-volatility classifier (src/regime/volatility_classifier.py):
    NORMAL / EXPANSION / DANGEROUS_SPIKE / NEWS_LIKE_SHOCK /
    SPREAD_MISMATCH / UNSTABLE_STOPS. Dangerous states hard-gate the
    pipeline BEFORE hypothesis; EXPANSION never blocks alone
    (03_RISK_POLICY volatility rule now explicit).
(e) ADAPTIVE DEMO RISK POLICY (owner-directed change to 03_RISK_POLICY):
    the fixed 0.5% demo cap is replaced by evidence-gated per-phase bounds:
    P1 (<$10k) base 0.40% ceiling 1.00%; P2 base 0.35% ceiling 0.80%;
    P3 base 0.30% ceiling 0.60%; P4 base 0.20% ceiling 0.50%.
    Daily 2% / weekly 5% / 3 trades/day / 1 position + protected add-on are
    UNCHANGED survival anchors; real-money policy UNCHANGED. Justification:
    E = r(pR-(1-p)); concentrating risk on the elite-evidence subset halves
    trades-to-milestone while the daily/weekly stops (not the per-trade
    cap) bound the tail — two max-risk Phase-1 losses still stop the day at
    -2%. Expansion multipliers x1.4 (strong) / x2.0 (elite); contraction
    unchanged (multiplicative, no martingale structurally). The demo tier
    dollar caps ($40/$80/$100, policy 20) remain a further outer bound and
    are non-binding at $2k equity.
(f) Opportunity audit verdicts extended: MISSED_SWEEP_REVERSAL,
    MISSED_CONTINUATION, DATA_INSUFFICIENT (plus existing
    NO_TRADE_CORRECT / POSSIBLY_TOO_STRICT / MIXED).
(g) BACKTEST-001 readiness: src/backtest/calibration.py +
    scripts/calibration_replay.py replay threshold variants
    (chop-override / continuation confluence / displacement, now a pipeline
    parameter) over historical M5 candles, score outcomes in R, and emit a
    recommendation. The tool NEVER mutates live thresholds (tested).
(h) Terminal: MTF row gains m1 + degraded-source + conflict lines; new
    vol=/asian= line; banner gains an honest macro status line.

## Evidence:
668 tests pass (+34): test_volatility_classifier (7), test_session_levels
(6), test_macro_context (3), test_calibration (4), adaptive phase-ceiling
tests (3), MTF true-fetch/degradation tests (session + pipeline), terminal
field assertions, opportunity-audit verdict tests.
pre_demo_safety_check.sh passed.

## Alternatives Considered:
- Keeping 0.5% and extending session length instead: rejected — at $2k a
  0.5% cap yields $10 risk/trade, which barely clears the broker min-lot
  floor on normal gold stops; the evaluation would starve mathematically.
- Weighting M1 in alignment now: rejected — uncalibrated micro-noise; it is
  display-only until BACKTEST-001 says otherwise.
- Pretending aggregated M5 is native H1/M15: rejected outright — sources
  are labelled and printed.

## Risk:
Phase-1 elite trades can risk up to 0.8% (x2.0 of 0.4% base), reaching 1.0%
only if a future evidence multiplier is added; loss clusters are capped by
the unchanged daily/weekly stops. Asian/volatility heuristics are reasoned,
not yet calibrated.

## Mitigation:
Demo-only; daily/weekly anchors unchanged; every adverse signal contracts
the budget multiplicatively; calibration tooling is ready to test all new
thresholds on history before any further change.

## Files Affected:
03_RISK_POLICY.md, 25_WIRING_MATRIX.md (new),
src/regime/volatility_classifier.py (new), src/data/session_levels.py (new),
src/orderflow/macro_context.py (new), src/backtest/calibration.py (new),
scripts/calibration_replay.py (new), src/risk/adaptive_risk.py,
src/strategy/pipeline.py, src/strategy/confluence.py,
src/execution/demo_session.py, src/execution/session_profiles.py,
src/execution/trading_service.py, src/reflection/opportunity_audit.py,
scripts/trading_service.py, scripts/demo_session_run.py,
scripts/generate_evidence_pack.py, package __init__ files, tests.

## Status:
Accepted

---

## Decision ID:
2026-06-10-09

## Date:
2026-06-10

## Area:
News / Macro / Futures / Strategy / Calibration / Verification

## Decision:
FINAL-INTELLIGENCE: complete the remaining intelligence layers honestly and
prove the wiring executable.

(a) NEWS-001 architecture: NewsProvider abstraction; the static calendar
    gains impact (HIGH/MEDIUM, unknown=HIGH fail-safe) and gold categories
    (CPI/PPI/NFP/FOMC/...). Five states: NEWS_CLEAR / NEWS_BLOCK /
    NEWS_UNKNOWN / NEWS_HIGH_IMPACT_SOON / NEWS_ACTIVE. HIGH active blocks
    entries; MEDIUM active and HIGH-soon (30-min lead) REDUCE risk (x0.50
    adaptive contraction); UNKNOWN stays fail-closed; open positions are
    always still managed. A real HTTP feed remains NEWS-001 (never faked).
(b) MACRO-001/FUTURES-001 interim: FileMacroProvider reads the operator-
    maintained, TIMESTAMPED configs/macro_context.json (as_of + max_age;
    stale/missing/malformed => UNAVAILABLE, never guessed). gold_pressure():
    DXY+yields rising => bearish-gold; falling => bullish-gold; mixed =>
    NEUTRAL. Confluence gains macro (0.04) + futures (0.04) components
    (weights re-normalized); unavailable sits at the neutral 0.5. Macro
    conflict contracts adaptive risk x0.75. Confirmation only — proven by
    test that macro cannot create a candidate direction.
(c) M1 refinement upgraded from display-only: M1RefinementEngine assesses
    micro rejection/displacement/noise ONLY after a setup exists; its sole
    power is VETO_DELAY (skip this cycle's entry). Tests prove M1 cannot
    create trades or override the higher-timeframe stack.
(d) BACKTEST-001 readiness completed: calibration reports max drawdown (R),
    false positives, missed sweep-reversal vs continuation decomposition,
    volatility blocks, per-segment expectancies (walk-forward-ready), and a
    KEEP / TIGHTEN / LOOSEN / NEED_MORE_DATA verdict with recommended
    thresholds. Still recommendation-only.
(e) Executable wiring verification: scripts/verify_wiring.py runs a REAL
    pipeline decision on synthetic candles + introspects the execution
    classes; writes per-layer LIVE/PARTIAL/UNAVAILABLE_BY_CONFIG/
    PLACEHOLDER/MISSING with evidence. Current: 16 LIVE, 1 PARTIAL (news),
    2 UNAVAILABLE_BY_CONFIG (macro/futures operator file absent), 0 MISSING.
(f) Terminal: banner gains macro provider status, M1 state, active
    thresholds, capital phase (+equity); cycles gain external macro=/
    futures= line, m1= line, phase= in the risk line, and the 5-state news
    label.

## Evidence:
692 tests pass (+24): news states (7), macro file provider + confluence/
adaptive influence (5), M1 refinement (6), calibration verdicts (2), wiring
verification (4). pre_demo_safety_check.sh passed. Self-audit: no stale
imports, no duplicate demo/live logic, runners import clean, bounded runner
still honest off-Windows.

## Alternatives Considered:
- Scraping a public calendar/quotes site for "real" feeds: rejected —
  unreliable, ToS-questionable, and silently breakable; the stale-aware
  operator file is honest and the provider interface is feed-ready.
- Letting M1 carry alignment weight now: rejected — uncalibrated; veto-only
  is the safe useful subset.
- Auto-applying calibration recommendations: rejected outright
  (04_ADAPTATION_POLICY).

## Risk:
The operator macro file can be wrong (human error) — bounded: confirmation
weights total 0.08 and contraction-only on conflict. M1 veto may skip some
good entries (delay, never loss).

## Mitigation:
Stale-aware timestamps; all states visible per cycle; calibration tooling
ready to measure every new threshold on history.

## Files Affected:
src/risk/news_guard.py, src/orderflow/macro_context.py,
src/strategy/m1_refinement.py (new), src/strategy/confluence.py,
src/strategy/pipeline.py, src/risk/adaptive_risk.py,
src/execution/demo_session.py, src/execution/trading_service.py,
src/backtest/calibration.py, src/reflection/wiring_verification.py (new),
scripts/verify_wiring.py (new), scripts/calibration_replay.py,
scripts/trading_service.py, scripts/generate_evidence_pack.py,
25_WIRING_MATRIX.md, package __init__ files, tests (3 new files + updates).

## Status:
Accepted
