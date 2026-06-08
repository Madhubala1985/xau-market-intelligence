# 07_TEST_POLICY.md

## Purpose

This file defines the testing policy.

Tests are mandatory. Passing tests through bypasses is forbidden.

## Test Philosophy

Every important trading rule must be testable.

No module is complete unless it has tests and evidence.

## Required Test Types

The project must include:

1. unit tests,
2. integration tests,
3. backtest validation,
4. walk-forward validation,
5. paper-trading validation,
6. MT5 demo-connection tests,
7. state-recovery tests,
8. risk-governor tests,
9. execution-state tests,
10. regression tests.

## Critical Modules Requiring Tests

Mandatory tests for:

- data ingestion,
- data validation,
- timeframe aggregation,
- session detection,
- liquidity sweep detection,
- BOS/CHOCH detection,
- FVG detection,
- order block detection,
- premium/discount detection,
- regime classification,
- confidence scoring,
- uncertainty scoring,
- risk governor,
- position sizing,
- stop-loss placement,
- trailing stop logic,
- execution state machine,
- broker state recovery,
- trade journal,
- reflection reports.

## Risk Tests

Risk-governor tests must prove:

- no stop-loss = blocked,
- too much risk = blocked,
- daily loss reached = blocked,
- weekly loss reached = blocked,
- spread too high = blocked,
- invalid lot size = blocked,
- broker state unknown = blocked,
- duplicate trade = blocked,
- wrong symbol = blocked.

## Backtest Requirements

Backtests must include:

- spread,
- slippage,
- commission if applicable,
- realistic stop-loss,
- realistic lot sizing,
- session rules,
- data availability rules,
- no future leakage.

## Test Failure Rule

If a test fails, Claude must not bypass it.

Claude must:

1. reproduce the failure,
2. identify root cause,
3. classify the defect,
4. make the smallest correct fix,
5. rerun the failed test,
6. run relevant regression tests,
7. document result.

## Forbidden Test Behavior

Claude must not:

- delete failing tests,
- weaken assertions,
- mock core trading logic falsely,
- silence errors,
- skip risk tests,
- mark untested modules complete,
- claim success without output evidence.

## Final Rule

A feature is not complete until tests prove it.
