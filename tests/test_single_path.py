"""Single-execution-path guarantees (LIQUIDITY-INTEL-001).

Proves the rebuild's structural invariants:
- exactly one trading profile exists and the retired names cannot run;
- the deleted decision modules cannot be imported (no accidental old path);
- the trading service builds exactly ONE pipeline + ONE planner (no fork);
- there is one decision engine class wired into the service.
"""

import importlib

import pytest

from src.execution.session_profiles import PROFILES, RETIRED_PROFILES, get_profile


def test_exactly_one_trading_profile():
    assert set(PROFILES) == {"liquidity_intel"}


@pytest.mark.parametrize("name", sorted(RETIRED_PROFILES))
def test_retired_profiles_cannot_run(name):
    with pytest.raises(ValueError, match="RETIRED"):
        get_profile(name)


def test_dual_planner_module_is_deleted():
    """The fixed-lot ChallengeTradePlanner path is gone; IntelTradePlanner is
    the one planner."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("src.execution.challenge_planner")


def test_v2_sweep_scripts_are_deleted():
    """The per-profile sweep/longhaul scripts (a second decision pathway's
    tooling) are gone; the one ship gate is scripts/decision_replay.py."""
    import os
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for gone in ("scripts/v2_sweep.py", "scripts/v2_longhaul.py",
                 "scripts/demo_session_run.py"):
        assert not os.path.exists(os.path.join(repo, gone))


def test_the_one_engine_is_the_proven_brain_on_the_single_path():
    """The single engine composes the validated day-narrative brain (option 1)
    rather than re-deriving an unproven one — restored modules are INTERNALS of
    the one engine, not selectable profiles."""
    from src.strategy.liquidity_intel import LiquidityIntelEngine
    from src.strategy.smc_v2 import SmcV2Pipeline

    assert issubclass(LiquidityIntelEngine, SmcV2Pipeline)


def test_service_builds_one_pipeline_and_one_planner():
    """The service entrypoint imports the single engine + single planner and
    no longer references the old fork symbols."""
    import scripts.trading_service as svc

    src = importlib.import_module("scripts.trading_service")
    # The single engine + planner are imported.
    assert hasattr(svc, "make_liquidity_intel_pipeline")
    assert hasattr(svc, "IntelTradePlanner")
    # The dual-path symbols are gone.
    assert not hasattr(svc, "make_smc_pipeline")
    assert not hasattr(svc, "ChallengeTradePlanner")
    assert not hasattr(svc, "make_live_pipeline")
    assert not hasattr(svc, "DemoTradePlanner")
    assert not hasattr(svc, "AdaptiveExposureGovernor")
    # No CHALLENGE_PROFILE_NAMES fork constant.
    assert not hasattr(svc, "CHALLENGE_PROFILE_NAMES")
    del src


def test_single_engine_decide_interface():
    """The one engine exposes the decide()/note_stop_loss contract the chassis
    drives — and nothing else needs a second strategy module."""
    from src.strategy.liquidity_intel import LiquidityIntelEngine

    assert hasattr(LiquidityIntelEngine, "decide")
    assert hasattr(LiquidityIntelEngine, "note_stop_loss")
