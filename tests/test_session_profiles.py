"""Session-profile tests (GOLD-ALPHA-001): ONE profile, retired names cannot
run, the envelope can only tighten the risk policy."""

import pytest

from src.execution.session_profiles import (
    GOLD_MAX_DAILY_LOSS,
    GOLD_MAX_OPEN_POSITIONS,
    GOLD_MAX_RISK_PER_TRADE,
    GOLD_MAX_WEEKLY_LOSS,
    PROFILE_NAME,
    PROFILES,
    RETIRED_PROFILES,
    SessionProfile,
    get_profile,
)


def test_exactly_one_trading_profile():
    assert set(PROFILES) == {"gold_alpha"}
    assert PROFILE_NAME == "gold_alpha"


def test_gold_alpha_is_continuous_and_uncapped():
    p = get_profile("gold_alpha")
    assert p.duration_minutes is None       # continuous service
    assert p.max_orders is None             # no artificial per-session cap
    assert p.envelope == "gold_alpha"


def test_envelope_is_growth_mode():
    limits = get_profile("gold_alpha").risk_limits("XAUUSDM")
    assert limits.max_risk_per_trade == GOLD_MAX_RISK_PER_TRADE == 0.06
    assert limits.max_daily_loss == GOLD_MAX_DAILY_LOSS == 1.0     # breaker off
    assert limits.max_weekly_loss == GOLD_MAX_WEEKLY_LOSS == 1.0   # breaker off
    assert limits.max_open_trades == GOLD_MAX_OPEN_POSITIONS == 5
    assert limits.max_trades_per_day == 1000                       # no cap


@pytest.mark.parametrize("name", sorted(RETIRED_PROFILES))
def test_every_retired_profile_is_blocked(name):
    with pytest.raises(ValueError, match="RETIRED"):
        get_profile(name)


def test_retired_message_points_at_the_one_profile():
    with pytest.raises(ValueError, match="gold_alpha"):
        get_profile("liquidity_intel")


def test_get_profile_is_case_insensitive_and_rejects_unknown():
    assert get_profile("  GOLD_ALPHA ").name == "gold_alpha"
    with pytest.raises(KeyError):
        get_profile("totally_unknown_profile")
    with pytest.raises((KeyError, ValueError)):
        get_profile("real")


def test_the_gold_alpha_envelope_is_reserved_for_that_name():
    with pytest.raises(ValueError, match="reserved"):
        SessionProfile(
            name="sneaky", description="x", duration_minutes=None,
            max_risk_per_trade=GOLD_MAX_RISK_PER_TRADE,
            max_daily_loss=GOLD_MAX_DAILY_LOSS,
            max_weekly_loss=GOLD_MAX_WEEKLY_LOSS,
            max_open_positions=GOLD_MAX_OPEN_POSITIONS,
            envelope="gold_alpha")


def test_a_demo_envelope_profile_cannot_loosen_the_policy():
    with pytest.raises(ValueError, match="looser"):
        SessionProfile(
            name="loose", description="x", duration_minutes=60,
            max_risk_per_trade=0.05, envelope="demo")
