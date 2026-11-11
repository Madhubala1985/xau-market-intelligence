# 19_GOLD_FUTURES_CONFIRMATION_POLICY.md

## Purpose

This file defines how the system may use gold futures data to support XAU/USD trading decisions.

## Core Rule

Spot/CFD XAU/USD from MT5/Exness is the execution instrument.

Gold futures data may be used only as:

- confirmation,
- context,
- confidence adjustment,
- uncertainty adjustment,
- risk adjustment.

Gold futures data may not directly trigger trades by itself.

## Allowed Futures Inputs

The system may use:

- gold futures price movement,
- futures volume,
- open interest,
- futures session highs/lows,
- futures/spot divergence,
- high-volume futures zones,
- COT positioning after official release.

## Look-Ahead Bias Ban

The system must never use data that was not available at the time of decision.

Forbidden:

- future candles during backtest,
- end-of-day volume before the day ends,
- COT data before official release,
- delayed data treated as live,
- revised data treated as originally known.

## Confirmation Logic

Gold futures may increase confidence only when it aligns with:

1. XAU/USD structure,
2. liquidity thesis,
3. regime,
4. volatility condition,
5. execution quality.

## Conflict Logic

If XAU/USD gives a setup but gold futures conflicts:

- reduce confidence,
- increase uncertainty,
- reduce risk,
- or block trade.

## COT Usage

COT is slow macro-positioning context.

COT may influence higher-timeframe bias.

COT may not be used for 5M or 15M entries.

## Futures/Spot Divergence

If spot breaks a level but futures does not confirm, the model must become cautious.

If futures leads and spot follows with structure confirmation, confidence may increase.

## Missing Futures Data

If futures data is unavailable, the system must continue using XAU/USD core logic.

Missing futures data must not crash the system.

## Final Authority

Gold futures confirmation cannot override the risk governor.

If risk is invalid, trade remains blocked.
