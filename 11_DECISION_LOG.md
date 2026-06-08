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
