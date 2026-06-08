"""Tests for P3-002 liquidity map engine (known examples)."""

from datetime import datetime, timedelta, timezone

from src.data.schemas import Candle
from src.liquidity import (
    LiquidityKind,
    LiquidityMap,
    LiquidityMapEngine,
    LiquiditySide,
)

UTC = timezone.utc


def ch(t: datetime, high: float, low: float) -> Candle:
    close = (high + low) / 2
    return Candle(
        symbol="XAUUSD",
        timeframe="1H",
        broker_time=t,
        time_utc=t,
        open=close,
        high=high,
        low=low,
        close=close,
        tick_volume=100,
    )


def hours(day=9, n=0):
    return datetime(2026, 6, day, 0, 0, tzinfo=UTC) + n * timedelta(hours=1)


# ---------------------------------------------------------------------------
# Swing levels and side classification
# ---------------------------------------------------------------------------

def test_swing_levels_and_sides():
    candles = [
        ch(hours(n=0), 10, 8),
        ch(hours(n=1), 12, 9),   # swing high 12
        ch(hours(n=2), 11, 7),   # swing low 7
        ch(hours(n=3), 13, 9),
    ]
    m = LiquidityMapEngine(swing_strength=1).build(candles)
    highs = m.of_kind(LiquidityKind.SWING_HIGH)
    lows = m.of_kind(LiquidityKind.SWING_LOW)
    assert any(l.price == 12 and l.side is LiquiditySide.BUY_SIDE for l in highs)
    assert any(l.price == 7 and l.side is LiquiditySide.SELL_SIDE for l in lows)
    # Buy-side helper returns the swing high; sell-side returns the swing low.
    assert any(l.kind is LiquidityKind.SWING_HIGH for l in m.buy_side())
    assert any(l.kind is LiquidityKind.SWING_LOW for l in m.sell_side())


# ---------------------------------------------------------------------------
# Equal highs / lows
# ---------------------------------------------------------------------------

def test_equal_highs_detected():
    candles = [
        ch(hours(n=0), 2340.0, 2330.0),
        ch(hours(n=1), 2350.00, 2338.0),  # swing high A
        ch(hours(n=2), 2342.0, 2334.0),   # dip (swing low)
        ch(hours(n=3), 2350.05, 2338.0),  # swing high B (~equal to A)
        ch(hours(n=4), 2341.0, 2333.0),
    ]
    m = LiquidityMapEngine(swing_strength=1, equal_tolerance=0.1).build(candles)
    equal_highs = m.of_kind(LiquidityKind.EQUAL_HIGHS)
    assert len(equal_highs) == 1
    lvl = equal_highs[0]
    assert lvl.touches == 2
    assert lvl.side is LiquiditySide.BUY_SIDE
    assert lvl.price == 2350.05  # representative = top of the equal cluster
    assert m.of_kind(LiquidityKind.EQUAL_LOWS) == []


def test_equal_highs_not_detected_when_outside_tolerance():
    candles = [
        ch(hours(n=0), 2340.0, 2330.0),
        ch(hours(n=1), 2350.0, 2338.0),
        ch(hours(n=2), 2342.0, 2334.0),
        ch(hours(n=3), 2355.0, 2338.0),  # 5.0 apart -> not equal at tol 0.1
        ch(hours(n=4), 2341.0, 2333.0),
    ]
    m = LiquidityMapEngine(swing_strength=1, equal_tolerance=0.1).build(candles)
    assert m.of_kind(LiquidityKind.EQUAL_HIGHS) == []


# ---------------------------------------------------------------------------
# Session highs / lows
# ---------------------------------------------------------------------------

def test_session_levels():
    # 2026-06-09 is a Tuesday. Asian (00-08) and London (08-13) UTC.
    candles = [
        ch(hours(day=9, n=1), 2310, 2300),  # Asian
        ch(hours(day=9, n=3), 2320, 2295),  # Asian (extremes)
        ch(hours(day=9, n=9), 2330, 2305),  # London
        ch(hours(day=9, n=11), 2325, 2290),  # London (new low)
    ]
    m = LiquidityMapEngine(swing_strength=1).build(candles)
    sess_highs = m.of_kind(LiquidityKind.SESSION_HIGH)
    sess_lows = m.of_kind(LiquidityKind.SESSION_LOW)

    asian_high = next(l for l in sess_highs if l.label == "ASIAN")
    london_low = next(l for l in sess_lows if l.label == "LONDON")
    assert asian_high.price == 2320
    assert asian_high.side is LiquiditySide.BUY_SIDE
    assert london_low.price == 2290
    assert london_low.side is LiquiditySide.SELL_SIDE


# ---------------------------------------------------------------------------
# Previous day / week
# ---------------------------------------------------------------------------

def test_previous_day_levels():
    candles = [
        ch(hours(day=9, n=2), 2330, 2310),   # day 1 (2026-06-09)
        ch(hours(day=9, n=6), 2345, 2305),   # day 1 high/low extremes
        ch(hours(day=10, n=2), 2400, 2380),  # day 2 (current) -> previous = day 1
    ]
    m = LiquidityMapEngine(swing_strength=1).build(candles)
    pdh = m.of_kind(LiquidityKind.PREV_DAY_HIGH)
    pdl = m.of_kind(LiquidityKind.PREV_DAY_LOW)
    assert pdh and pdh[0].price == 2345
    assert pdh[0].side is LiquiditySide.BUY_SIDE
    assert pdl and pdl[0].price == 2305
    assert pdl[0].side is LiquiditySide.SELL_SIDE


def test_previous_week_levels():
    # 2026-06-05 is a Friday (prior ISO week); 2026-06-09 is the following week.
    candles = [
        ch(hours(day=5, n=2), 2200, 2180),   # previous week
        ch(hours(day=5, n=6), 2250, 2150),   # previous week extremes
        ch(hours(day=9, n=2), 2400, 2380),   # current week
    ]
    m = LiquidityMapEngine(swing_strength=1).build(candles)
    pwh = m.of_kind(LiquidityKind.PREV_WEEK_HIGH)
    pwl = m.of_kind(LiquidityKind.PREV_WEEK_LOW)
    assert pwh and pwh[0].price == 2250
    assert pwl and pwl[0].price == 2150


def test_no_previous_period_with_single_day():
    candles = [ch(hours(day=9, n=h), 2300 + h, 2290 + h) for h in range(4)]
    m = LiquidityMapEngine(swing_strength=1).build(candles)
    assert m.of_kind(LiquidityKind.PREV_DAY_HIGH) == []
    assert m.of_kind(LiquidityKind.PREV_WEEK_HIGH) == []


# ---------------------------------------------------------------------------
# Empty input and no look-ahead
# ---------------------------------------------------------------------------

def test_empty_input():
    assert LiquidityMapEngine().build([]) == LiquidityMap(())


def test_no_lookahead_prefix_excludes_future_spike():
    candles = [
        ch(hours(n=0), 10, 8),
        ch(hours(n=1), 12, 9),    # swing high 12
        ch(hours(n=2), 11, 7),    # swing low 7
        ch(hours(n=3), 13, 9),
        ch(hours(n=4), 9999, 5),  # future spike
    ]
    prefix = LiquidityMapEngine(swing_strength=1).build(candles[:4])
    # No level in the prefix map references the future spike price.
    assert all(lvl.price != 9999 for lvl in prefix.levels)
