# 17_STOP_AND_TRAILING_POLICY.md

## Purpose

This file defines stop-loss and trailing-stop intelligence.

The system must be harder to kill.

It must not place stops at obvious retail liquidity locations and must not use fear-based tight stops.

## Stop-Loss Principles

A stop-loss must be placed where the trade thesis is invalidated.

Stop-loss must account for:

- liquidity sweep high/low,
- retail stop clusters,
- ATR or volatility buffer,
- spread,
- broker minimum stop distance,
- structure invalidation,
- session volatility,
- news volatility.

## Forbidden Stop Behavior

The system must not:

- place stop directly on obvious equal highs/lows,
- place stop too close because risk size is too large,
- remove stop-loss,
- widen stop-loss after entry,
- average down,
- move stop based on hope,
- tighten stop only to increase lot size.

## Be Harder To Kill Rule

The system must ask:

"Is my stop placed where the crowd is likely to place theirs?"

If yes, the system must either:

- move stop beyond logical liquidity with buffer,
- reduce position size,
- skip trade.

## Trailing Stop Methods

Allowed trailing methods:

1. structure-based trailing,
2. volatility-based trailing,
3. liquidity-target trailing,
4. partial profit plus runner,
5. break-even only after confirmation.

## Partial Profit Logic

The system may take partial profit at:

- 1R,
- next liquidity pool,
- opposing session level,
- opposing FVG/order block,
- volatility exhaustion area.

## Runner Logic

The system may hold a runner only when:

- structure remains valid,
- no opposite displacement appears,
- spread remains safe,
- risk is protected,
- liquidity target remains open.

## Emergency Exit

The system may exit early if:

- broker state becomes unsafe,
- spread explodes,
- major news volatility begins,
- opposite structure shift confirms,
- stop-loss attachment fails,
- data feed becomes stale.

## Final Rule

The system must not exit winners from fear.

The system must not hold invalid trades from hope.
