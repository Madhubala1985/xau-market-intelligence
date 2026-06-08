"""Tests for P3-003 liquidity sweep engine (true / false / no sweep)."""

from datetime import datetime, timedelta, timezone

from src.data.schemas import Candle
from src.liquidity import (
    LiquidityKind,
    LiquidityLevel,
    LiquiditySide,
    SweepEngine,
    SweepStatus,
)
from src.structure.market_structure import Bias

UTC = timezone.utc
T0 = datetime(2026, 6, 9, 0, 0, tzinfo=UTC)


def cc(i: int, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(
        symbol="XAUUSD",
        timeframe="1H",
        broker_time=T0 + i * timedelta(hours=1),
        time_utc=T0 + i * timedelta(hours=1),
        open=o,
        high=h,
        low=l,
        close=c,
        tick_volume=100,
    )


def buy_level(price: float, *, before_index: int = 0) -> LiquidityLevel:
    """A buy-side (high) liquidity level established before the series."""
    return LiquidityLevel(
        kind=LiquidityKind.PREV_DAY_HIGH,
        side=LiquiditySide.BUY_SIDE,
        price=price,
        time_utc=T0 - timedelta(hours=1),
    )


def sell_level(price: float) -> LiquidityLevel:
    return LiquidityLevel(
        kind=LiquidityKind.PREV_DAY_LOW,
        side=LiquiditySide.SELL_SIDE,
        price=price,
        time_utc=T0 - timedelta(hours=1),
    )


def engine() -> SweepEngine:
    return SweepEngine(swing_strength=1, confirm_window=3, displacement_factor=1.5)


# ---------------------------------------------------------------------------
# True sweep: take-out + close-back + displacement + bearish structure
# ---------------------------------------------------------------------------

def test_true_sweep_buyside():
    # Level rests at 100. A swing low at idx1 (95) gives structure to break.
    candles = [
        cc(0, 98, 99, 96, 98),
        cc(1, 98, 99, 95, 98),    # swing low 95
        cc(2, 98, 99, 97, 98),
        cc(3, 99.5, 100.5, 98, 98.2),  # SWEEP: wick > 100, closes back to 98.2
        cc(4, 98.0, 98.2, 93.0, 93.5),  # displacement down; close 93.5 < 95 -> bearish BOS
        cc(5, 93.5, 94, 92, 93),
        cc(6, 93, 93.5, 91, 92),
    ]
    events = engine().detect(candles, [buy_level(100.0)])
    assert len(events) == 1
    ev = events[0]
    assert ev.status is SweepStatus.TRUE_SWEEP
    assert ev.swept_side is LiquiditySide.BUY_SIDE
    assert ev.rejection_bias is Bias.BEARISH
    assert ev.sweep_index == 3
    assert ev.displacement_index == 4
    assert ev.structure_index == 4
    assert ev.confirmed_index == 4


def test_true_sweep_sellside():
    # Level rests at 100. A swing high at idx1 (105) gives structure to break up.
    candles = [
        cc(0, 102, 104, 101, 102),
        cc(1, 102, 105, 101, 102),   # swing high 105
        cc(2, 102, 104, 101, 102),
        cc(3, 101, 102, 99.5, 101.8),  # SWEEP: wick < 100, closes back to 101.8
        cc(4, 102, 107, 101.5, 106.5),  # displacement up; close 106.5 > 105 -> bullish BOS
        cc(5, 106, 108, 105, 107),
        cc(6, 107, 109, 106, 108),
    ]
    events = engine().detect(candles, [sell_level(100.0)])
    assert len(events) == 1
    ev = events[0]
    assert ev.status is SweepStatus.TRUE_SWEEP
    assert ev.swept_side is LiquiditySide.SELL_SIDE
    assert ev.rejection_bias is Bias.BULLISH


# ---------------------------------------------------------------------------
# False sweep: take-out + close-back but no displacement / no structure
# ---------------------------------------------------------------------------

def test_false_sweep_no_confirmation():
    candles = [
        cc(0, 98.5, 99, 98, 98.5),
        cc(1, 98.5, 99, 98, 98.5),
        cc(2, 98.5, 99, 98, 98.5),
        cc(3, 99, 100.5, 98, 98.5),   # SWEEP: wick > 100, closes back
        cc(4, 98.5, 99, 98, 98.5),    # weak follow-through (no displacement)
        cc(5, 98.5, 99, 98, 98.6),
        cc(6, 98.5, 99, 98, 98.5),    # window fully elapsed -> FALSE
    ]
    events = engine().detect(candles, [buy_level(100.0)])
    assert len(events) == 1
    assert events[0].status is SweepStatus.FALSE_SWEEP
    assert events[0].confirmed_index is None


# ---------------------------------------------------------------------------
# No sweep
# ---------------------------------------------------------------------------

def test_no_sweep_clean_breakout():
    # Wick takes 100 but price CLOSES above it (continuation) -> not a candidate.
    candles = [
        cc(0, 98.5, 99, 98, 98.5),
        cc(1, 98.5, 99, 98, 98.5),
        cc(2, 99, 99.8, 98.5, 99.5),  # high stays below 100 (not taken)
        cc(3, 99.5, 101, 99, 100.8),  # takes 100 and closes ABOVE -> breakout, not sweep
        cc(4, 100.8, 101.5, 100.5, 101.2),
    ]
    assert engine().detect(candles, [buy_level(100.0)]) == []


def test_no_sweep_level_untouched():
    candles = [cc(i, 98, 99, 97, 98) for i in range(5)]  # never reaches 100
    assert engine().detect(candles, [buy_level(100.0)]) == []


# ---------------------------------------------------------------------------
# No look-ahead / pending
# ---------------------------------------------------------------------------

def test_level_formed_after_candle_is_ignored():
    candles = [
        cc(0, 98, 99, 97, 98),
        cc(1, 99, 100.5, 98, 98.2),  # would sweep, but level is "newer"
    ]
    future_level = LiquidityLevel(
        kind=LiquidityKind.PREV_DAY_HIGH,
        side=LiquiditySide.BUY_SIDE,
        price=100.0,
        time_utc=T0 + timedelta(hours=5),  # established after both candles
    )
    assert engine().detect(candles, [future_level]) == []


def test_pending_before_window_elapses():
    # Candidate at idx3 but the series ends before the confirm window elapses
    # and before any displacement/structure -> PENDING, not FALSE.
    candles = [
        cc(0, 98.5, 99, 98, 98.5),
        cc(1, 98.5, 99, 98, 98.5),
        cc(2, 98.5, 99, 98, 98.5),
        cc(3, 99, 100.5, 98, 98.5),  # SWEEP candidate; no further candles
    ]
    events = engine().detect(candles, [buy_level(100.0)])
    assert len(events) == 1
    assert events[0].status is SweepStatus.PENDING


def test_each_level_consumed_once():
    candles = [
        cc(0, 98, 99, 96, 98),
        cc(1, 98, 99, 95, 98),
        cc(2, 98, 99, 97, 98),
        cc(3, 99.5, 100.5, 98, 98.2),   # first sweep of the level
        cc(4, 98.0, 98.2, 93.0, 93.5),
        cc(5, 99.5, 100.6, 98, 98.2),   # pokes 100 again -> must NOT re-emit
        cc(6, 93, 93.5, 91, 92),
    ]
    events = engine().detect(candles, [buy_level(100.0)])
    assert len(events) == 1  # the level is consumed by its first sweep
