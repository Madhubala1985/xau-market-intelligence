"""Tests for P3-004 FVG / order block / supply-demand engine (valid/invalid zones)."""

from datetime import datetime, timedelta, timezone

from src.data.schemas import Candle
from src.structure import Bias, ZoneEngine, ZoneKind

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


def engine() -> ZoneEngine:
    return ZoneEngine(swing_strength=1, displacement_factor=1.5)


# ---------------------------------------------------------------------------
# Fair value gaps
# ---------------------------------------------------------------------------

def test_valid_bullish_fvg():
    candles = [
        cc(0, 9, 10, 8, 9.5),       # prev.high = 10
        cc(1, 9.5, 13, 9.5, 12.8),  # up displacement
        cc(2, 12.8, 13.5, 12, 13),  # next.low = 12 > 10 -> gap [10, 12]
    ]
    fvgs = engine().find_fvgs(candles)
    assert len(fvgs) == 1
    z = fvgs[0]
    assert z.kind is ZoneKind.FAIR_VALUE_GAP
    assert z.bias is Bias.BULLISH
    assert (z.bottom, z.top) == (10, 12)
    assert z.created_index == 2
    assert z.mitigated is False  # no candle returns into the gap


def test_valid_bearish_fvg():
    candles = [
        cc(0, 11, 12, 10, 10.5),    # prev.low = 10
        cc(1, 10.5, 10.5, 7, 7.2),  # down displacement
        cc(2, 7.2, 8, 6.5, 7),      # next.high = 8 < 10 -> gap [8, 10]
    ]
    fvgs = engine().find_fvgs(candles)
    assert len(fvgs) == 1
    assert fvgs[0].bias is Bias.BEARISH
    assert (fvgs[0].bottom, fvgs[0].top) == (8, 10)


def test_no_fvg_when_no_gap():
    candles = [
        cc(0, 9, 10, 8, 9.5),
        cc(1, 9.5, 11, 7, 10),
        cc(2, 10, 10.5, 8.5, 9),  # overlaps prev range -> no gap
    ]
    assert engine().find_fvgs(candles) == []


def test_fvg_mitigation():
    candles = [
        cc(0, 9, 10, 8, 9.5),
        cc(1, 9.5, 13, 9.5, 12.8),
        cc(2, 12.8, 13.5, 12, 13),     # gap [10, 12]
        cc(3, 12, 12.5, 10.5, 11),     # trades back into the gap -> mitigated
    ]
    z = engine().find_fvgs(candles)[0]
    assert z.mitigated is True
    assert z.mitigation_index == 3


# ---------------------------------------------------------------------------
# Order blocks
# ---------------------------------------------------------------------------

def test_valid_bullish_order_block():
    # swing high 12 (idx1); bearish OB candle (idx2); up break closes > 12 (idx3).
    candles = [
        cc(0, 9, 10, 8.5, 9.5),
        cc(1, 9.5, 12, 9, 11.5),       # swing high 12
        cc(2, 11.5, 11.6, 10.5, 10.8),  # bearish OB candle
        cc(3, 10.8, 13, 10.6, 12.8),    # bullish break (close 12.8 > 12)
        cc(4, 12.8, 13.5, 12.5, 13.2),
    ]
    obs = engine().find_order_blocks(candles)
    assert len(obs) == 1
    z = obs[0]
    assert z.kind is ZoneKind.ORDER_BLOCK
    assert z.bias is Bias.BULLISH
    assert z.origin_index == 2
    assert (z.bottom, z.top) == (10.5, 11.6)
    assert z.created_index == 3


def test_no_order_block_without_structure_break():
    candles = [
        cc(0, 10.0, 10.2, 9.8, 10.0),
        cc(1, 10.0, 10.2, 9.8, 10.05),
        cc(2, 10.0, 10.2, 9.8, 10.0),
        cc(3, 10.0, 10.2, 9.8, 10.05),
        cc(4, 10.0, 10.2, 9.8, 10.0),
    ]
    assert engine().find_order_blocks(candles) == []


# ---------------------------------------------------------------------------
# Supply / demand
# ---------------------------------------------------------------------------

def test_valid_demand_zone():
    candles = [
        cc(0, 10, 10.5, 9.5, 10),
        cc(1, 10, 10.5, 9.5, 10),
        cc(2, 10, 10.5, 9.5, 10),    # base candle [9.5, 10.5]
        cc(3, 10, 15, 9.8, 14.5),    # up displacement -> demand zone
    ]
    zones = engine().find_supply_demand(candles)
    assert len(zones) == 1
    z = zones[0]
    assert z.kind is ZoneKind.SUPPLY_DEMAND
    assert z.bias is Bias.BULLISH
    assert z.origin_index == 2
    assert (z.bottom, z.top) == (9.5, 10.5)


def test_valid_supply_zone():
    candles = [
        cc(0, 10, 10.5, 9.5, 10),
        cc(1, 10, 10.5, 9.5, 10),
        cc(2, 10, 10.5, 9.5, 10),    # base candle
        cc(3, 10, 10.2, 5, 5.5),     # down displacement -> supply zone
    ]
    zones = engine().find_supply_demand(candles)
    assert len(zones) == 1
    assert zones[0].bias is Bias.BEARISH


def test_no_supply_demand_without_displacement():
    candles = [cc(i, 10, 10.5, 9.5, 10.1) for i in range(5)]  # all small ranges
    assert engine().find_supply_demand(candles) == []


# ---------------------------------------------------------------------------
# build() and no look-ahead
# ---------------------------------------------------------------------------

def test_build_combines_all_kinds():
    candles = [
        cc(0, 9, 10, 8, 9.5),
        cc(1, 9.5, 13, 9.5, 12.8),
        cc(2, 12.8, 13.5, 12, 13),
        cc(3, 13, 14, 12.8, 13.5),
    ]
    zones = engine().build(candles)
    kinds = {z.kind for z in zones}
    assert ZoneKind.FAIR_VALUE_GAP in kinds
    # sorted by created_index
    assert all(
        zones[i].created_index <= zones[i + 1].created_index
        for i in range(len(zones) - 1)
    )


def test_mitigation_no_lookahead_prefix():
    candles = [
        cc(0, 9, 10, 8, 9.5),
        cc(1, 9.5, 13, 9.5, 12.8),
        cc(2, 12.8, 13.5, 12, 13),     # gap created at idx2
        cc(3, 12, 12.5, 10.5, 11),     # would mitigate, but excluded from prefix
    ]
    # On the prefix ending at the creation candle, the gap is not yet mitigated.
    z_prefix = engine().find_fvgs(candles[:3])[0]
    assert z_prefix.mitigated is False
    # With the later candle, it is mitigated.
    z_full = engine().find_fvgs(candles)[0]
    assert z_full.mitigated is True
