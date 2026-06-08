"""Tests for P2-002 session / kill-zone engine.

Covers the two required categories:
- timestamp-to-session mapping (including overlap, rollover, low-liquidity, weekend),
- session highs/lows tracking (running, no look-ahead, and per-occurrence).
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.data import (
    Candle,
    SessionConfig,
    SessionEngine,
    SessionSegment,
)
from src.data.enums import SessionType

UTC = timezone.utc


def at(year=2026, month=6, day=9, hour=0, minute=0) -> datetime:
    # 2026-06-09 is a Tuesday (a normal trading day).
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def candle(t: datetime, *, high, low, symbol="XAUUSD", timeframe="1H") -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        broker_time=t,
        time_utc=t,
        open=(high + low) / 2,
        high=high,
        low=low,
        close=(high + low) / 2,
        tick_volume=100,
    )


# ---------------------------------------------------------------------------
# Timestamp -> session mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "hour,expected",
    [
        (0, SessionType.ASIAN),
        (7, SessionType.ASIAN),
        (8, SessionType.LONDON),
        (12, SessionType.LONDON),
        (13, SessionType.LONDON_NY_OVERLAP),
        (15, SessionType.LONDON_NY_OVERLAP),
        (16, SessionType.NEW_YORK),
        (20, SessionType.NEW_YORK),
        (21, SessionType.ROLLOVER),
        (22, SessionType.LOW_LIQUIDITY),
        (23, SessionType.LOW_LIQUIDITY),
    ],
)
def test_classify_by_hour(hour, expected):
    assert SessionEngine().classify(at(hour=hour)) is expected


def test_boundaries_are_half_open():
    eng = SessionEngine()
    # 08:00 is London (inclusive start), 07:59 is still Asian.
    assert eng.classify(at(hour=7, minute=59)) is SessionType.ASIAN
    assert eng.classify(at(hour=8, minute=0)) is SessionType.LONDON
    # 16:00 is New York, 15:59 is still overlap.
    assert eng.classify(at(hour=15, minute=59)) is SessionType.LONDON_NY_OVERLAP
    assert eng.classify(at(hour=16, minute=0)) is SessionType.NEW_YORK


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError):
        SessionEngine().classify(datetime(2026, 6, 9, 10, 0))


def test_non_utc_timestamp_normalized():
    eng = SessionEngine()
    plus2 = timezone(timedelta(hours=2))
    # 10:00 at +02:00 == 08:00 UTC -> London.
    t = datetime(2026, 6, 9, 10, 0, tzinfo=plus2)
    assert eng.classify(t) is SessionType.LONDON


# ---------------------------------------------------------------------------
# Weekend / closed market
# ---------------------------------------------------------------------------

def test_saturday_is_closed():
    # 2026-06-13 is a Saturday.
    assert SessionEngine().classify(at(day=13, hour=12)) is SessionType.CLOSED
    assert SessionEngine().is_market_open(at(day=13, hour=12)) is False


def test_friday_after_close_is_closed():
    # 2026-06-12 is a Friday; close defaults to 21:00 UTC.
    eng = SessionEngine()
    assert eng.classify(at(day=12, hour=20)) is SessionType.NEW_YORK
    assert eng.classify(at(day=12, hour=21)) is SessionType.CLOSED


def test_sunday_before_open_is_closed_then_opens():
    # 2026-06-14 is a Sunday; open defaults to 22:00 UTC.
    eng = SessionEngine()
    assert eng.classify(at(day=14, hour=21)) is SessionType.CLOSED
    assert eng.classify(at(day=14, hour=22)) is SessionType.LOW_LIQUIDITY


# ---------------------------------------------------------------------------
# Flags and bounds
# ---------------------------------------------------------------------------

def test_kill_zone_and_tradeable_flags():
    eng = SessionEngine()
    london = eng.session_state(at(hour=9))
    assert london.session is SessionType.LONDON
    assert london.is_kill_zone is True
    assert london.is_tradeable is True

    low_liq = eng.session_state(at(hour=23))
    assert low_liq.is_kill_zone is False
    assert low_liq.is_tradeable is False


def test_segment_bounds():
    start, end = SessionEngine().segment_bounds(at(hour=14))  # overlap 13-16
    assert start == at(hour=13)
    assert end == at(hour=16)


def test_closed_bounds_span_full_day():
    start, end = SessionEngine().segment_bounds(at(day=13, hour=12))  # Saturday
    assert start == at(day=13, hour=0)
    assert end == at(day=14, hour=0)


def test_session_state_carries_levels():
    state = SessionEngine().session_state(at(hour=9), high=2350.0, low=2310.0)
    assert state.session_high == 2350.0
    assert state.session_low == 2310.0


# ---------------------------------------------------------------------------
# Session highs/lows tracking
# ---------------------------------------------------------------------------

def test_track_levels_per_session():
    eng = SessionEngine()
    candles = [
        candle(at(hour=1), high=2310, low=2300),   # Asian
        candle(at(hour=3), high=2320, low=2295),   # Asian (new extremes)
        candle(at(hour=9), high=2330, low=2305),   # London
        candle(at(hour=11), high=2325, low=2290),  # London (new low)
        candle(at(hour=17), high=2340, low=2315),  # New York
    ]
    levels = eng.track_session_levels(candles)
    assert len(levels) == 3

    asian, london, ny = levels
    assert asian.session is SessionType.ASIAN
    assert (asian.high, asian.low) == (2320, 2295)
    assert asian.candle_count == 2

    assert london.session is SessionType.LONDON
    assert (london.high, london.low) == (2330, 2290)

    assert ny.session is SessionType.NEW_YORK
    assert (ny.high, ny.low) == (2340, 2315)


def test_same_session_on_different_days_are_separate_occurrences():
    eng = SessionEngine()
    candles = [
        candle(at(day=9, hour=9), high=2330, low=2305),
        candle(at(day=10, hour=9), high=2400, low=2380),  # next day's London
    ]
    levels = eng.track_session_levels(candles)
    assert len(levels) == 2
    assert levels[0].start_utc.day == 9
    assert levels[1].start_utc.day == 10


def test_annotate_running_levels_no_lookahead():
    eng = SessionEngine()
    candles = [
        candle(at(hour=1), high=2310, low=2300),
        candle(at(hour=2), high=2320, low=2295),
        candle(at(hour=3), high=2315, low=2290),
    ]
    states = eng.annotate(candles)
    # Running high/low reflect only candles seen so far (no future leakage).
    assert (states[0].session_high, states[0].session_low) == (2310, 2300)
    assert (states[1].session_high, states[1].session_low) == (2320, 2295)
    assert (states[2].session_high, states[2].session_low) == (2320, 2290)
    assert all(s.session is SessionType.ASIAN for s in states)


def test_annotate_resets_on_new_session():
    eng = SessionEngine()
    candles = [
        candle(at(hour=2), high=2320, low=2295),   # Asian
        candle(at(hour=9), high=2330, low=2310),   # London -> reset
    ]
    states = eng.annotate(candles)
    assert (states[1].session_high, states[1].session_low) == (2330, 2310)


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def test_segments_with_gap_rejected():
    with pytest.raises(ValueError):
        SessionConfig(
            segments=(
                SessionSegment(SessionType.ASIAN, 0, 8 * 60),
                SessionSegment(SessionType.LONDON, 9 * 60, 24 * 60),  # gap 8h-9h
            )
        )


def test_segments_not_covering_day_rejected():
    with pytest.raises(ValueError):
        SessionConfig(
            segments=(SessionSegment(SessionType.ASIAN, 0, 12 * 60),)  # ends at 12:00
        )
