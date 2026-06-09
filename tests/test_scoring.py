"""Tests for P6-002 confidence and uncertainty engine.

Required:
- high uncertainty blocks/reduces trade,
- confidence alone cannot bypass risk.
"""

import dataclasses

import pytest

from src.orderflow import FuturesAlignment, FuturesConfirmation, OrderFlowProxy, ProxyPressure, VolumeState
from src.strategy import (
    ComponentScores,
    ConfidenceEngine,
    ConfidenceResult,
    ScoreRecommendation,
)
from src.structure.market_structure import Bias


def comps(v: float) -> ComponentScores:
    return ComponentScores(
        structure=v, liquidity=v, regime=v, volatility=v, session=v, execution_quality=v
    )


def engine() -> ConfidenceEngine:
    return ConfidenceEngine()


def conflicting_proxy() -> OrderFlowProxy:
    # A proxy result that lowers confidence and raises uncertainty.
    return OrderFlowProxy(
        pressure=ProxyPressure.BEARISH,
        volume_state=VolumeState.EXHAUSTION,
        volume_ratio=1.0,
        spread_ratio=1.0,
        spread_widening=True,
        aggression=0.1,
        delta_proxy=-100.0,
        cvd_proxy=-100.0,
        divergence=True,
        abnormal_activity=False,
        conflict_with_structure=True,
        confidence_adjustment=-0.2,
        uncertainty_adjustment=0.2,
        note="conflict",
    )


def conflicting_futures() -> FuturesConfirmation:
    return FuturesConfirmation(
        alignment=FuturesAlignment.CONFLICT,
        spot_bias=Bias.BULLISH,
        futures_bias=Bias.BEARISH,
        confidence_adjustment=-0.1,
        uncertainty_adjustment=0.1,
        note="conflict",
    )


# ---------------------------------------------------------------------------
# Aggregation basics
# ---------------------------------------------------------------------------

def test_strong_aligned_components_allow():
    r = engine().score(comps(0.9))
    assert r.recommendation is ScoreRecommendation.ALLOW
    assert r.size_factor == 1.0
    assert r.confidence > 0.8
    assert r.uncertainty < 0.4


def test_scores_clamped_to_unit_interval():
    r = engine().score(comps(1.0))
    assert 0.0 <= r.confidence <= 1.0
    assert 0.0 <= r.uncertainty <= 1.0


def test_component_out_of_range_rejected():
    with pytest.raises(ValueError):
        ComponentScores(
            structure=1.2, liquidity=0.5, regime=0.5,
            volatility=0.5, session=0.5, execution_quality=0.5,
        )


# ---------------------------------------------------------------------------
# High uncertainty blocks / reduces
# ---------------------------------------------------------------------------

def test_component_disagreement_blocks_via_uncertainty():
    # Half the components fully support, half fully oppose -> large disagreement.
    c = ComponentScores(
        structure=1.0, liquidity=1.0, regime=1.0,
        volatility=0.0, session=0.0, execution_quality=0.0,
    )
    r = engine().score(c)
    # base_uncertainty = (1-0.5)*0.5 + 1.0*0.5 = 0.75 -> BLOCK.
    assert r.uncertainty >= 0.7
    assert r.recommendation is ScoreRecommendation.BLOCK
    assert r.size_factor == 0.0


def test_elevated_uncertainty_reduces_size():
    # Moderate disagreement pushes uncertainty into the reduce band.
    c = ComponentScores(
        structure=0.8, liquidity=0.8, regime=0.8,
        volatility=0.2, session=0.8, execution_quality=0.8,
    )
    r = engine().score(c)
    # base_uncertainty = (1-0.7)*0.5 + 0.6*0.5 = 0.45 -> REDUCE band.
    assert r.recommendation is ScoreRecommendation.REDUCE
    assert 0.0 < r.size_factor < 1.0


def test_proxy_and_futures_conflict_raise_uncertainty():
    base = engine().score(comps(0.7))
    conflicted = engine().score(comps(0.7), proxy=conflicting_proxy(), futures=conflicting_futures())
    assert conflicted.uncertainty > base.uncertainty
    assert conflicted.confidence < base.confidence
    assert conflicted.recommendation in (ScoreRecommendation.REDUCE, ScoreRecommendation.BLOCK)


def test_low_confidence_blocks():
    r = engine().score(comps(0.1))
    assert r.recommendation is ScoreRecommendation.BLOCK


# ---------------------------------------------------------------------------
# Confidence alone cannot bypass risk
# ---------------------------------------------------------------------------

def test_max_confidence_still_requires_risk_governor():
    r = engine().score(comps(1.0))
    assert r.confidence == 1.0
    assert r.recommendation is ScoreRecommendation.ALLOW
    # Even at maximum confidence, scoring never authorizes a trade.
    assert r.authorizes_trade is False
    assert r.risk_governor_required is True


def test_result_has_no_trade_authorization_field():
    field_names = {f.name for f in dataclasses.fields(ConfidenceResult)}
    forbidden = {"approved", "authorized", "bypass_risk", "order", "signal", "execute"}
    assert field_names.isdisjoint(forbidden)


def test_engine_has_no_authorization_method():
    methods = dir(ConfidenceEngine)
    for banned in ("approve", "authorize", "bypass", "execute", "trade", "order"):
        assert not any(banned in m.lower() for m in methods)
