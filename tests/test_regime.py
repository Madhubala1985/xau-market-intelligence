"""Tests for P4-002 regime engine (regime cases)."""

from datetime import datetime, timedelta, timezone

from src.data.schemas import Candle
from src.regime import Regime, RegimeEngine

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)


def c(i: int, o: float, h: float, l: float, cl: float) -> Candle:
    return Candle(
        symbol="XAUUSD",
        timeframe="1H",
        broker_time=T0 + i * timedelta(hours=1),
        time_utc=T0 + i * timedelta(hours=1),
        open=o,
        high=h,
        low=l,
        close=cl,
        tick_volume=100,
    )


def engine() -> RegimeEngine:
    return RegimeEngine(swing_strength=1)


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------

def test_trend_uptrend():
    candles = [
        c(0, 9, 10, 8, 9),
        c(1, 9, 12, 9, 11),       # swing high 12
        c(2, 11, 11, 9.5, 10),
        c(3, 10, 13, 10, 12.8),   # BOS up
        c(4, 12.5, 12.5, 10.5, 11),
        c(5, 11, 15, 11, 14.5),   # BOS up
        c(6, 14.5, 14.5, 13, 14),
    ]
    r = engine().classify(candles)
    assert r.regime is Regime.TREND
    assert r.bos_count >= 1
    assert r.flips == 0


# ---------------------------------------------------------------------------
# Choppy
# ---------------------------------------------------------------------------

def test_choppy_alternating_structure():
    candles = [
        c(0, 9, 10, 8, 9),
        c(1, 9, 12, 9, 11),
        c(2, 11, 11.5, 7, 8),
        c(3, 8, 13, 8, 12.8),     # bull break
        c(4, 12.8, 13.2, 6, 6.5),  # bear break
        c(5, 6.5, 7, 5, 6),
        c(6, 6, 15, 6, 14.5),      # bull break
        c(7, 14.5, 15, 13, 14),
    ]
    r = engine().classify(candles)
    assert r.regime is Regime.CHOPPY
    assert r.flips >= 2


# ---------------------------------------------------------------------------
# Expansion / compression
# ---------------------------------------------------------------------------

def test_expansion_widening_volatility():
    candles = [
        c(0, 100, 100.5, 99.5, 100),
        c(1, 100, 100.6, 99.4, 100),
        c(2, 100, 100.5, 99.5, 100),
        c(3, 100, 102, 98, 100),
        c(4, 100, 103, 97, 100),
        c(5, 100, 104, 96, 100),
        c(6, 100, 103, 97, 100),
    ]
    r = engine().classify(candles)
    assert r.regime is Regime.EXPANSION
    assert r.volatility_ratio >= 1.5


def test_compression_contracting_volatility():
    candles = [
        c(0, 100, 103, 97, 100),
        c(1, 100, 102.5, 97.5, 100),
        c(2, 100, 102, 98, 100),
        c(3, 100, 101, 99, 100),
        c(4, 100, 100.8, 99.2, 100),
        c(5, 100, 100.6, 99.4, 100),
        c(6, 100, 100.5, 99.5, 100),
    ]
    r = engine().classify(candles)
    assert r.regime is Regime.COMPRESSION
    assert r.volatility_ratio <= 0.67


# ---------------------------------------------------------------------------
# Range
# ---------------------------------------------------------------------------

def test_range_bounded_stable():
    candles = [
        c(0, 100, 101, 99, 100.5),
        c(1, 100.5, 101, 99, 99.5),
        c(2, 99.5, 101, 99, 100.5),
        c(3, 100.5, 101, 99, 99.5),
        c(4, 99.5, 101, 99, 100.5),
        c(5, 100.5, 101, 99, 99.5),
        c(6, 99.5, 101, 99, 100.5),
    ]
    r = engine().classify(candles)
    assert r.regime is Regime.RANGE
    assert r.bos_count == 0


# ---------------------------------------------------------------------------
# News-risk and no-trade
# ---------------------------------------------------------------------------

def test_news_risk_flag_overrides():
    candles = [c(i, 100, 101, 99, 100.5) for i in range(7)]
    r = engine().classify(candles, news_risk=True)
    assert r.regime is Regime.NEWS_RISK


def test_no_trade_insufficient_data():
    candles = [c(i, 100, 101, 99, 100) for i in range(3)]  # below min_candles
    r = engine().classify(candles)
    assert r.regime is Regime.NO_TRADE
    assert "insufficient" in r.reason
