# 13_XAUUSD_SMC_PLAYBOOK.md

## Purpose

This file defines the XAU/USD Smart Money Concepts playbook.

The system must not trade random indicator signals. It must trade only structured XAU/USD opportunities based on liquidity, market structure, session behavior, premium/discount location, displacement, imbalance, and risk-controlled execution.

## Core Market Model

The system treats XAU/USD movement as a possible sequence of:

1. accumulation,
2. manipulation,
3. distribution,
4. expansion.

These phases must be detected mechanically and never assumed emotionally.

## Primary Concepts

The system must track:

- buy-side liquidity,
- sell-side liquidity,
- equal highs,
- equal lows,
- previous day high/low,
- previous week high/low,
- Asian session high/low,
- London session high/low,
- New York session high/low,
- swing highs/lows,
- BOS,
- CHOCH,
- FVG,
- order blocks,
- supply zones,
- demand zones,
- displacement candles,
- premium/discount zones,
- liquidity sweeps,
- failed breakouts,
- reclaim after sweep.

## Multi-Timeframe Roles

Daily:
- macro bias,
- major liquidity,
- major supply/demand,
- large premium/discount zones.

4H:
- directional context,
- major liquidity sweep confirmation,
- key order blocks,
- FVG,
- supply/demand.

1H:
- setup formation,
- liquidity engineering,
- trend/reversal conditions.

15M:
- refined entry zone,
- displacement validation,
- FVG/order-block retest.

5M:
- microstructure confirmation,
- entry timing,
- spread and execution quality.

5M confirmation may never override higher-timeframe context.

## Valid Trade Hypothesis

A valid trade hypothesis must include:

1. higher-timeframe bias,
2. liquidity target or liquidity sweep,
3. structure confirmation,
4. refined entry zone,
5. invalidation level,
6. stop-loss logic,
7. target/liquidity objective,
8. confidence score,
9. uncertainty score,
10. risk-governor approval.

If any are missing, the trade must be rejected.

## Primary Setup Types

### Setup 1: Asian Range Sweep to London Reversal

Asian range forms.
London sweeps Asian high or low.
Price rejects back.
Displacement appears.
Lower timeframe confirms CHOCH/BOS.
Entry may occur on FVG/order-block retest.
Stop must be beyond sweep with volatility buffer.

### Setup 2: London Sweep to New York Reversal or Continuation

London creates liquidity.
New York sweeps London high or low.
Model checks whether sweep is reversal or continuation.
Entry only after 15M/5M confirmation.

### Setup 3: Daily/4H Liquidity Sweep Reversal

Major high/low is swept.
Price fails to continue.
Displacement appears.
1H/15M structure shifts.
Entry only after refined confirmation.

### Setup 4: Trend Pullback into Premium/Discount

Daily/4H trend is clear.
Price pulls into discount for longs or premium for shorts.
FVG/order block aligns.
Lower timeframe confirms continuation.

### Setup 5: No-Trade Manipulation Zone

Liquidity is swept repeatedly.
No clean displacement.
Structure is unclear.
Spread or volatility is unsafe.
Correct output is NO TRADE.

## Final Rule

No trade is allowed from SMC language alone.

Every SMC concept must be mechanically detected, scored, and risk-approved.
