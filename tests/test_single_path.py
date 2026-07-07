"""Single-execution-path guarantees (GOLD-INTEL-001).

- exactly one trading profile (gold_intel); every prior name is retired;
- the retired strategy modules are deleted (no accidental old path); the
  day-narrative family (day_narrative/smc_v2/smc_execution) is RESTORED as
  internal engine logic of gold_intel, not as selectable profiles;
- the trading service builds one engine + one planner (no fork);
- the one engine exposes the decide()/note_stop_loss()/manage_stop() contract.
"""

import importlib

import pytest

from src.execution.session_profiles import PROFILES, RETIRED_PROFILES, get_profile


def test_exactly_one_trading_profile():
    assert set(PROFILES) == {"gold_intel"}


@pytest.mark.parametrize("name", sorted(RETIRED_PROFILES))
def test_retired_profiles_cannot_run(name):
    with pytest.raises(ValueError, match="RETIRED"):
        get_profile(name)


@pytest.mark.parametrize("module", [
    "src.strategy.liquidity_intel",
    "src.strategy.gold_alpha",
    "src.strategy.trade_attribution",
    "src.execution.challenge_planner",
])
def test_retired_modules_are_deleted(module):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)


def test_service_builds_one_engine_and_one_planner():
    import scripts.trading_service as svc
    assert hasattr(svc, "make_gold_intel_pipeline")
    assert hasattr(svc, "IntelTradePlanner")
    # no dual-path / old-engine symbols remain
    for gone in ("make_liquidity_intel_pipeline", "make_smc_pipeline",
                 "make_smc_v2_pipeline", "ChallengeTradePlanner",
                 "make_live_pipeline", "AdaptiveExposureGovernor"):
        assert not hasattr(svc, gone)


def test_one_engine_decide_manage_contract():
    from src.strategy.gold_intel import GoldIntelEngine
    assert hasattr(GoldIntelEngine, "decide")
    assert hasattr(GoldIntelEngine, "note_stop_loss")
    assert hasattr(GoldIntelEngine, "note_trade_closed")
    assert hasattr(GoldIntelEngine, "manage_stop")

def test_narrative_family_is_internal_not_a_profile():
    # restored as ENGINE INTERNALS of gold_intel — still not selectable.
    import importlib
    for mod in ("src.strategy.day_narrative", "src.strategy.smc_v2",
                "src.strategy.smc_execution"):
        importlib.import_module(mod)
    for name in ("smc_v2", "smc_challenge", "gold_alpha"):
        with pytest.raises(ValueError, match="RETIRED"):
            get_profile(name)
