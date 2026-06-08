# 04_ADAPTATION_POLICY.md

## Purpose

This file defines how the system may adapt and improve.

The system should be adaptive, but not reckless.

Adaptation must be evidence-gated, testable, reversible, and never emotional.

## Core Rule

Live self-mutation is forbidden.

The system may observe and reflect during live/demo trading, but it may not change core trading logic during an active session.

## Allowed Live Adaptation

During demo or live execution, the system may adapt only in protective ways:

- reduce risk,
- block trading,
- enter observation mode,
- increase confirmation requirement,
- trigger cooldown,
- stop trading after drawdown,
- reduce confidence after repeated uncertainty,
- flag regime mismatch.

## Forbidden Live Adaptation

During execution, the system must not:

- rewrite strategy rules,
- change thresholds to force trades,
- remove filters,
- bypass risk checks,
- retrain model live,
- change stop logic live,
- increase risk after wins,
- revenge-adjust after losses.

## Reflection-Based Adaptation

After each session, the reflection engine may analyze:

- winning trades,
- losing trades,
- missed trades,
- rejected trades,
- false positives,
- false negatives,
- wrong regime classifications,
- poor stop placement,
- weak confirmations,
- poor trailing behavior,
- spread/slippage problems,
- repeated mistakes.

## Mistake Categories

Every mistake must be classified as one of:

- wrong direction,
- early entry,
- late entry,
- poor stop placement,
- stop too obvious,
- stop too tight,
- stop too wide,
- invalid liquidity interpretation,
- wrong regime,
- poor session context,
- weak displacement,
- false FVG/order block,
- execution issue,
- news shock,
- spread/slippage issue,
- random market artifact,
- model overconfidence,
- uncertainty ignored,
- risk violation.

## Improvement Proposal Rule

Every proposed improvement must include:

1. root cause,
2. affected module,
3. expected benefit,
4. risk of change,
5. required tests,
6. validation method,
7. rollback plan.

## Promotion Gate

A change can enter execution only after passing:

1. unit tests,
2. integration tests,
3. backtest comparison,
4. walk-forward validation,
5. paper/demo validation,
6. risk review,
7. decision-log entry.

## Final Rule

Adaptation is allowed only when it increases robustness.

Adaptation is forbidden when it only increases activity.
