# 08_ERROR_POLICY.md

## Purpose

This file defines how Claude Code and the system must handle errors.

Errors must be solved through root cause, not bypassed.

## Error Classification

Every error must be classified as:

- Proven Defect,
- High-Confidence Defect,
- Hypothesis,
- Environment Issue,
- Data Issue,
- Broker Issue,
- Test Issue,
- Market Artifact,
- Unknown.

## Error Handling Procedure

When an error occurs:

1. capture exact error,
2. reproduce it if possible,
3. identify affected module,
4. inspect relevant code/data,
5. classify the error,
6. determine root cause,
7. propose minimal fix,
8. apply fix,
9. rerun failed test,
10. run regression test,
11. update decision log or handoff.

## Forbidden Fixes

Claude must never:

- hide errors,
- comment out failing code without reason,
- delete tests,
- bypass risk checks,
- use broad rewrites unnecessarily,
- replace real logic with fake mocks,
- claim environment issue without evidence,
- mark unresolved errors as complete.

## Trading Error Rule

If error affects trading safety, execution, broker state, risk, stop-loss, or position tracking, the system must enter safe mode.

Safe mode means:

- no new trades,
- preserve logs,
- manage existing positions only if safe,
- require manual review.

## Broker Error Rule

If MT5 or broker state is inconsistent:

- do not trade,
- read current open positions,
- compare local state,
- log mismatch,
- block execution until resolved.

## Data Error Rule

If candles, ticks, spread, or session data are invalid:

- do not trade,
- reject affected data,
- log error,
- wait for valid data.

## Unknown Error Rule

If root cause is unknown, Claude must not guess a fix.

Claude may create an investigation note and stop safely.

## Final Rule

Unexplained safety errors block trading.
