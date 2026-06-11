"""Tests for session risk profiles (DEMO-EVAL).

Proves:
- the registry offers the five evaluation profiles,
- the one-order cap exists ONLY in the smoke profile; every serious profile
  is policy-governed (max_orders=None),
- a profile can never be constructed looser than the 03_RISK_POLICY.md demo
  limits (risk %, daily/weekly loss, trades/day, open positions, spread),
- operator overrides re-validate against the same policy bounds,
- profiles map onto the exact RiskLimits the governor/planner enforce.
"""

import pytest

from src.execution.session_profiles import (
    POLICY_MAX_DAILY_LOSS,
    POLICY_MAX_OPEN_POSITIONS,
    POLICY_MAX_RISK_PER_TRADE,
    POLICY_MAX_TRADES_PER_DAY,
    POLICY_MAX_WEEKLY_LOSS,
    PROFILES,
    SessionProfile,
    get_profile,
)


def test_registry_offers_the_evaluation_profiles():
    assert set(PROFILES) == {
        "smoke", "evaluation", "london", "newyork", "full_day", "continuous",
        "growth_evaluation", "demo_challenge",
    }


def test_continuous_profile_is_unbounded_and_policy_governed():
    continuous = get_profile("continuous")
    assert continuous.duration_minutes is None  # no fixed session length
    assert continuous.max_orders is None        # risk policy governs
    # and still policy-bounded on every risk limit
    limits = continuous.risk_limits("XAUUSDM")
    assert limits.max_trades_per_day == 3  # ordinary bound; growth profile = 6
    assert limits.max_daily_loss == POLICY_MAX_DAILY_LOSS


def test_only_smoke_has_an_artificial_one_order_cap():
    assert PROFILES["smoke"].max_orders == 1
    for name, profile in PROFILES.items():
        if name != "smoke":
            assert profile.max_orders is None, (
                f"profile {name} must be policy-governed, not artificially capped"
            )


def test_get_profile_is_case_insensitive_and_rejects_unknown():
    assert get_profile("  EVALUATION ").name == "evaluation"
    with pytest.raises(KeyError):
        get_profile("real")  # no real profile exists; real mode is forbidden


@pytest.mark.parametrize("field,value", [
    ("max_risk_per_trade", POLICY_MAX_RISK_PER_TRADE + 0.001),
    ("max_daily_loss", POLICY_MAX_DAILY_LOSS + 0.01),
    ("max_weekly_loss", POLICY_MAX_WEEKLY_LOSS + 0.01),
    ("max_trades_per_day", POLICY_MAX_TRADES_PER_DAY + 1),
    ("max_open_positions", POLICY_MAX_OPEN_POSITIONS + 1),
    ("max_spread_price", 2.0),
])
def test_profiles_can_never_loosen_risk_policy(field, value):
    kwargs = dict(name="loose", description="x", duration_minutes=60)
    kwargs[field] = value
    with pytest.raises(ValueError, match="looser than 03_RISK_POLICY"):
        SessionProfile(**kwargs)


def test_profiles_may_tighten_risk_policy():
    tight = SessionProfile(
        name="tight", description="x", duration_minutes=30,
        max_risk_per_trade=0.001, max_trades_per_day=1, max_open_positions=1,
    )
    limits = tight.risk_limits("XAUUSDM")
    assert limits.max_risk_per_trade == 0.001
    assert limits.max_trades_per_day == 1
    assert limits.max_open_trades == 1


def test_duration_must_fit_the_session_hard_ceiling():
    with pytest.raises(ValueError, match="duration"):
        SessionProfile(name="x", description="x", duration_minutes=8 * 60 + 1)
    with pytest.raises(ValueError, match="duration"):
        SessionProfile(name="x", description="x", duration_minutes=0)


def test_negative_max_orders_is_rejected():
    with pytest.raises(ValueError, match="max_orders"):
        SessionProfile(name="x", description="x", duration_minutes=10,
                       max_orders=-1)


def test_overrides_revalidate_against_policy():
    profile = get_profile("evaluation")
    with pytest.raises(ValueError, match="looser than 03_RISK_POLICY"):
        profile.with_overrides(max_open_positions=POLICY_MAX_OPEN_POSITIONS + 1)


def test_overrides_apply_and_unset_max_orders_is_preserved():
    profile = get_profile("smoke")
    assert profile.with_overrides().max_orders == 1  # unset keeps the cap
    capped = profile.with_overrides(max_orders=2, duration_minutes=20)
    assert capped.max_orders == 2
    assert capped.duration_minutes == 20
    uncapped = profile.with_overrides(max_orders=None)
    assert uncapped.max_orders is None  # explicit None = policy-governed


def test_risk_limits_carry_the_expected_symbol_and_spread():
    limits = get_profile("london").risk_limits("XAUUSDM")
    assert limits.expected_symbol == "XAUUSDM"
    assert limits.max_spread == 1.0
    assert limits.max_daily_loss == POLICY_MAX_DAILY_LOSS
    assert limits.max_weekly_loss == POLICY_MAX_WEEKLY_LOSS
