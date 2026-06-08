"""Tests for P1-003 Data Validation Engine.

Covers the three required categories from 10_TASK_QUEUE.md / 12_HANDOFF.md:
- valid data passes,
- malformed data is rejected,
- invalid data produces a NO_TRADE status.

Plus each individual detection: missing candles, duplicates, timestamp issues,
stale data, look-ahead, spread anomalies, symbol/timeframe mismatch, zero volume.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.data import (
    Candle,
    DataValidator,
    ValidationCode,
    ValidationConfig,
    ValidationStatus,
)

UTC = timezone.utc
START = datetime(2026, 6, 9, 0, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


def make_candle(t: datetime, *, symbol="XAUUSD", timeframe="1H", tick_volume=100,
                spread=20.0, base=2300.0) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        broker_time=t,
        time_utc=t,
        open=base,
        high=base + 5,
        low=base - 5,
        close=base + 2,
        tick_volume=tick_volume,
        spread=spread,
    )


def hourly_series(n: int, start: datetime = START) -> list[Candle]:
    return [make_candle(start + i * HOUR, base=2300.0 + i) for i in range(n)]


# ---------------------------------------------------------------------------
# Valid data passes
# ---------------------------------------------------------------------------

def test_valid_series_passes():
    report = DataValidator().validate_candles(hourly_series(5))
    assert report.status is ValidationStatus.VALID
    assert report.is_valid
    assert report.blocking_issues == []


def test_valid_series_with_freshness_and_spread_config_passes():
    candles = hourly_series(5)
    now = candles[-1].time_utc + timedelta(minutes=10)
    cfg = ValidationConfig(
        expected_symbol="XAUUSD",
        max_spread=50.0,
        max_staleness=timedelta(hours=1),
    )
    report = DataValidator(cfg).validate_candles(candles, now=now)
    assert report.status is ValidationStatus.VALID


# ---------------------------------------------------------------------------
# Empty / malformed input
# ---------------------------------------------------------------------------

def test_empty_input_is_no_trade():
    report = DataValidator().validate_candles([])
    assert report.status is ValidationStatus.NO_TRADE
    assert report.has_code(ValidationCode.EMPTY_INPUT)


# ---------------------------------------------------------------------------
# Missing candles
# ---------------------------------------------------------------------------

def test_missing_candle_detected():
    candles = hourly_series(5)
    del candles[2]  # drop one hour -> 2h gap
    report = DataValidator().validate_candles(candles)
    assert report.status is ValidationStatus.NO_TRADE
    assert report.has_code(ValidationCode.MISSING_CANDLES)


def test_gap_detection_can_be_disabled():
    candles = hourly_series(5)
    del candles[2]
    cfg = ValidationConfig(detect_gaps=False)
    report = DataValidator(cfg).validate_candles(candles)
    assert report.status is ValidationStatus.VALID


# ---------------------------------------------------------------------------
# Duplicates and timestamp ordering
# ---------------------------------------------------------------------------

def test_duplicate_timestamp_detected():
    candles = hourly_series(3)
    candles.append(make_candle(candles[-1].time_utc, base=2400.0))  # repeat last ts
    report = DataValidator().validate_candles(candles)
    assert report.status is ValidationStatus.NO_TRADE
    assert report.has_code(ValidationCode.DUPLICATE_TIMESTAMP)


def test_out_of_order_detected():
    candles = hourly_series(4)
    candles[2], candles[3] = candles[3], candles[2]  # swap to break order
    report = DataValidator().validate_candles(candles)
    assert report.status is ValidationStatus.NO_TRADE
    assert report.has_code(ValidationCode.NON_MONOTONIC)


def test_misaligned_interval_detected():
    candles = hourly_series(2)
    # Append a candle 90 minutes after the last (not a multiple of 1H).
    candles.append(make_candle(candles[-1].time_utc + timedelta(minutes=90)))
    report = DataValidator().validate_candles(candles)
    assert report.status is ValidationStatus.NO_TRADE
    assert report.has_code(ValidationCode.NON_MONOTONIC)


# ---------------------------------------------------------------------------
# Stale data and look-ahead
# ---------------------------------------------------------------------------

def test_stale_data_detected():
    candles = hourly_series(5)
    now = candles[-1].time_utc + timedelta(hours=6)
    cfg = ValidationConfig(max_staleness=timedelta(hours=2))
    report = DataValidator(cfg).validate_candles(candles, now=now)
    assert report.status is ValidationStatus.NO_TRADE
    assert report.has_code(ValidationCode.STALE_DATA)


def test_look_ahead_detected():
    candles = hourly_series(5)
    now = candles[2].time_utc  # candles 3 and 4 are in the future
    report = DataValidator().validate_candles(candles, now=now)
    assert report.status is ValidationStatus.NO_TRADE
    assert report.has_code(ValidationCode.LOOK_AHEAD)


def test_no_freshness_checks_without_now():
    candles = hourly_series(5)
    report = DataValidator(
        ValidationConfig(max_staleness=timedelta(minutes=1))
    ).validate_candles(candles)  # now=None -> stale/look-ahead skipped
    assert report.status is ValidationStatus.VALID


# ---------------------------------------------------------------------------
# Spread anomalies and zero volume
# ---------------------------------------------------------------------------

def test_spread_too_high_detected():
    candles = hourly_series(3)
    candles[1] = make_candle(candles[1].time_utc, spread=500.0, base=2301.0)
    cfg = ValidationConfig(max_spread=100.0)
    report = DataValidator(cfg).validate_candles(candles)
    assert report.status is ValidationStatus.NO_TRADE
    assert report.has_code(ValidationCode.SPREAD_TOO_HIGH)


def test_zero_volume_is_warning_by_default():
    candles = hourly_series(3)
    candles[1] = make_candle(candles[1].time_utc, tick_volume=0, base=2301.0)
    report = DataValidator().validate_candles(candles)
    assert report.status is ValidationStatus.VALID  # warning only
    assert report.has_code(ValidationCode.ZERO_VOLUME)
    assert len(report.warnings) == 1


def test_zero_volume_can_block():
    candles = hourly_series(3)
    candles[1] = make_candle(candles[1].time_utc, tick_volume=0, base=2301.0)
    cfg = ValidationConfig(block_on_zero_volume=True)
    report = DataValidator(cfg).validate_candles(candles)
    assert report.status is ValidationStatus.NO_TRADE
    assert report.has_code(ValidationCode.ZERO_VOLUME)


# ---------------------------------------------------------------------------
# Symbol / timeframe consistency
# ---------------------------------------------------------------------------

def test_mixed_symbols_detected():
    candles = hourly_series(3)
    candles[1] = make_candle(candles[1].time_utc, symbol="XAGUSD", base=2301.0)
    report = DataValidator().validate_candles(candles)
    assert report.status is ValidationStatus.NO_TRADE
    assert report.has_code(ValidationCode.MIXED_SYMBOLS)


def test_symbol_mismatch_against_expected():
    candles = hourly_series(3)  # all XAUUSD
    cfg = ValidationConfig(expected_symbol="EURUSD")
    report = DataValidator(cfg).validate_candles(candles)
    assert report.status is ValidationStatus.NO_TRADE
    assert report.has_code(ValidationCode.SYMBOL_MISMATCH)


def test_mixed_timeframes_detected():
    candles = hourly_series(2)
    candles.append(make_candle(candles[-1].time_utc + HOUR, timeframe="5M"))
    report = DataValidator().validate_candles(candles)
    assert report.status is ValidationStatus.NO_TRADE
    assert report.has_code(ValidationCode.MIXED_TIMEFRAMES)
