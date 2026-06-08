"""Tests for P2-001 timeframe aggregation.

Covers the two required categories:
- aggregation correctness (OHLCV, alignment, volumes),
- no future leakage (forming bar withheld; bars never include later-period data).
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.data import (
    AggregationError,
    Candle,
    TimeframeAggregator,
    aggregate,
)
from src.data.enums import Timeframe

UTC = timezone.utc
PLUS2 = timezone(timedelta(hours=2))
START = datetime(2026, 6, 9, 10, 0, tzinfo=UTC)
MIN = timedelta(minutes=1)


def m1(i: int, *, symbol="XAUUSD", timeframe="1M", o=None, h=None, l=None, c=None,
       tick_volume=10, real_volume=None, broker_tz=UTC) -> Candle:
    """Build a 1-minute candle at START + i minutes with simple derived prices."""
    t = START + i * MIN
    base = 2300.0 + i
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        broker_time=t.astimezone(broker_tz),
        time_utc=t,
        open=base if o is None else o,
        high=(base + 2) if h is None else h,
        low=(base - 2) if l is None else l,
        close=(base + 1) if c is None else c,
        tick_volume=tick_volume,
        real_volume=real_volume,
    )


def minutes(n: int, **kw) -> list[Candle]:
    return [m1(i, **kw) for i in range(n)]


# ---------------------------------------------------------------------------
# Correctness
# ---------------------------------------------------------------------------

def test_1m_to_5m_basic_ohlcv():
    bars = aggregate(minutes(10), Timeframe.M5, drop_incomplete=False)
    assert len(bars) == 2
    first = bars[0]
    assert first.timeframe == "5M"
    assert first.time_utc == START                # aligned to :00
    assert first.open == minutes(10)[0].open       # open of first source bar
    assert first.close == minutes(10)[4].close     # close of last source bar in window
    assert first.high == max(c.high for c in minutes(10)[:5])
    assert first.low == min(c.low for c in minutes(10)[:5])
    assert first.tick_volume == sum(c.tick_volume for c in minutes(10)[:5])
    # Second window aligned to :05
    assert bars[1].time_utc == START + 5 * MIN


def test_aggregated_spread_is_none():
    bars = aggregate(minutes(5), Timeframe.M5, drop_incomplete=False)
    assert bars[0].spread is None


def test_real_volume_summed_when_all_present():
    src = [m1(i, real_volume=100) for i in range(5)]
    bars = aggregate(src, Timeframe.M5, drop_incomplete=False)
    assert bars[0].real_volume == 500


def test_real_volume_none_when_any_missing():
    src = [m1(i, real_volume=(100 if i != 2 else None)) for i in range(5)]
    bars = aggregate(src, Timeframe.M5, drop_incomplete=False)
    assert bars[0].real_volume is None


def test_broker_offset_preserved():
    src = minutes(5, broker_tz=PLUS2)
    bars = aggregate(src, Timeframe.M5, drop_incomplete=False)
    assert bars[0].broker_time.utcoffset() == timedelta(hours=2)
    assert bars[0].time_utc.utcoffset() == timedelta(0)
    assert bars[0].broker_time == bars[0].time_utc  # same instant


def test_1m_to_hourly_alignment():
    # 120 one-minute bars -> two 1H bars, aligned to the hour.
    bars = aggregate(minutes(120), Timeframe.H1, drop_incomplete=False)
    assert len(bars) == 2
    assert bars[0].time_utc == START
    assert bars[1].time_utc == START + timedelta(hours=1)


def test_daily_alignment_to_utc_midnight():
    day_start = datetime(2026, 6, 9, 0, 0, tzinfo=UTC)
    src = [
        Candle(
            symbol="XAUUSD", timeframe="1H",
            broker_time=day_start + timedelta(hours=h),
            time_utc=day_start + timedelta(hours=h),
            open=2300.0 + h, high=2305.0 + h, low=2295.0 + h, close=2301.0 + h,
            tick_volume=100,
        )
        for h in range(24)
    ]
    bars = aggregate(src, Timeframe.D1, drop_incomplete=False)
    assert len(bars) == 1
    assert bars[0].time_utc == day_start
    assert bars[0].open == 2300.0
    assert bars[0].close == 2301.0 + 23
    assert bars[0].tick_volume == 2400


def test_source_other_than_1m():
    # 12 five-minute bars -> one 1H bar.
    src = [
        Candle(
            symbol="XAUUSD", timeframe="5M",
            broker_time=START + i * timedelta(minutes=5),
            time_utc=START + i * timedelta(minutes=5),
            open=2300.0, high=2310.0, low=2290.0, close=2305.0, tick_volume=50,
        )
        for i in range(12)
    ]
    bars = aggregate(src, Timeframe.H1, drop_incomplete=False)
    assert len(bars) == 1
    assert bars[0].tick_volume == 600


# ---------------------------------------------------------------------------
# No future leakage
# ---------------------------------------------------------------------------

def test_aggregated_bar_excludes_next_window_data():
    src = minutes(10)
    # Spike the high of a bar in the SECOND window (minute 7).
    src[7] = m1(7, h=9999.0)
    bars = aggregate(src, Timeframe.M5, drop_incomplete=False)
    assert bars[0].high < 9999.0          # first window must not see the spike
    assert bars[1].high == 9999.0          # it belongs to the second window


def test_forming_bar_withheld_by_default_without_now():
    # 7 minutes -> window [10:00,10:05) complete, [10:05,10:10) still forming.
    bars = aggregate(minutes(7), Timeframe.M5)  # drop_incomplete=True, now=None
    assert len(bars) == 1
    assert bars[0].time_utc == START


def test_now_keeps_only_closed_windows():
    src = minutes(7)
    now = START + timedelta(minutes=7)  # second window not yet closed (ends 10:10)
    bars = aggregate(src, Timeframe.M5, now=now)
    assert len(bars) == 1
    assert bars[0].time_utc == START


def test_now_at_window_end_keeps_bar():
    src = minutes(5)
    now = START + timedelta(minutes=5)  # window [10:00,10:05) fully elapsed
    bars = aggregate(src, Timeframe.M5, now=now)
    assert len(bars) == 1
    assert bars[0].time_utc == START


def test_now_before_window_end_drops_bar():
    src = minutes(5)
    now = START + timedelta(minutes=4, seconds=59)
    bars = aggregate(src, Timeframe.M5, now=now)
    assert bars == []


def test_drop_incomplete_false_keeps_forming_bar():
    bars = aggregate(minutes(7), Timeframe.M5, drop_incomplete=False)
    assert len(bars) == 2  # includes the forming [10:05,10:10) bar


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def test_empty_returns_empty():
    assert aggregate([], Timeframe.M5) == []


def test_target_not_larger_than_source_raises():
    with pytest.raises(AggregationError):
        aggregate(minutes(5), Timeframe.M1, drop_incomplete=False)


def test_target_smaller_than_source_raises():
    src = [
        Candle(
            symbol="XAUUSD", timeframe="15M",
            broker_time=START + i * timedelta(minutes=15),
            time_utc=START + i * timedelta(minutes=15),
            open=2300.0, high=2310.0, low=2290.0, close=2305.0, tick_volume=50,
        )
        for i in range(4)
    ]
    with pytest.raises(AggregationError):
        aggregate(src, Timeframe.M5, drop_incomplete=False)


def test_mixed_symbols_raises():
    src = minutes(5)
    src[2] = m1(2, symbol="XAGUSD")
    with pytest.raises(AggregationError):
        aggregate(src, Timeframe.M5, drop_incomplete=False)


def test_mixed_timeframes_raises():
    src = minutes(5)
    src[2] = m1(2, timeframe="5M")
    with pytest.raises(AggregationError):
        aggregate(src, Timeframe.M5, drop_incomplete=False)


def test_out_of_order_raises():
    src = minutes(5)
    src[2], src[3] = src[3], src[2]
    with pytest.raises(AggregationError):
        aggregate(src, Timeframe.M5, drop_incomplete=False)


def test_duplicate_timestamp_raises():
    src = minutes(5)
    src[3] = m1(2)  # duplicate of minute 2's timestamp
    with pytest.raises(AggregationError):
        aggregate(src, Timeframe.M5, drop_incomplete=False)


def test_aggregator_class_matches_module_function():
    a = TimeframeAggregator().aggregate(minutes(5), Timeframe.M5, drop_incomplete=False)
    b = aggregate(minutes(5), Timeframe.M5, drop_incomplete=False)
    assert [c.model_dump() for c in a] == [c.model_dump() for c in b]
