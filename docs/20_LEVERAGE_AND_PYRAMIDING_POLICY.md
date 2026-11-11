# 20_LEVERAGE_AND_PYRAMIDING_POLICY.md

## Purpose

This file defines leverage-aware XAU/USD position sizing and protected pyramiding.

The system may use leverage in demo, but leverage must never bypass max-loss rules.

The system must calculate actual loss at stop-loss before every trade.

## Core Rule

Stop distance comes from structure.

Lot size comes from allowed risk.

Leverage only affects margin requirement. Leverage does not reduce trade loss if stop-loss is hit.

## Required Calculations

Before any trade, the system must calculate:

- account balance,
- free margin,
- symbol contract size,
- tick size,
- tick value,
- minimum lot,
- lot step,
- maximum lot,
- requested lot,
- stop-loss distance,
- loss per lot at stop,
- implied USD loss,
- implied account risk percentage,
- margin required,
- total open XAU/USD risk,
- same-direction exposure,
- correlated exposure.

## Demo Confidence Risk Tiers

Demo may use higher risk than real mode for validation.

Allowed demo tiers:

### NO_TRADE

Used when setup is weak, unclear, conflicting, or invalid.

Risk: 0.

### NORMAL_SETUP

Used when setup is valid but not elite.

Maximum loss: $40.

### HIGH_CONFLUENCE_SETUP

Used when structure, liquidity, session, regime, and execution quality are strongly aligned.

Maximum loss: $80.

### ELITE_A_PLUS_SETUP

Used only in demo and only when all confluence conditions are present.

Maximum loss: $100.

## Real Risk Separation

Real-money launch risk remains conservative.

Real mode must not inherit demo tier limits.

Initial real-money risk remains controlled by 03_RISK_POLICY.md and 18_CAPITAL_AND_SCALING_POLICY.md.

## Fixed Lot Rule

The system may consider 0.01, 0.05, or 0.10 lot in demo only after calculating implied loss at the structural stop.

Fixed lot size may never bypass max-loss rules.

If 0.10 lot creates excessive loss, reduce or block.

If broker minimum lot creates excessive risk, block.

## Protected Pyramiding

Adding another same-direction trade is allowed only when:

1. the existing trade is already protected at break-even or locked profit,
2. the first trade is not moving toward its original stop-loss,
3. the add-on trade has a fresh valid setup,
4. the add-on trade has its own thesis, invalidation, stop-loss, and risk calculation,
5. HTF bias, liquidity direction, and regime still support continuation,
6. total combined XAU/USD exposure remains within the allowed demo cap.

## Forbidden Pyramiding

The system must not:

- add to a losing trade,
- add when price is moving toward original stop-loss,
- add to recover a bad entry,
- add only because leverage is available,
- add if total open risk exceeds the cap,
- add if the first trade is not protected,
- add if the new trade lacks its own setup.

## After Stop-Loss

If original stop-loss is hit, the model may trade again only after a fresh independent setup forms.

A new trade after stop-loss must not be a revenge trade.

## Final Rule

Add to winners only.

Never add to losers.

Every add-on is a new trade thesis.

Total exposure remains controlled.
