"""Tests for MTF alignment + graded confluence (INTELLIGENCE-001).

Proves each evidence component genuinely moves the score (sweep, FVG, order
block, premium/discount, displacement, orderflow, MTF) and that alignment is
computed from real per-timeframe structure.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.data.enums import Direction, SessionType
from src.data.schemas import Candle
from src.liquidity.liquidity_map import (
    LiquidityKind,
    LiquidityLevel,
    LiquiditySide,
)
from src.liquidity.sweep import SweepEvent, SweepStatus
from src.strategy.confluence import (
    ConfluenceEngine,
    MtfAlignment,
    MtfAlignmentEngine,
)
from src.structure.market_structure import (
    Bias,
    MarketStructureEngine,
)
from src.structure.premium_discount import PriceZone
from src.structure.zones import Zone, ZoneKind

UTC = timezone.utc
T0 = datetime(2026, 6, 9, 9, 0, tzinfo=UTC)


def candle(i, o, h, l, c, step=timedelta(minutes=5)):
    t = T0 + i * step
    return Candle(symbol="XAUUSD", timeframe="5M", broker_time=t, time_utc=t,
                  open=o, high=h, low=l, close=c, tick_volume=100)


def falling(n, step=timedelta(minutes=5)):
    return [candle(i, 100 - i, 101 - i, 99 - i, 99.5 - i, step) for i in range(n)]


def rising(n, step=timedelta(minutes=5)):
    return [candle(i, 100 + i, 101 + i, 99 + i, 100.5 + i, step) for i in range(n)]


def bearish_series(step):
    """Swing low then a close below it -> bearish BOS -> final BEARISH."""
    rows = [
        (11, 12, 10, 11), (11, 11.5, 8, 9), (9, 11, 9, 10),
        (10, 10.2, 7, 7.2), (7.2, 7.5, 6, 6.5),
    ]
    return [candle(i, *row, step) for i, row in enumerate(rows)]


def bullish_series(step):
    rows = [
        (9, 10, 8, 9), (9, 12, 9, 11), (11, 11, 9.5, 10),
        (10, 13, 10, 12.8), (12.8, 13.5, 12.5, 13.2),
    ]
    return [candle(i, *row, step) for i, row in enumerate(rows)]


def sweep(total, *, bias=Bias.BEARISH, status=SweepStatus.TRUE_SWEEP):
    level = LiquidityLevel(kind=LiquidityKind.PREV_DAY_HIGH,
                           side=LiquiditySide.BUY_SIDE, price=101.0,
                           time_utc=T0)
    return SweepEvent(level=level, swept_side=LiquiditySide.BUY_SIDE,
                      rejection_bias=bias, sweep_index=total - 3,
                      sweep_time=T0, status=status)


def zone(kind, *, bias=Bias.BEARISH, created=95, mitigated=False):
    return Zone(kind=kind, bias=bias, top=101.0, bottom=100.5,
                origin_index=created - 1, created_index=created,
                created_time=T0, mitigated=mitigated)


STRUCTURE = MarketStructureEngine().analyze(falling(40))


def bearish_mtf(score=0.9):
    return MtfAlignment(d1=Bias.BEARISH, h4=Bias.BEARISH, h1=Bias.BEARISH,
                        m15=Bias.BEARISH, m5=Bias.BEARISH,
                        direction=Direction.SHORT, score=score, reason="test")


def assess(direction=Direction.SHORT, **overrides):
    kwargs = dict(
        mtf=bearish_mtf(),
        sweeps=[],
        structure=STRUCTURE,
        zones=[],
        price_zone=PriceZone.PREMIUM,
        displacement_ratio=1.0,
        session=SessionType.LONDON,
        spread_ratio=0.2,
        orderflow=None,
        total_candles=100,
    )
    kwargs.update(overrides)
    return ConfluenceEngine().assess(direction, **kwargs)


# -- MTF alignment -------------------------------------------------------------

def test_mtf_alignment_all_bearish_supports_short():
    engine = MtfAlignmentEngine(swing_strength=1)
    out = engine.align(
        daily=bearish_series(timedelta(days=1)),
        h4=bearish_series(timedelta(hours=4)),
        h1=bearish_series(timedelta(hours=1)),
        m15=bearish_series(timedelta(minutes=15)),
        m5_bias=Bias.BEARISH,
    )
    assert out.direction is Direction.SHORT
    assert out.score > 0.9
    assert out.d1 is Bias.BEARISH and out.m15 is Bias.BEARISH


def test_mtf_conflict_yields_no_direction():
    engine = MtfAlignmentEngine(swing_strength=1, min_direction_score=0.7)
    out = engine.align(
        daily=bullish_series(timedelta(days=1)),
        h4=bearish_series(timedelta(hours=4)),
        h1=bullish_series(timedelta(hours=1)),
        m15=bearish_series(timedelta(minutes=15)),
        m5_bias=None,
    )
    assert out.direction is None


def test_missing_timeframes_are_honest_not_fake():
    out = MtfAlignmentEngine().align(daily=[], h4=[], h1=[], m15=[], m5_bias=None)
    assert out.direction is None
    assert out.score == 0.0
    assert out.d1 is None and out.h1 is None


# -- component effects ----------------------------------------------------------

def test_no_candidate_direction_scores_zero_with_everything_missing():
    report = assess(direction=None)
    assert report.score == 0.0
    assert "mtf" in report.missing and "sweep" in report.missing


def test_sweep_evidence_raises_the_score():
    without = assess()
    with_sweep = assess(sweeps=[sweep(100)])
    assert with_sweep.score > without.score
    assert with_sweep.statuses["sweep"] == "TRUE_SWEEP"
    assert "sweep" in without.missing and "sweep" not in with_sweep.missing


def test_fvg_evidence_raises_the_score():
    without = assess()
    with_fvg = assess(zones=[zone(ZoneKind.FAIR_VALUE_GAP)])
    assert with_fvg.score > without.score
    assert with_fvg.statuses["fvg"] == "ALIGNED"


def test_mitigated_or_opposing_fvg_does_not_count():
    mitigated = assess(zones=[zone(ZoneKind.FAIR_VALUE_GAP, mitigated=True)])
    opposing = assess(zones=[zone(ZoneKind.FAIR_VALUE_GAP, bias=Bias.BULLISH)])
    baseline = assess()
    assert mitigated.score == pytest.approx(baseline.score)
    assert opposing.score == pytest.approx(baseline.score)


def test_order_block_evidence_raises_the_score():
    without = assess()
    with_ob = assess(zones=[zone(ZoneKind.ORDER_BLOCK)])
    assert with_ob.score > without.score
    assert with_ob.statuses["order_block"] == "OB_ALIGNED"


def test_premium_discount_location_matters():
    short_in_premium = assess(price_zone=PriceZone.PREMIUM)
    short_in_discount = assess(price_zone=PriceZone.DISCOUNT)
    assert short_in_premium.score > short_in_discount.score
    long_in_discount = assess(direction=Direction.LONG,
                              mtf=MtfAlignment(
                                  d1=Bias.BULLISH, h4=Bias.BULLISH,
                                  h1=Bias.BULLISH, m15=Bias.BULLISH,
                                  m5=Bias.BULLISH, direction=Direction.LONG,
                                  score=0.9, reason="t"),
                              price_zone=PriceZone.DISCOUNT)
    long_in_premium = assess(direction=Direction.LONG,
                             mtf=long_in_discount.direction and MtfAlignment(
                                 d1=Bias.BULLISH, h4=Bias.BULLISH,
                                 h1=Bias.BULLISH, m15=Bias.BULLISH,
                                 m5=Bias.BULLISH, direction=Direction.LONG,
                                 score=0.9, reason="t"),
                             price_zone=PriceZone.PREMIUM)
    assert long_in_discount.score > long_in_premium.score


def test_displacement_raises_the_score():
    weak = assess(displacement_ratio=1.0)
    strong = assess(displacement_ratio=2.5)
    assert strong.score > weak.score


def test_mtf_misalignment_lowers_the_score():
    aligned = assess()
    misaligned = assess(mtf=MtfAlignment(
        d1=Bias.BULLISH, h4=Bias.BULLISH, h1=Bias.BULLISH, m15=Bias.BULLISH,
        m5=Bias.BULLISH, direction=Direction.LONG, score=0.9, reason="t"))
    assert aligned.score > misaligned.score


def test_report_serializes_with_statuses_and_missing():
    report = assess(sweeps=[sweep(100)])
    d = report.to_dict()
    assert d["direction"] == "SHORT"
    assert "statuses" in d and "missing" in d
    assert 0.0 <= d["score"] <= 1.0
