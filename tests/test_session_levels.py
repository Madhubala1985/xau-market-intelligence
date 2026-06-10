"""Tests for the Asian range + London/NY expansion context (INTELLIGENCE-002)."""

from datetime import datetime, timedelta, timezone

import pytest

from src.data.schemas import Candle
from src.data.session_levels import AsianRangeEngine

UTC = timezone.utc
DAY = datetime(2026, 6, 9, 0, 0, tzinfo=UTC)  # Tuesday, 00:00 UTC
ENGINE = AsianRangeEngine()


def candle(minutes, o, h, l, c):
    t = DAY + timedelta(minutes=minutes)
    return Candle(symbol="XAUUSD", timeframe="5M", broker_time=t, time_utc=t,
                  open=o, high=h, low=l, close=c, tick_volume=100)


def asian_session(high=105.0, low=100.0):
    """An 8h Asian session ranging between low and high."""
    out = []
    for i in range(0, 8 * 12):  # 96 x M5
        mid_low = low + 0.5
        mid_high = high - 0.5
        out.append(candle(i * 5, mid_low, mid_high + 0.5, mid_low - 0.5,
                          mid_high))
    return out


def london(minutes_offset, o, h, l, c):
    return candle(8 * 60 + minutes_offset, o, h, l, c)


def test_asian_range_detected_with_levels():
    candles = asian_session()
    ctx = ENGINE.analyze(candles, DAY + timedelta(hours=9))
    assert ctx.known
    assert ctx.high == pytest.approx(105.0)
    assert ctx.low == pytest.approx(100.0)
    assert ctx.position == "INSIDE"
    assert ctx.swept == "NONE"


def test_london_sweep_of_asian_high_is_detected():
    candles = asian_session()
    candles.append(london(5, 104.5, 105.8, 104.0, 104.2))  # takes the high
    ctx = ENGINE.analyze(candles, DAY + timedelta(hours=8, minutes=10))
    assert ctx.swept == "HIGH"
    assert ctx.position == "INSIDE"  # rejected back into the range (trap)


def test_london_expansion_below_the_range():
    candles = asian_session()
    px = 100.0
    for i in range(12):  # an hour of bearish expansion below the range
        candles.append(london(5 + i * 5, px, px + 0.3, px - 1.0, px - 0.9))
        px -= 0.9
    ctx = ENGINE.analyze(candles, DAY + timedelta(hours=9, minutes=10))
    assert ctx.swept in ("LOW", "BOTH")
    assert ctx.position == "BELOW"
    assert ctx.expanding is True
    assert ctx.expansion_ratio >= 1.2


def test_missing_asian_session_is_honestly_unknown():
    # Feed only contains London candles (service started mid-day, short feed).
    candles = [london(i * 5, 100, 101, 99, 100.5) for i in range(20)]
    ctx = ENGINE.analyze(candles, DAY + timedelta(hours=10))
    assert ctx.known is False
    assert ctx.high is None and ctx.low is None
    assert "not fabricated" in ctx.reason


def test_naive_now_is_rejected():
    with pytest.raises(ValueError):
        ENGINE.analyze(asian_session(), datetime(2026, 6, 9, 9, 0))


def test_context_serializes():
    d = ENGINE.analyze(asian_session(), DAY + timedelta(hours=9)).to_dict()
    assert d["known"] is True and d["swept"] == "NONE"
