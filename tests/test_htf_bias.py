"""Tests for P4-001 Daily and 4H bias engine (bias cases)."""

from datetime import datetime, timedelta, timezone

from src.data.schemas import Candle
from src.regime import HtfBias, HtfBiasEngine
from src.structure.market_structure import Bias

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)


def candle(i: int, o: float, h: float, l: float, c: float, tf: str) -> Candle:
    return Candle(
        symbol="XAUUSD",
        timeframe=tf,
        broker_time=T0 + i * timedelta(hours=4),
        time_utc=T0 + i * timedelta(hours=4),
        open=o,
        high=h,
        low=l,
        close=c,
        tick_volume=100,
    )


def bullish_series(tf: str) -> list[Candle]:
    # swing high 12 (idx1); close above it (idx3) -> bullish BOS -> final BULLISH.
    return [
        candle(0, 9, 10, 8, 9, tf),
        candle(1, 9, 12, 9, 11, tf),
        candle(2, 11, 11, 9.5, 10, tf),
        candle(3, 10, 13, 10, 12.8, tf),
        candle(4, 12.8, 13.5, 12.5, 13.2, tf),
    ]


def bearish_series(tf: str) -> list[Candle]:
    # swing low 8 (idx1); close below it (idx3) -> bearish BOS -> final BEARISH.
    return [
        candle(0, 11, 12, 10, 11, tf),
        candle(1, 11, 11.5, 8, 9, tf),
        candle(2, 9, 11, 9, 10, tf),
        candle(3, 10, 10.2, 7, 7.2, tf),
        candle(4, 7.2, 7.5, 6, 6.5, tf),
    ]


def neutral_series(tf: str) -> list[Candle]:
    # ranging, no structure break -> NEUTRAL.
    return [candle(i, 10, 10.2, 9.8, 10.0, tf) for i in range(5)]


def engine() -> HtfBiasEngine:
    return HtfBiasEngine(swing_strength=1)


# ---------------------------------------------------------------------------
# Component structure bias sanity (the building block)
# ---------------------------------------------------------------------------

def test_component_series_biases():
    from src.structure.market_structure import MarketStructureEngine

    ms = MarketStructureEngine(strength=1)
    assert ms.analyze(bullish_series("1D")).final_bias is Bias.BULLISH
    assert ms.analyze(bearish_series("1D")).final_bias is Bias.BEARISH
    assert ms.analyze(neutral_series("1D")).final_bias is Bias.NEUTRAL


# ---------------------------------------------------------------------------
# Aligned biases
# ---------------------------------------------------------------------------

def test_daily_and_h4_bullish():
    r = engine().classify(bullish_series("1D"), bullish_series("4H"))
    assert r.bias is HtfBias.BULLISH
    assert r.daily_bias is Bias.BULLISH
    assert r.h4_bias is Bias.BULLISH


def test_daily_and_h4_bearish():
    r = engine().classify(bearish_series("1D"), bearish_series("4H"))
    assert r.bias is HtfBias.BEARISH


# ---------------------------------------------------------------------------
# Daily leads when 4H is neutral
# ---------------------------------------------------------------------------

def test_daily_bullish_h4_neutral_is_bullish():
    r = engine().classify(bullish_series("1D"), neutral_series("4H"))
    assert r.bias is HtfBias.BULLISH


def test_daily_bearish_h4_neutral_is_bearish():
    r = engine().classify(bearish_series("1D"), neutral_series("4H"))
    assert r.bias is HtfBias.BEARISH


# ---------------------------------------------------------------------------
# Conflict -> NO_TRADE
# ---------------------------------------------------------------------------

def test_conflict_bullish_daily_bearish_h4():
    r = engine().classify(bullish_series("1D"), bearish_series("4H"))
    assert r.bias is HtfBias.NO_TRADE
    assert "conflict" in r.reason


def test_conflict_bearish_daily_bullish_h4():
    r = engine().classify(bearish_series("1D"), bullish_series("4H"))
    assert r.bias is HtfBias.NO_TRADE


# ---------------------------------------------------------------------------
# Neutral and insufficient data
# ---------------------------------------------------------------------------

def test_daily_neutral_is_neutral():
    r = engine().classify(neutral_series("1D"), bullish_series("4H"))
    assert r.bias is HtfBias.NEUTRAL


def test_missing_daily_is_no_trade():
    r = engine().classify([], bullish_series("4H"))
    assert r.bias is HtfBias.NO_TRADE
    assert r.daily_bias is None
    assert "insufficient daily data" in r.reason


def test_daily_bullish_missing_h4_is_bullish():
    r = engine().classify(bullish_series("1D"), [])
    assert r.bias is HtfBias.BULLISH
    assert r.h4_bias is None
