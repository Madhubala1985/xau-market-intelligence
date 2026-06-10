"""Tests for M1 entry refinement (FINAL-INTELLIGENCE).

Proves M1 can only DELAY a qualified entry — it can never create a trade,
choose a direction, or override the higher-timeframe stack.
"""

from datetime import datetime, timedelta, timezone

from src.data.enums import Direction
from src.data.schemas import Candle
from src.strategy.m1_refinement import M1RefinementEngine, M1State

UTC = timezone.utc
T0 = datetime(2026, 6, 9, 9, 0, tzinfo=UTC)
ENGINE = M1RefinementEngine()


def candle(i, o, h, l, c):
    t = T0 + i * timedelta(minutes=1)
    return Candle(symbol="XAUUSD", timeframe="1M", broker_time=t, time_utc=t,
                  open=o, high=h, low=l, close=c, tick_volume=50)


def calm(n):
    return [candle(i, 100.0, 100.35, 99.85, 100.3) for i in range(n)]


def test_no_qualified_entry_means_pass_m1_cannot_create_trades():
    out = ENGINE.assess(calm(20), None)
    assert out.state == M1State.PASS
    assert out.vetoes_entry is False
    # an actionable M1 pattern with NO setup direction still cannot do anything
    out2 = ENGINE.assess(calm(20), Direction.WAIT)
    assert out2.state == M1State.PASS


def test_missing_m1_feed_is_unavailable_with_no_effect():
    out = ENGINE.assess(None, Direction.SHORT)
    assert out.state == M1State.UNAVAILABLE
    assert out.vetoes_entry is False
    short = calm(3)
    assert ENGINE.assess(short, Direction.SHORT).state == M1State.UNAVAILABLE


def test_strong_opposing_rejection_vetoes_this_cycle():
    candles = calm(17)
    # For a SHORT: long lower wicks (buyers rejecting lower prices).
    for i in range(3):
        candles.append(candle(17 + i, 100.0, 100.1, 98.6, 99.98))
    out = ENGINE.assess(candles, Direction.SHORT)
    assert out.state == M1State.VETO_DELAY
    assert out.vetoes_entry is True
    assert "delay" in out.reason


def test_aligned_micro_displacement_confirms():
    candles = calm(19)
    candles.append(candle(19, 100.0, 100.05, 98.7, 98.75))  # bearish impulse
    out = ENGINE.assess(candles, Direction.SHORT)
    assert out.state == M1State.CONFIRM
    assert out.vetoes_entry is False


def test_veto_only_delays_a_real_pipeline_setup():
    """Through the REAL pipeline: with a qualified SHORT setup, an M1 veto
    produces 'entry delayed' — and without any setup, hostile M1 data does
    not conjure a trade."""
    from src.regime.regime_engine import Regime
    from src.strategy import DecisionPipeline
    from tests.test_intelligence_pipeline import (
        bearish_engines,
        falling,
    )
    from tests.test_pipeline import base_input, big_broker

    candles = falling(30)
    entry = candles[-1].close
    engines = bearish_engines(entry, regime=Regime.TREND)
    # M1 candles with strong lower-wick rejection against the SHORT.
    m1 = calm(17) + [candle(17 + i, 100.0, 100.1, 98.6, 99.98)
                     for i in range(3)]
    result = DecisionPipeline(engines).decide(
        base_input(candles, broker=big_broker(), m1_candles=m1)
    )
    assert result.approved is False
    assert "entry delayed by M1" in result.reason
    assert result.context.m1.state == M1State.VETO_DELAY
    # same M1 data without a setup: nothing is created
    engines_no_setup = bearish_engines(entry, regime=Regime.TREND, sweep=False)
    engines_no_setup.mtf = type(engines.mtf)(None, 0.2)
    result2 = DecisionPipeline(engines_no_setup).decide(
        base_input(candles, broker=big_broker(), m1_candles=m1)
    )
    assert result2.approved is False
    assert result2.context.m1.state == M1State.PASS  # nothing to refine


def test_m1_serializes():
    d = ENGINE.assess(calm(20), Direction.LONG).to_dict()
    assert d["state"] in (M1State.PASS, M1State.CONFIRM, M1State.CAUTION)
