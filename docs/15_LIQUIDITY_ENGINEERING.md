# 15_LIQUIDITY_ENGINEERING.md

## Purpose

This file defines liquidity-engineering logic.

The system must understand where retail stops may cluster and how price may sweep liquidity before moving.

## Liquidity Types

The system must track:

- buy-side liquidity,
- sell-side liquidity,
- equal highs,
- equal lows,
- session highs,
- session lows,
- previous day high,
- previous day low,
- previous week high,
- previous week low,
- swing highs,
- swing lows,
- round-number zones,
- obvious breakout zones.

## Buy-Side Liquidity

Buy-side liquidity exists above:

- equal highs,
- recent swing highs,
- previous day high,
- session high,
- breakout resistance,
- round-number zones.

## Sell-Side Liquidity

Sell-side liquidity exists below:

- equal lows,
- recent swing lows,
- previous day low,
- session low,
- breakout support,
- round-number zones.

## Valid Liquidity Sweep

A liquidity sweep requires:

1. price takes a known liquidity level,
2. price fails to continue cleanly,
3. price closes back or rejects meaningfully,
4. displacement appears in opposite or continuation direction,
5. structure confirms.

A wick alone is not enough.

## Manipulation Definition

Manipulation must be defined mechanically.

Possible manipulation pattern:

1. price builds obvious liquidity,
2. price sweeps that liquidity,
3. breakout traders are trapped,
4. price reclaims level,
5. displacement appears,
6. structure shifts.

The system must not label manipulation without evidence.

## Accumulation Definition

Accumulation may be detected when:

- price ranges,
- volatility compresses,
- liquidity builds on both sides,
- no clean trend expansion occurs,
- order-flow proxy is mixed or compressed.

## Distribution Definition

Distribution may be detected when:

- price expands away from swept liquidity,
- displacement follows,
- structure aligns,
- volume/tick proxy supports participation,
- pullbacks respect imbalance or order block.

## Expansion Definition

Expansion may be detected when:

- range breaks with displacement,
- pullbacks are shallow or structured,
- momentum continues toward liquidity target,
- volatility expands but remains tradable.

## Stop-Hunt Awareness

The system must avoid placing stops directly at obvious retail stop pools unless protected by a volatility and structure buffer.

## Final Rule

Liquidity sweep is not a trade by itself.

Trade is allowed only after sweep, confirmation, valid stop, and risk approval.
