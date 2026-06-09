"""Tests for P5-002 gold futures confirmation layer.

Required categories:
- confirmation boosts/reduces confidence,
- missing futures data does not break the core system.
"""

import dataclasses
from datetime import datetime, timedelta, timezone

from src.data.schemas import Candle
from src.orderflow import (
    FuturesAlignment,
    FuturesConfirmation,
    FuturesConfirmationEngine,
)
from src.structure.market_structure import Bias

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)


def candle(i: int, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(
        symbol="GC",  # gold futures
        timeframe="1H",
        broker_time=T0 + i * timedelta(hours=1),
        time_utc=T0 + i * timedelta(hours=1),
        open=o,
        high=h,
        low=l,
        close=c,
        tick_volume=100,
    )


def bullish_futures() -> list[Candle]:
    # swing high 12 (idx1); close above it (idx3) -> bullish BOS -> final BULLISH.
    return [
        candle(0, 9, 10, 8, 9),
        candle(1, 9, 12, 9, 11),
        candle(2, 11, 11, 9.5, 10),
        candle(3, 10, 13, 10, 12.8),
        candle(4, 12.8, 13.5, 12.5, 13.2),
        candle(5, 13.2, 14, 13, 13.8),
    ]


def bearish_futures() -> list[Candle]:
    return [
        candle(0, 11, 12, 10, 11),
        candle(1, 11, 11.5, 8, 9),
        candle(2, 9, 11, 9, 10),
        candle(3, 10, 10.2, 7, 7.2),
        candle(4, 7.2, 7.5, 6, 6.5),
        candle(5, 6.5, 7, 5.5, 6.0),
    ]


def neutral_futures() -> list[Candle]:
    return [candle(i, 10, 10.2, 9.8, 10.0) for i in range(6)]


def engine() -> FuturesConfirmationEngine:
    return FuturesConfirmationEngine(swing_strength=1)


# ---------------------------------------------------------------------------
# Confirmation boosts / reduces confidence
# ---------------------------------------------------------------------------

def test_aligned_futures_boosts_confidence():
    r = engine().confirm(Bias.BULLISH, bullish_futures())
    assert r.alignment is FuturesAlignment.ALIGNED
    assert r.futures_bias is Bias.BULLISH
    assert r.confidence_adjustment > 0
    assert r.uncertainty_adjustment == 0


def test_conflicting_futures_reduces_confidence():
    r = engine().confirm(Bias.BULLISH, bearish_futures())
    assert r.alignment is FuturesAlignment.CONFLICT
    assert r.futures_bias is Bias.BEARISH
    assert r.confidence_adjustment < 0
    assert r.uncertainty_adjustment > 0


def test_aligned_bearish():
    r = engine().confirm(Bias.BEARISH, bearish_futures())
    assert r.alignment is FuturesAlignment.ALIGNED
    assert r.confidence_adjustment > 0


def test_neutral_futures_no_change():
    r = engine().confirm(Bias.BULLISH, neutral_futures())
    assert r.alignment is FuturesAlignment.NEUTRAL
    assert r.confidence_adjustment == 0
    assert r.uncertainty_adjustment == 0


def test_neutral_spot_no_change():
    r = engine().confirm(Bias.NEUTRAL, bullish_futures())
    assert r.alignment is FuturesAlignment.NEUTRAL
    assert r.confidence_adjustment == 0


# ---------------------------------------------------------------------------
# Missing futures data does not break the core system
# ---------------------------------------------------------------------------

def test_missing_futures_none_is_unavailable():
    r = engine().confirm(Bias.BULLISH, None)
    assert r.alignment is FuturesAlignment.UNAVAILABLE
    assert r.futures_bias is None
    assert r.confidence_adjustment == 0
    assert r.uncertainty_adjustment == 0
    assert "unavailable" in r.note


def test_empty_futures_is_unavailable():
    r = engine().confirm(Bias.BEARISH, [])
    assert r.alignment is FuturesAlignment.UNAVAILABLE


def test_too_short_futures_is_unavailable():
    r = engine().confirm(Bias.BULLISH, bullish_futures()[:3])  # below min_candles
    assert r.alignment is FuturesAlignment.UNAVAILABLE
    assert r.confidence_adjustment == 0


# ---------------------------------------------------------------------------
# No direct trade signal from futures alone
# ---------------------------------------------------------------------------

def test_futures_is_never_a_trade_signal():
    r = engine().confirm(Bias.BULLISH, bullish_futures())
    assert r.is_trade_signal is False


def test_result_exposes_no_trade_decision_fields():
    field_names = {f.name for f in dataclasses.fields(FuturesConfirmation)}
    forbidden = {"direction", "signal", "order", "entry", "side", "action", "trade"}
    assert field_names.isdisjoint(forbidden)


def test_engine_has_no_decision_method():
    methods = dir(FuturesConfirmationEngine)
    for banned in ("decide", "signal", "trade", "order", "enter", "buy", "sell"):
        assert not any(banned in m.lower() for m in methods)
