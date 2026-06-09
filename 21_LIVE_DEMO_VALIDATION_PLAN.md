# 21_LIVE_DEMO_VALIDATION_PLAN.md

## Purpose

This file defines the next phase after the completed P0-P11 roadmap.

The goal is to move from tested architecture to live demo validation.

## Phase 12 Goal

Connect the completed DecisionPipeline to real or replayed XAU/USD data, validate MT5 demo connectivity, run live shadow mode, and only then allow supervised demo order execution.

## Non-Negotiable Safety Rules

1. Real-money trading remains forbidden.
2. Demo order execution is allowed only after required gates pass.
3. No credentials may be printed or committed.
4. .env must remain ignored.
5. The pipeline must not execute orders directly.
6. ExecutionGateway remains the only order pathway.
7. Risk Governor remains final authority.
8. The system must stop safely on broker/data/state inconsistency.

## Required Gate Sequence

### Gate 1: RISK-001

Implement leverage-aware confidence-tiered sizing and protected pyramiding.

### Gate 2: LIVE-VERIFY-001

Generate an evidence pack showing what is implemented, what is tested, what is stubbed, and what is not live-proven.

This is not a broad rewrite or re-audit.

### Gate 3: WINMT5-001

Validate MT5 demo connection on the correct host.

Required proof:

- MT5 initializes,
- demo login works,
- XAU/USD symbol is detected,
- symbol info is read,
- latest candles are fetched,
- spread is read,
- account info is read without printing credentials,
- no order_send is called.

### Gate 4: LIVE-001

Create live/replay adapter feeding DecisionPipeline into ShadowRunner.

No orders.

### Gate 5: LIVE-002

Run live shadow mode for XAU/USD.

No orders.

Required output:

- pipeline decisions,
- rejected trade reasons,
- confidence/uncertainty,
- risk decisions,
- journal entries,
- session report.

### Gate 6: DEMO-001

Run demo execution preflight.

Allowed only after live shadow is stable.

### Gate 7: DEMO-002

Run supervised MT5 demo order execution.

Demo orders only.

No real orders.

## Demo Order Permission

Demo orders are allowed only when:

- TRADING_MODE=DEMO,
- REAL_TRADING_ENABLED=false,
- ALLOW_REAL_ORDERS=false,
- ALLOW_DEMO_ORDERS=true,
- ALLOW_MT5_ORDER_SEND=true,
- Risk Governor approves,
- ExecutionGateway approves,
- broker account is verified as demo,
- state persistence is healthy,
- journal is writable.

## Final Rule

The project may proceed to demo execution.

The project may not proceed to real-money execution.
