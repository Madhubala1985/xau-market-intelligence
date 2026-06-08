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
