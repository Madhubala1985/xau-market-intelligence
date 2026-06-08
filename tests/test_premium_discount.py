"""Tests for P3-005 premium/discount engine (correct zone mapping)."""

from datetime import datetime, timedelta, timezone

import pytest

from src.data.schemas import Candle
from src.structure import (
    DealingRange,
    PremiumDiscountEngine,
    PriceZone,
)

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


# ---------------------------------------------------------------------------
# Range basics
# ---------------------------------------------------------------------------

def test_range_geometry():
    r = DealingRange(high=100.0, low=0.0)
    assert r.size == 100.0
    assert r.equilibrium == 50.0
    assert r.fraction_of(75.0) == 0.75
    assert r.price_at(0.25) == 25.0


def test_degenerate_range_rejected():
    with pytest.raises(ValueError):
        DealingRange(high=50.0, low=50.0)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def test_classify_premium_discount_equilibrium():
    eng = PremiumDiscountEngine()
    r = DealingRange(high=100.0, low=0.0)
    assert eng.classify(r, 75.0) is PriceZone.PREMIUM
    assert eng.classify(r, 25.0) is PriceZone.DISCOUNT
    assert eng.classify(r, 50.0) is PriceZone.EQUILIBRIUM


def test_classify_outside_range():
    eng = PremiumDiscountEngine()
    r = DealingRange(high=100.0, low=0.0)
    assert eng.classify(r, 120.0) is PriceZone.PREMIUM   # above the high
    assert eng.classify(r, -10.0) is PriceZone.DISCOUNT  # below the low


def test_equilibrium_band():
    eng = PremiumDiscountEngine(equilibrium_band=0.1)  # [45%, 55%] is equilibrium
    r = DealingRange(high=100.0, low=0.0)
    assert eng.classify(r, 52.0) is PriceZone.EQUILIBRIUM
    assert eng.classify(r, 56.0) is PriceZone.PREMIUM
    assert eng.classify(r, 44.0) is PriceZone.DISCOUNT


def test_classify_on_offset_range():
    eng = PremiumDiscountEngine()
    r = DealingRange(high=2400.0, low=2300.0)  # equilibrium 2350
    assert eng.classify(r, 2375.0) is PriceZone.PREMIUM
    assert eng.classify(r, 2325.0) is PriceZone.DISCOUNT
    assert eng.classify(r, 2350.0) is PriceZone.EQUILIBRIUM


# ---------------------------------------------------------------------------
# Gann-box-style segmentation
# ---------------------------------------------------------------------------

def test_default_quartile_segments():
    eng = PremiumDiscountEngine()
    r = DealingRange(high=100.0, low=0.0)
    bands = eng.segments(r)
    assert len(bands) == 4
    assert [(b.bottom, b.top) for b in bands] == [
        (0.0, 25.0), (25.0, 50.0), (50.0, 75.0), (75.0, 100.0)
    ]
    assert [b.zone for b in bands] == [
        PriceZone.DISCOUNT, PriceZone.DISCOUNT, PriceZone.PREMIUM, PriceZone.PREMIUM
    ]
    assert bands[0].label == "0-25%"


def test_custom_segments():
    eng = PremiumDiscountEngine(segments=(0.0, 0.5, 1.0))
    r = DealingRange(high=100.0, low=0.0)
    bands = eng.segments(r)
    assert len(bands) == 2
    assert bands[0].zone is PriceZone.DISCOUNT
    assert bands[1].zone is PriceZone.PREMIUM


def test_invalid_segments_rejected():
    with pytest.raises(ValueError):
        PremiumDiscountEngine(segments=(0.0, 0.5, 0.5, 1.0))  # not strictly increasing


# ---------------------------------------------------------------------------
# Auto range selection from candles
# ---------------------------------------------------------------------------

def test_range_from_candles():
    # swing low 90 at idx1, swing high 110 at idx3 (strength=1).
    candles = [
        cc(0, 95, 96, 92, 95),
        cc(1, 95, 97, 90, 94),    # swing low 90
        cc(2, 94, 100, 93, 99),
        cc(3, 99, 110, 98, 108),  # swing high 110
        cc(4, 108, 109, 104, 106),
    ]
    eng = PremiumDiscountEngine(swing_strength=1)
    r = eng.range_from_candles(candles)
    assert r is not None
    assert r.high == 110.0
    assert r.low == 90.0
    assert r.equilibrium == 100.0
    assert eng.classify(r, 105.0) is PriceZone.PREMIUM
    assert eng.classify(r, 95.0) is PriceZone.DISCOUNT


def test_range_from_candles_none_without_swings():
    candles = [cc(i, 100, 101, 99, 100) for i in range(2)]  # too short / no swings
    assert PremiumDiscountEngine(swing_strength=1).range_from_candles(candles) is None
