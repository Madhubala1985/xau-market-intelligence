# 18_CAPITAL_AND_SCALING_POLICY.md

## Purpose

This file defines capital protection and scaling rules.

The system must earn the right to scale.

## Starting Capital Assumption

Expected real capital:

- minimum: $1,500,
- maximum initial range: $2,000.

Small accounts require strict survival rules.

## Demo Stage

In demo stage, the system must prove:

- execution stability,
- risk calculation,
- stop placement,
- trade journal consistency,
- reflection quality,
- no duplicate trades,
- no state mismatch,
- no risk-governor bypass.

Demo profit alone is not enough.

## Demo Risk Profile

Allowed demo profile:

- maximum 0.50% risk per trade,
- maximum 2.00% daily loss,
- maximum 5.00% weekly loss,
- maximum 3 trades per day,
- maximum 1 open trade.

This demo profile is for validation only.

It does not approve the same risk for real-money trading.

## Paper / Demo Performance Requirements

Before real money, paper/demo/live-shadow results must show:

- stable execution,
- acceptable drawdown,
- no critical defects,
- realistic trade frequency,
- correct no-trade behavior,
- no revenge behavior,
- no overtrading,
- proper stop-loss behavior,
- proper trailing behavior.

## Real-Money Stage 1

Initial real mode, if approved:

- maximum 0.25% risk per trade,
- maximum 0.50% daily loss,
- maximum 1.50% weekly loss,
- maximum 1 open trade,
- maximum 2 trades per day,
- no compounding,
- no scaling for at least first validation period.

## Scaling Conditions

Risk may increase only if:

1. live execution is stable,
2. drawdown remains controlled,
3. journal has no missing trades,
4. risk governor has no violations,
5. reflection reports are consistent,
6. performance is stable across regimes,
7. no critical defects remain,
8. manual approval is given.

## Forbidden Scaling

The system must not scale because of:

- one winning day,
- one strong trade,
- high confidence,
- emotional recovery goal,
- missed profit,
- backtest-only result,
- Claude suggestion without validation.

## Drawdown Response

During drawdown, the system must:

- reduce risk,
- reduce trade frequency,
- increase confirmation threshold,
- review mistake categories,
- avoid live strategy changes,
- enter observation mode if necessary.

## Final Rule

Scaling is earned through evidence, not excitement.
