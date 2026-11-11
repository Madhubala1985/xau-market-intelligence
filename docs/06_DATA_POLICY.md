# 06_DATA_POLICY.md

## Purpose

This file defines data rules for the XAU/USD system.

No trading decision is valid unless data quality is valid.

## Required Data Sources

Primary execution data:

- MT5 XAU/USD bid/ask,
- MT5 XAU/USD candles,
- spread,
- tick volume,
- account state,
- position state,
- order history.

Optional confirmation data:

- gold futures price,
- futures volume,
- open interest,
- COT data,
- economic calendar,
- DXY or USD context,
- yields context.

Optional data may support confidence but may not bypass core trading rules.

## Timeframes

The system should support:

- tick,
- 1M,
- 5M,
- 15M,
- 1H,
- 4H,
- Daily.

Main model usage:

- Daily: macro bias and major levels,
- 4H: directional context and major sweeps,
- 1H: setup formation,
- 15M: entry refinement,
- 5M: execution confirmation.

## Data Validation

The system must detect:

- missing candles,
- duplicate candles,
- malformed timestamps,
- timezone mismatch,
- impossible OHLC values,
- abnormal spreads,
- zero-volume anomalies,
- stale data,
- disconnected broker feed,
- inconsistent bid/ask,
- mismatched symbol,
- look-ahead leakage.

## Timestamp Policy

All data must be normalized to one internal timezone.

The system must preserve broker timestamp and normalized timestamp.

Session classification must be based on normalized time.

## Look-Ahead Bias Ban

Backtests must use only data available at the decision timestamp.

Forbidden:

- future candles,
- end-of-day values before day close,
- delayed data treated as live,
- future COT reports,
- future high/low levels unknown at entry time.

## Data Storage

The system should store:

- raw data,
- normalized data,
- validation results,
- rejected data records,
- trading decisions,
- broker responses,
- trade outcomes,
- reflection reports.

## Final Rule

Bad data must never produce a trade.
