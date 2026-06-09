"""Tests for P5-001 order-flow proxy engine.

Required categories:
- proxy values calculated,
- NO direct trade signal from proxy alone (INIT-005 / 16_ORDERFLOW_PROXY_POLICY.md).
"""

import dataclasses
from datetime import datetime, timedelta, timezone

from src.data.schemas import Candle
from src.orderflow import (
    OrderFlowProxy,
    OrderFlowProxyEngine,
    ProxyPressure,
    VolumeState,
)
from src.structure.market_structure import Bias

UTC = timezone.utc
T0 = datetime(2026, 6, 9, 0, 0, tzinfo=UTC)


def c(i: int, o: float, h: float, l: float, cl: float, vol: int, spread: float = 20.0) -> Candle:
    return Candle(
        symbol="XAUUSD",
        timeframe="1H",
        broker_time=T0 + i * timedelta(hours=1),
        time_utc=T0 + i * timedelta(hours=1),
        open=o,
        high=h,
        low=l,
        close=cl,
        tick_volume=vol,
        spread=spread,
    )


def engine() -> OrderFlowProxyEngine:
    return OrderFlowProxyEngine()


# ---------------------------------------------------------------------------
# Proxy values are calculated
# ---------------------------------------------------------------------------

def test_bullish_expansion_proxy_values():
    # Flat low-volume base, then a strong high-volume bullish candle.
    candles = [c(i, 100, 100.5, 99.5, 100.1, 100) for i in range(5)]
    candles.append(c(5, 100, 105, 99.9, 104.8, 400))  # big body, 4x volume
    p = engine().analyze(candles)
    assert p.pressure is ProxyPressure.BULLISH
    assert p.volume_state is VolumeState.EXPANSION
    assert p.volume_ratio > 1.5
    assert p.aggression > 0.5
    assert p.delta_proxy > 0
    assert p.cvd_proxy > 0
    assert p.confidence_adjustment > 0


def test_exhaustion_high_volume_small_body():
    candles = [c(i, 100, 100.5, 99.5, 100.0, 100) for i in range(5)]
    # High volume but tiny body inside a large range -> exhaustion.
    candles.append(c(5, 100, 106, 94, 100.2, 400))
    p = engine().analyze(candles)
    assert p.volume_state is VolumeState.EXHAUSTION
    assert p.uncertainty_adjustment > 0


def test_spread_widening_increases_uncertainty():
    candles = [c(i, 100, 100.5, 99.5, 100.1, 100, spread=20.0) for i in range(5)]
    candles.append(c(5, 100, 100.6, 99.4, 100.2, 110, spread=80.0))  # 4x spread
    p = engine().analyze(candles)
    assert p.spread_widening is True
    assert p.spread_ratio >= 1.5
    assert p.uncertainty_adjustment > 0
    assert p.confidence_adjustment < 0


def test_cvd_divergence_detected():
    # Price drifts up over the window but candles are mostly bearish-bodied
    # (net negative signed volume) -> divergence.
    candles = [
        c(0, 100.0, 100.6, 99.5, 100.5, 100),  # bullish small
        c(1, 100.5, 101.0, 100.0, 100.2, 300),  # bearish heavy
        c(2, 100.2, 101.2, 100.0, 100.8, 100),  # bullish small
        c(3, 100.8, 101.5, 100.4, 100.4, 300),  # bearish heavy
        c(4, 100.4, 101.6, 100.2, 101.2, 100),  # bullish small, price ends higher
    ]
    p = engine().analyze(candles)
    assert p.cvd_proxy < 0          # net signed volume negative
    assert p.divergence is True     # price up but proxy down
    assert p.pressure is ProxyPressure.BEARISH


def test_conflict_with_structure_increases_uncertainty():
    candles = [c(i, 100, 100.5, 99.5, 100.0, 100) for i in range(5)]  # neutral bodies
    candles.append(c(5, 100, 100.6, 99, 99.2, 400))  # bearish heavy -> bearish proxy
    # Structure says bullish, proxy says bearish -> conflict.
    p = engine().analyze(candles, structural_bias=Bias.BULLISH)
    assert p.pressure is ProxyPressure.BEARISH
    assert p.conflict_with_structure is True
    assert p.uncertainty_adjustment > 0


def test_inconclusive_on_short_series():
    p = engine().analyze([c(0, 100, 101, 99, 100, 100)])
    assert p.pressure is ProxyPressure.NEUTRAL
    assert "insufficient" in p.note


# ---------------------------------------------------------------------------
# No direct trade signal from proxy alone
# ---------------------------------------------------------------------------

def test_proxy_is_never_a_trade_signal():
    candles = [c(i, 100, 100.5, 99.5, 100.1, 100) for i in range(5)]
    candles.append(c(5, 100, 105, 99.9, 104.8, 500))  # very strong bullish
    p = engine().analyze(candles)
    # Even with strong bullish pressure, the proxy is explicitly not actionable.
    assert p.is_trade_signal is False


def test_result_exposes_no_trade_decision_fields():
    field_names = {f.name for f in dataclasses.fields(OrderFlowProxy)}
    forbidden = {"direction", "signal", "order", "entry", "side", "action", "trade"}
    assert field_names.isdisjoint(forbidden)


def test_engine_has_no_decision_method():
    methods = dir(OrderFlowProxyEngine)
    for banned in ("decide", "signal", "trade", "order", "enter", "buy", "sell"):
        assert not any(banned in m.lower() for m in methods)


def test_pressure_is_not_a_trade_direction():
    # ProxyPressure is a proxy descriptor, distinct from Direction (LONG/SHORT).
    from src.data.enums import Direction

    assert set(ProxyPressure.__members__) == {"BULLISH", "BEARISH", "NEUTRAL"}
    assert "LONG" not in ProxyPressure.__members__
    assert ProxyPressure is not Direction
