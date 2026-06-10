"""Tests for the Adaptive Exposure Governor (OPERATIONAL-INTELLIGENCE-001)."""

from src.risk.exposure_governor import (
    AdaptiveExposureGovernor,
    ExposureInputs,
    ExposureState,
)

GOV = AdaptiveExposureGovernor()


def inputs(**overrides) -> ExposureInputs:
    kwargs = dict(
        confluence_score=0.55,
        mtf_score=0.60,
        session="LONDON",
        volatility_dangerous=False,
        spread_ratio=0.2,
        news_blocked=False,
        news_caution=False,
        daily_loss_pct=0.0,
        weekly_loss_pct=0.0,
        max_daily_loss=0.02,
        max_weekly_loss=0.05,
        consecutive_losses=0,
        trades_today=0,
        open_positions=0,
        hard_max_trades=6,
        hard_max_open=2,
    )
    kwargs.update(overrides)
    return ExposureInputs(**kwargs)


def test_normal_conditions_standard_allowance():
    d = GOV.decide(inputs())
    assert d.state == ExposureState.NORMAL
    assert d.max_trades_today == 3
    assert d.trades_remaining == 3
    assert d.max_open == 2


def test_strong_evidence_in_killzone_extends_allowance():
    d = GOV.decide(inputs(confluence_score=0.78, mtf_score=0.90,
                          session="NEW_YORK"))
    assert d.state == ExposureState.AGGRESSIVE
    assert d.max_trades_today == 6
    assert "aggressive" in d.reason


def test_aggressive_never_exceeds_the_profile_hard_bound():
    d = GOV.decide(inputs(confluence_score=0.90, mtf_score=0.95,
                          hard_max_trades=3))
    assert d.max_trades_today == 3  # tighten-only vs the static bound


def test_losses_and_drawdown_force_defensive():
    assert GOV.decide(inputs(consecutive_losses=2)).state == \
        ExposureState.DEFENSIVE
    d = GOV.decide(inputs(daily_loss_pct=0.012))
    assert d.state == ExposureState.DEFENSIVE
    assert d.max_trades_today == 1 and d.max_open == 1
    # a loss streak can NEVER raise the allowance (no revenge structurally)
    clean = GOV.decide(inputs(confluence_score=0.9, mtf_score=0.9))
    losing = GOV.decide(inputs(confluence_score=0.9, mtf_score=0.9,
                               consecutive_losses=3))
    assert losing.max_trades_today < clean.max_trades_today


def test_news_caution_forces_defensive_and_block_forces_zero():
    assert GOV.decide(inputs(news_caution=True)).state == \
        ExposureState.DEFENSIVE
    blocked = GOV.decide(inputs(news_blocked=True))
    assert blocked.state == ExposureState.BLOCKED
    assert blocked.trades_remaining == 0
    assert blocked.allows_entry is False


def test_dangerous_volatility_and_max_spread_block():
    assert GOV.decide(inputs(volatility_dangerous=True)).state == \
        ExposureState.BLOCKED
    assert GOV.decide(inputs(spread_ratio=1.0)).state == \
        ExposureState.BLOCKED


def test_loss_limits_lock_entries_down():
    d = GOV.decide(inputs(daily_loss_pct=0.02))
    assert d.state == ExposureState.LOCKDOWN
    assert d.trades_remaining == 0
    assert GOV.decide(inputs(weekly_loss_pct=0.05)).state == \
        ExposureState.LOCKDOWN


def test_remaining_counts_down_with_trades_taken():
    d = GOV.decide(inputs(trades_today=2))
    assert d.trades_remaining == 1
    done = GOV.decide(inputs(trades_today=3))
    assert done.trades_remaining == 0 and done.allows_entry is False


def test_decision_serializes_with_reason():
    payload = GOV.decide(inputs()).to_dict()
    assert payload["state"] == "NORMAL"
    assert payload["reason"]
