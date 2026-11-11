# 16_ORDERFLOW_PROXY_POLICY.md

## Purpose

This file defines how the system may use order-flow, volume, CVD, and delta information for XAU/USD trading.

## Important Limitation

XAU/USD through MT5/Exness is not guaranteed centralized exchange order flow.

Therefore, MT5 tick volume, real volume, CVD, and delta must be treated as broker-level or data-source-level proxies unless proven otherwise.

The system must never claim that broker-level volume data represents the full institutional gold market.

## Allowed Inputs

The system may use:

- tick-volume expansion,
- tick-volume exhaustion,
- spread widening,
- bid/ask tick movement proxy,
- aggressive candle movement,
- CVD proxy divergence,
- delta proxy confirmation,
- volume expansion during displacement,
- volume exhaustion after sweep,
- abnormal tick activity.

## Allowed Interpretation

Allowed language:

- tick-volume proxy supports bullish pressure,
- delta proxy conflicts with long thesis,
- CVD proxy suggests exhaustion,
- order-flow proxy is inconclusive,
- volume proxy supports displacement.

Forbidden language:

- institutions are definitely buying,
- smart money is confirmed,
- CVD proves reversal,
- volume guarantees direction.

## Trade Rule

Order-flow proxy can adjust:

- confidence,
- uncertainty,
- risk size,
- trailing aggressiveness.

Order-flow proxy cannot directly trigger trades.

## Conflict Rule

If price structure and order-flow proxy conflict, uncertainty must increase.

If uncertainty becomes too high, the trade must be blocked or reduced.

## Final Rule

Order-flow proxy supports the thesis.

It does not replace structure, liquidity, or risk.
