# 05_EXECUTION_POLICY.md

## Purpose

This file defines execution rules for MT5/Exness integration.

Execution must be strict and safe.

The execution layer does not think. It only executes approved orders after validation.

## Execution Instrument

The only tradable instrument is XAU/USD.

Broker symbol mapping may vary, such as:

- XAUUSD,
- XAUUSDm,
- XAUUSD.raw,
- GOLD.

The system must map broker symbol names carefully and must not trade any other instrument.

## Execution Modes

Allowed modes:

1. backtest,
2. paper simulation,
3. MT5 demo execution,
4. live shadow mode,
5. real execution after explicit approval.

Default mode must never be real.

## Demo Credential Policy

For demo mode, MT5 login, password, server, path, and symbol may be loaded from local `.env`.

The `.env` file must remain uncommitted.

Claude may create code that reads credentials from environment variables.

Claude must not hardcode credentials.

Claude must not print credentials.

Claude must not store credentials in logs or reports.

Demo credentials allow connection testing and demo execution only after risk and execution modules are validated.

Real credentials remain forbidden until explicit real-mode approval.

## Execution Permission Flags

The system must respect:

- ALLOW_PAPER_ORDERS,
- ALLOW_DEMO_ORDERS,
- ALLOW_REAL_ORDERS,
- ALLOW_MT5_ORDER_SEND,
- REAL_TRADING_ENABLED.

Demo execution requires:

- TRADING_MODE=DEMO,
- ALLOW_DEMO_ORDERS=true,
- ALLOW_MT5_ORDER_SEND=true,
- ALLOW_REAL_ORDERS=false,
- REAL_TRADING_ENABLED=false.

Real execution requires a future explicit approval process and must remain disabled by default.

## Pre-Execution Checklist

Before sending any order, the execution gateway must verify:

1. risk governor approved,
2. symbol is XAU/USD only,
3. account mode is correct,
4. broker connection is active,
5. market is tradable,
6. spread is acceptable,
7. lot size is valid,
8. stop-loss is attached,
9. take-profit or exit logic exists,
10. margin is sufficient,
11. no duplicate order exists,
12. state persistence is active,
13. trade journal is writable,
14. current position state is known.

If any check fails, order must not be sent.

## Order State Machine

Every trade must follow this lifecycle:

SIGNAL_CREATED
→ RISK_APPROVED
→ ORDER_PREPARED
→ ORDER_SENT
→ ORDER_ACCEPTED or ORDER_REJECTED
→ POSITION_OPEN
→ POSITION_MANAGED
→ POSITION_CLOSED
→ TRADE_LOGGED
→ REFLECTION_PENDING
→ REFLECTION_COMPLETE

Any missing state transition must be treated as a defect.

## Order Rejection Rule

If broker rejects an order:

- log rejection reason,
- do not retry blindly,
- do not increase lot size,
- do not remove stop-loss,
- do not bypass risk,
- classify rejection,
- enter safe mode if repeated.

## Duplicate Trade Protection

The system must prevent duplicate orders caused by:

- repeated signal loop,
- terminal reconnect,
- script restart,
- stale state,
- network delay,
- MT5 response delay.

## Open Position Recovery

On startup, the system must check broker open positions before generating new trades.

If broker state and local state disagree, trading must be blocked until resolved.

## Manual Kill Switch

There must be a manual kill switch that immediately prevents new orders.

Open-position management may continue only for protective exits.

## Final Rule

Execution may never bypass the risk governor.
