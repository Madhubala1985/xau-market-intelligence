"""Tests for the gold volatility safety classifier (INTELLIGENCE-002)."""

from datetime import datetime, timedelta, timezone

from src.data.schemas import Candle
from src.regime.volatility_classifier import (
    VolatilityClassifier,
    VolatilityState,
)

UTC = timezone.utc
T0 = datetime(2026, 6, 9, 9, 0, tzinfo=UTC)
CLF = VolatilityClassifier()


def candle(i, o, h, l, c):
    t = T0 + i * timedelta(minutes=5)
    return Candle(symbol="XAUUSD", timeframe="5M", broker_time=t, time_utc=t,
                  open=o, high=h, low=l, close=c, tick_volume=100)


def calm(n, base=100.0):
    """Steady candles: range 1.0, clean bodies."""
    return [candle(i, base, base + 0.7, base - 0.3, base + 0.5)
            for i in range(n)]


def test_normal_conditions():
    a = CLF.classify(calm(30))
    assert a.state is VolatilityState.NORMAL
    assert a.dangerous is False


def test_single_spike_is_dangerous():
    candles = calm(29)
    candles.append(candle(29, 100, 103.0, 97.0, 99.0))  # 6x the median range
    a = CLF.classify(candles)
    assert a.state is VolatilityState.DANGEROUS_SPIKE
    assert a.dangerous is True


def test_news_like_shock_burst_blocks():
    candles = calm(25)
    # Five huge alternating candles (news behavior), each below the
    # single-spike threshold so the burst itself is what classifies.
    for i, up in enumerate([True, False, True, False, True]):
        o, c = (99.5, 102.0) if up else (102.0, 99.5)
        candles.append(candle(25 + i, o, 102.4, 99.1, c))
    a = CLF.classify(candles)
    assert a.state is VolatilityState.NEWS_LIKE_SHOCK
    assert a.dangerous is True


def test_spread_blowout_without_volatility_is_a_mismatch():
    a = CLF.classify(calm(30), spread_ratio=0.85)
    assert a.state is VolatilityState.SPREAD_MISMATCH
    assert a.dangerous is True
    assert "liquidity problem" in a.reason


def test_expansion_is_tradeable_not_dangerous():
    candles = calm(25)
    # Recent candles ~1.7x the baseline range with CLEAN bodies.
    for i in range(5):
        candles.append(candle(25 + i, 100.0, 101.6, 99.9, 101.5))
    a = CLF.classify(candles, spread_ratio=0.2)
    assert a.state is VolatilityState.EXPANSION
    assert a.dangerous is False


def test_unstable_stops_blocks():
    candles = calm(25)
    # ATR doubling with wick-dominated candles: no rational stop distance.
    for i in range(5):
        candles.append(candle(25 + i, 100.0, 101.9, 98.6, 100.1))
    a = CLF.classify(candles)
    assert a.state is VolatilityState.UNSTABLE_STOPS
    assert a.dangerous is True


def test_assessment_serializes():
    d = CLF.classify(calm(30)).to_dict()
    assert d["state"] == "NORMAL"
    assert d["dangerous"] is False
