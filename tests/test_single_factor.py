"""Tests for the single-factor isolation setups (research/setups/single_factor.py)."""

from datetime import datetime, timedelta, timezone

import pytest

from research.setups.base import MarketData
from research.setups.single_factor import FACTORS, SingleFactorSetup
from src.data.enums import Direction, Timeframe
from src.data.schemas import Candle

UTC = timezone.utc
T0 = datetime(2026, 7, 1, tzinfo=UTC)


def _c(i, o, h, l, c):
    t = T0 + i * timedelta(hours=1)
    return Candle(symbol="XAUUSD", timeframe="1H", broker_time=t, time_utc=t,
                  open=o, high=h, low=l, close=c, tick_volume=100)


def test_factor_registry_has_six():
    assert set(FACTORS) == {"fvg", "liquidity_sweep", "displacement", "choch",
                            "order_block", "supply_demand"}


def test_unknown_factor_raises():
    with pytest.raises(ValueError):
        SingleFactorSetup("not_a_factor")


def test_fvg_factor_emits_market_long_with_atr_geometry():
    candles = [_c(i, 100, 100.5, 99.5, 100) for i in range(15)]
    candles += [
        _c(15, 100, 105, 100, 104),     # displacement up
        _c(16, 104, 106, 102, 105),     # next.low 102 > prev.high 100.5 -> bull FVG @ created 16
        _c(17, 105, 105.5, 104, 105),   # fill bar (market next open)
    ]
    setup = SingleFactorSetup("fvg", exec_timeframe=Timeframe.M5)
    intents = setup.scan(MarketData(by_tf={Timeframe.M5: candles}))
    longs = [it for it in intents if it.direction == Direction.LONG]
    assert len(longs) >= 1
    it = longs[0]
    assert it.entry_type == "MARKET"
    assert it.stop < it.entry_price            # long stop below entry (ATR stop)
    assert it.target > it.entry_price          # 2R target above
    # target distance ~ 2x stop distance (rr=2)
    assert (it.target - it.entry_price) == pytest.approx(
        2 * (it.entry_price - it.stop), rel=0.05)


def test_single_factor_no_confluence_in_rules():
    r = SingleFactorSetup("displacement").rules()
    assert r["confluence"] == "NONE (single factor only)"
    assert r["factor"] == "displacement"
