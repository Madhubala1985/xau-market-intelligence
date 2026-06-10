"""Tests for the Adaptive Risk Budget Engine (INTELLIGENCE-001).

Proves: risk expands ONLY with strong evidence, contracts on losses /
drawdown / uncertainty / spread / exposure, never exceeds the 03_RISK_POLICY
cap, and is structurally incapable of martingale behavior.
"""

import pytest

from src.risk.adaptive_risk import (
    POLICY_RISK_CAP,
    RISK_FLOOR,
    AdaptiveRiskEngine,
    AdaptiveRiskInputs,
    CapitalPhase,
    RiskTier,
)

ENGINE = AdaptiveRiskEngine()


def inputs(**overrides) -> AdaptiveRiskInputs:
    kwargs = dict(
        equity=2000.0,
        confluence_score=0.60,
        mtf_score=0.60,
        confidence=0.60,
        uncertainty=0.30,
        regime_tradeable=True,
        spread_ratio=0.20,
        news_clear=True,
        consecutive_losses=0,
        daily_loss_pct=0.0,
        weekly_loss_pct=0.0,
        open_positions=0,
    )
    kwargs.update(overrides)
    return AdaptiveRiskInputs(**kwargs)


def elite(**overrides):
    kwargs = dict(confluence_score=0.90, mtf_score=0.85, confidence=0.85,
                  uncertainty=0.10)
    kwargs.update(overrides)
    return inputs(**kwargs)


# -- policy bounds --------------------------------------------------------------

def test_never_exceeds_the_policy_cap_even_with_max_evidence():
    decision = ENGINE.decide(elite())
    assert decision.risk_pct <= POLICY_RISK_CAP
    assert decision.tier in (RiskTier.ELEVATED, RiskTier.MAX_EVIDENCE)


def test_floor_is_respected():
    decision = ENGINE.decide(inputs(
        confluence_score=0.1, mtf_score=0.1, uncertainty=0.6,
        consecutive_losses=4, daily_loss_pct=0.015, open_positions=1,
    ))
    assert decision.risk_pct == pytest.approx(RISK_FLOOR)


# -- expansion only with evidence ------------------------------------------------

def test_risk_increases_only_with_evidence():
    weak = ENGINE.decide(inputs(confluence_score=0.40, mtf_score=0.30))
    standard = ENGINE.decide(inputs())
    strong = ENGINE.decide(inputs(confluence_score=0.75, mtf_score=0.70,
                                  confidence=0.70, uncertainty=0.25))
    best = ENGINE.decide(elite())
    assert weak.risk_pct < standard.risk_pct
    assert standard.risk_pct < strong.risk_pct
    assert strong.risk_pct <= best.risk_pct
    assert any("expansion" in r for r in best.reasons)
    assert any("weak evidence" in r for r in weak.reasons)


def test_static_half_percent_is_not_the_default():
    # ordinary evidence does NOT produce the policy-cap 0.5%
    decision = ENGINE.decide(inputs())
    assert decision.risk_pct < POLICY_RISK_CAP


# -- contraction ------------------------------------------------------------------

def test_risk_decreases_after_losses_no_martingale_possible():
    risks = [
        ENGINE.decide(elite(consecutive_losses=n)).risk_pct for n in range(6)
    ]
    for before, after in zip(risks, risks[1:]):
        assert after <= before  # NEVER grows with the loss streak
    assert risks[3] < risks[0]


def test_drawdown_contracts_risk():
    fresh = ENGINE.decide(elite())
    daily_dd = ENGINE.decide(elite(daily_loss_pct=0.012))
    weekly_dd = ENGINE.decide(elite(weekly_loss_pct=0.035))
    assert daily_dd.risk_pct < fresh.risk_pct
    assert weekly_dd.risk_pct < fresh.risk_pct


def test_uncertainty_and_spread_contract_risk():
    base = ENGINE.decide(inputs())
    uncertain = ENGINE.decide(inputs(uncertainty=0.55))
    wide = ENGINE.decide(inputs(spread_ratio=0.70))
    assert uncertain.risk_pct < base.risk_pct
    assert wide.risk_pct < base.risk_pct


def test_open_exposure_contracts_risk():
    flat = ENGINE.decide(elite())
    exposed = ENGINE.decide(elite(open_positions=1))
    assert exposed.risk_pct < flat.risk_pct


# -- hard blocks -------------------------------------------------------------------

def test_unclear_news_blocks_all_budget():
    decision = ENGINE.decide(elite(news_clear=False))
    assert decision.risk_pct == 0.0
    assert decision.tier is RiskTier.BLOCKED


def test_untradeable_regime_blocks_all_budget():
    decision = ENGINE.decide(elite(regime_tradeable=False))
    assert decision.risk_pct == 0.0
    assert decision.tier is RiskTier.BLOCKED


def test_spread_at_max_blocks_all_budget():
    decision = ENGINE.decide(elite(spread_ratio=1.0))
    assert decision.tier is RiskTier.BLOCKED


# -- capital phases ------------------------------------------------------------------

def test_capital_phases_classify_equity():
    assert CapitalPhase.of(2_000) is CapitalPhase.PHASE_1
    assert CapitalPhase.of(12_000) is CapitalPhase.PHASE_2
    assert CapitalPhase.of(20_000) is CapitalPhase.PHASE_3
    assert CapitalPhase.of(30_000) is CapitalPhase.PHASE_4


def test_later_phases_derisk_relative_to_growth_phase():
    p1 = ENGINE.decide(inputs(equity=2_000))
    p4 = ENGINE.decide(inputs(equity=30_000))
    assert p1.phase is CapitalPhase.PHASE_1
    assert p4.phase is CapitalPhase.PHASE_4
    assert p4.risk_pct < p1.risk_pct


def test_every_decision_explains_itself():
    decision = ENGINE.decide(elite(consecutive_losses=1, spread_ratio=0.7))
    assert decision.reasons
    blob = " ".join(decision.reasons)
    assert "contraction" in blob
    d = decision.to_dict()
    assert d["risk_pct"] <= POLICY_RISK_CAP
