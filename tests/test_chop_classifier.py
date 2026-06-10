"""Tests for CHOPPY decomposition (INTELLIGENCE-001).

Proves CHOPPY is graded into subtypes: dangerous conditions stay hard-blocked,
while sweep/trap/breakout/continuation chop become tradeable CANDIDATES (still
fully gated by confluence, hypothesis invariants, and the Risk Governor).
"""

from datetime import datetime, timedelta, timezone

from src.data.schemas import Candle
from src.liquidity.liquidity_map import (
    LiquidityKind,
    LiquidityLevel,
    LiquiditySide,
)
from src.liquidity.sweep import SweepEvent, SweepStatus
from src.regime.chop_classifier import ChopClassifier, ChopSubtype
from src.structure.market_structure import Bias

UTC = timezone.utc
T0 = datetime(2026, 6, 9, 9, 0, tzinfo=UTC)


def candle(i, o, h, l, c):
    t = T0 + i * timedelta(minutes=5)
    return Candle(symbol="XAUUSD", timeframe="5M", broker_time=t, time_utc=t,
                  open=o, high=h, low=l, close=c, tick_volume=100)


def noisy_flat(n):
    """Alternating, body-dominated noise around 100 (low-quality chop)."""
    out = []
    for i in range(n):
        up = i % 2 == 0
        o, c = (100.0, 100.6) if up else (100.6, 100.0)
        out.append(candle(i, o, max(o, c) + 0.2, min(o, c) - 0.2, c))
    return out


def wicky(n):
    """Tiny bodies, huge wicks: erratic/dangerous conditions."""
    return [candle(i, 100.0, 102.0, 98.0, 100.05) for i in range(n)]


def drifting_down(n):
    """Persistent bearish drift with clean bodies (continuation)."""
    return [candle(i, 100 - 0.4 * i, 100.2 - 0.4 * i, 99.5 - 0.4 * i,
                   99.6 - 0.4 * i) for i in range(n)]


def sweep_event(index, status, bias=Bias.BEARISH):
    level = LiquidityLevel(kind=LiquidityKind.PREV_DAY_HIGH,
                           side=LiquiditySide.BUY_SIDE,
                           price=101.0, time_utc=T0)
    return SweepEvent(level=level, swept_side=LiquiditySide.BUY_SIDE,
                      rejection_bias=bias, sweep_index=index, sweep_time=T0,
                      status=status)


CLF = ChopClassifier()


def test_dangerous_spread_is_a_hard_block():
    a = CLF.classify(noisy_flat(40), spread_ratio=0.9)
    assert a.subtype is ChopSubtype.DANGEROUS_CHOP
    assert a.tradeable is False
    assert "spread" in a.reason


def test_erratic_wicks_are_dangerous():
    a = CLF.classify(wicky(40))
    assert a.subtype is ChopSubtype.DANGEROUS_CHOP
    assert a.tradeable is False


def test_low_quality_chop_blocks():
    a = CLF.classify(noisy_flat(40))
    assert a.subtype is ChopSubtype.LOW_QUALITY_CHOP
    assert a.tradeable is False


def test_confirmed_sweep_is_a_trap_reversal_candidate():
    candles = noisy_flat(40)
    a = CLF.classify(candles, [sweep_event(len(candles) - 5,
                                           SweepStatus.TRUE_SWEEP)])
    assert a.subtype is ChopSubtype.TRAP_REVERSAL_FROM_CHOP
    assert a.tradeable is True


def test_pending_sweep_is_liquidity_chop():
    candles = noisy_flat(40)
    a = CLF.classify(candles, [sweep_event(len(candles) - 5,
                                           SweepStatus.PENDING)])
    assert a.subtype is ChopSubtype.LIQUIDITY_CHOP_WITH_SWEEP
    assert a.tradeable is True


def test_old_sweep_outside_lookback_is_ignored():
    candles = noisy_flat(60)
    a = CLF.classify(candles, [sweep_event(2, SweepStatus.TRUE_SWEEP)])
    assert a.subtype is ChopSubtype.LOW_QUALITY_CHOP


def test_displacement_breakout_from_chop_is_a_candidate():
    candles = noisy_flat(39)
    # One strong displacement candle closing well below the prior range.
    candles.append(candle(39, 100.0, 100.1, 96.0, 96.2))
    a = CLF.classify(candles)
    assert a.subtype is ChopSubtype.BREAKOUT_EXPANSION_FROM_CHOP
    assert a.tradeable is True


def test_directional_drift_is_continuation():
    a = CLF.classify(drifting_down(40))
    assert a.subtype is ChopSubtype.CONTINUATION_AFTER_CHOP
    assert a.tradeable is True
    assert a.drift_ratio >= 0.35


def test_assessment_serializes():
    a = CLF.classify(noisy_flat(40))
    d = a.to_dict()
    assert d["subtype"] == a.subtype.value
    assert isinstance(d["tradeable"], bool)


def test_strong_mtf_direction_is_a_breakdown_not_low_quality():
    """OPERATIONAL-001 live regression: all-bearish MTF (score 1.0) with
    1.5x displacement must not read LOW_QUALITY_CHOP."""
    candles = noisy_flat(38)
    # a 1.5x-displacement bearish body: real but below the 1.8x breakout bar
    last = candles[-1].close
    candles.append(candle(38, last, last + 0.1, last - 1.6, last - 1.5))
    candles.append(candle(39, last - 1.5, last - 1.3, last - 1.7, last - 1.45))
    weak_geo = CLF.classify(candles)
    assert weak_geo.subtype is ChopSubtype.LOW_QUALITY_CHOP
    with_evidence = CLF.classify(candles, directional_score=0.90)
    assert with_evidence.subtype is ChopSubtype.DIRECTIONAL_CHOP_BREAKDOWN
    assert with_evidence.tradeable is True
    assert "MTF direction" in with_evidence.reason


def test_directional_evidence_cannot_override_dangerous_chop():
    a = CLF.classify(wicky(40), directional_score=1.0)
    assert a.subtype is ChopSubtype.DANGEROUS_CHOP
    assert a.tradeable is False


def test_weak_direction_with_weak_geometry_stays_low_quality():
    a = CLF.classify(noisy_flat(40), directional_score=0.60)
    assert a.subtype is ChopSubtype.LOW_QUALITY_CHOP
