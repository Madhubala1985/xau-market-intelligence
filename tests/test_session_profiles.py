"""Session-profile tests (LIQUIDITY-INTEL-001): ONE profile, retired names
cannot run, the envelope can only tighten the risk policy."""

import pytest

from src.execution.session_profiles import (
    INTEL_MAX_DAILY_LOSS,
    INTEL_MAX_OPEN_POSITIONS,
    INTEL_MAX_RISK_PER_TRADE,
    INTEL_MAX_WEEKLY_LOSS,
    PROFILE_NAME,
    PROFILES,
    RETIRED_PROFILES,
    SessionProfile,
    get_profile,
)


def test_exactly_one_trading_profile():
    assert set(PROFILES) == {"liquidity_intel"}
    assert PROFILE_NAME == "liquidity_intel"


def test_liquidity_intel_is_continuous_and_uncapped():
    p = get_profile("liquidity_intel")
    assert p.duration_minutes is None       # continuous service
    assert p.max_orders is None             # no artificial per-session cap
    assert p.envelope == "liquidity_intel"


def test_envelope_matches_the_standing_anchors():
    limits = get_profile("liquidity_intel").risk_limits("XAUUSDM")
    assert limits.max_risk_per_trade == INTEL_MAX_RISK_PER_TRADE == 0.030
    assert limits.max_daily_loss == INTEL_MAX_DAILY_LOSS == 0.05
    assert limits.max_weekly_loss == INTEL_MAX_WEEKLY_LOSS == 0.10
    assert limits.max_open_trades == INTEL_MAX_OPEN_POSITIONS == 3


@pytest.mark.parametrize("name", sorted(RETIRED_PROFILES))
def test_every_retired_profile_is_blocked(name):
    with pytest.raises(ValueError, match="RETIRED"):
        get_profile(name)


def test_retired_message_points_at_the_one_profile():
    with pytest.raises(ValueError, match="liquidity_intel"):
        get_profile("smc_v2")


def test_get_profile_is_case_insensitive_and_rejects_unknown():
    assert get_profile("  LIQUIDITY_INTEL ").name == "liquidity_intel"
    with pytest.raises(KeyError):
        get_profile("totally_unknown_profile")
    # real mode never has a profile
    with pytest.raises((KeyError, ValueError)):
        get_profile("real")


def test_the_liquidity_intel_envelope_is_reserved_for_that_name():
    # No other profile may borrow the liquidity_intel envelope.
    with pytest.raises(ValueError, match="reserved"):
        SessionProfile(
            name="sneaky", description="x", duration_minutes=None,
            max_risk_per_trade=INTEL_MAX_RISK_PER_TRADE,
            max_daily_loss=INTEL_MAX_DAILY_LOSS,
            max_weekly_loss=INTEL_MAX_WEEKLY_LOSS,
            max_open_positions=INTEL_MAX_OPEN_POSITIONS,
            envelope="liquidity_intel",
        )


def test_a_demo_envelope_profile_cannot_loosen_the_policy():
    with pytest.raises(ValueError, match="looser"):
        SessionProfile(
            name="loose", description="x", duration_minutes=60,
            max_risk_per_trade=0.05,  # > 1% demo policy ceiling
            envelope="demo",
        )
