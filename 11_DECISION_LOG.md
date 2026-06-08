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
