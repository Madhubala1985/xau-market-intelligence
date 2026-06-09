# 23_DEMO_TRADING_RUNBOOK.md

## Purpose

This file defines how supervised demo trading may be started after all gates pass.

## Pre-Demo Checklist

Before demo orders:

- all tests pass,
- .env is ignored,
- real trading disabled,
- demo account verified,
- XAU/USD symbol verified,
- risk governor tested,
- position sizing tested,
- stop-loss mandatory,
- journal writable,
- state persistence healthy,
- live shadow mode completed,
- manual user approval given.

## Demo Trading Mode

Demo trading may use:

- 0.01,
- 0.05,
- 0.10 lot,

only when risk calculation confirms the implied loss remains within the allowed tier.

## Demo Trading Goals

The goal of demo trading is not profit first.

The goal is to verify:

- signal quality,
- no-trade behavior,
- order correctness,
- stop placement,
- trailing logic,
- pyramiding safety,
- broker execution,
- state recovery,
- risk blocking,
- reflection reports.

## Demo Shutdown Conditions

Stop demo trading if:

- risk limit hit,
- two consecutive invalid trades,
- broker state mismatch,
- order state mismatch,
- journal failure,
- stop-loss attachment failure,
- unexpected order,
- spread abnormal,
- data stale,
- user kill switch activated.

## Final Rule

Demo mode is for validation.

Real mode remains forbidden.
