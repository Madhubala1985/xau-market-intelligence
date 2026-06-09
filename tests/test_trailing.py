"""Tests for P8-002 trailing stop engine.

Required:
- no premature trailing,
- no widening stop,
- valid partial/runners.
"""

from src.data.enums import Direction
from src.trade_management import (
    PositionState,
    RunnerConditions,
    TrailingStopEngine,
    TrailMethod,
)


def engine() -> TrailingStopEngine:
    return TrailingStopEngine(atr_multiple=1.0, buffer=1.0, be_trigger_r=1.0)


# LONG entry 2300, initial stop 2295 -> R = 5.
def long_state(current_price: float, current_stop: float = 2295.0, atr: float = 4.0) -> PositionState:
    return PositionState(
        direction=Direction.LONG, entry_price=2300.0, initial_stop=2295.0,
        current_stop=current_stop, current_price=current_price, atr=atr,
    )


def short_state(current_price: float, current_stop: float = 2305.0, atr: float = 4.0) -> PositionState:
    return PositionState(
        direction=Direction.SHORT, entry_price=2300.0, initial_stop=2305.0,
        current_stop=current_stop, current_price=current_price, atr=atr,
    )


# ---------------------------------------------------------------------------
# No premature trailing
# ---------------------------------------------------------------------------

def test_no_trailing_before_confirmation():
    # Profit 2 (0.4R) < 1R trigger -> no trail even though a candidate is better.
    state = long_state(current_price=2302.0)
    r = engine().update_stop(state, TrailMethod.VOLATILITY)
    assert r.moved is False
    assert r.new_stop == 2295.0
    assert "premature" in r.reason


def test_break_even_only_after_confirmation():
    # Before confirmation, break-even does not apply.
    assert engine().update_stop(long_state(2303.0), TrailMethod.BREAK_EVEN).moved is False
    # After confirmation (profit >= 1R), break-even locks in.
    r = engine().update_stop(long_state(2306.0), TrailMethod.BREAK_EVEN)
    assert r.moved is True
    assert r.new_stop == 2300.0


# ---------------------------------------------------------------------------
# Trailing moves only in favor; never widens
# ---------------------------------------------------------------------------

def test_volatility_trail_after_confirmation():
    # Profit 10 (2R). atr 4 -> candidate 2310 - 4 = 2306 > current 2295 -> move.
    r = engine().update_stop(long_state(2310.0), TrailMethod.VOLATILITY)
    assert r.moved is True
    assert r.new_stop == 2306.0


def test_no_widening_long():
    # Stop already at 2306; price 2308, candidate 2304 < current -> must NOT move.
    state = long_state(current_price=2308.0, current_stop=2306.0)
    r = engine().update_stop(state, TrailMethod.VOLATILITY)
    assert r.moved is False
    assert r.new_stop == 2306.0
    assert "widen" in r.reason


def test_no_widening_short():
    # Short stop already at 2294; candidate would be higher -> no move.
    state = short_state(current_price=2292.0, current_stop=2294.0)
    r = engine().update_stop(state, TrailMethod.VOLATILITY)
    assert r.moved is False
    assert r.new_stop == 2294.0


def test_structure_trail():
    # Confirmed; last swing low 2307 -> candidate 2307 - 1 = 2306 > 2295 -> move.
    r = engine().update_stop(long_state(2312.0), TrailMethod.STRUCTURE, last_swing=2307.0)
    assert r.moved is True
    assert r.new_stop == 2306.0


def test_liquidity_trail():
    r = engine().update_stop(long_state(2312.0), TrailMethod.LIQUIDITY, protect_level=2308.0)
    assert r.moved is True
    assert r.new_stop == 2307.0


def test_candidate_on_wrong_side_of_price_ignored():
    # Structure swing above price -> candidate above price -> ignored.
    state = long_state(current_price=2310.0)
    r = engine().update_stop(state, TrailMethod.STRUCTURE, last_swing=2315.0)
    assert r.moved is False


def test_short_volatility_trail():
    # Short: entry 2300, price 2290 (2R). atr 4 -> candidate 2294 < stop 2305 -> move.
    r = engine().update_stop(short_state(2290.0), TrailMethod.VOLATILITY)
    assert r.moved is True
    assert r.new_stop == 2294.0


# ---------------------------------------------------------------------------
# Partial / runner logic
# ---------------------------------------------------------------------------

def test_partial_levels_include_1r_and_liquidity():
    plan = engine().partial_plan(long_state(2310.0), next_liquidity=2315.0)
    assert plan.take_levels == (2305.0, 2315.0)  # 1R then next pool beyond it


def test_partial_skips_liquidity_below_1r():
    # next liquidity 2303 is before 1R (2305) -> not added.
    plan = engine().partial_plan(long_state(2310.0), next_liquidity=2303.0)
    assert plan.take_levels == (2305.0,)


def test_runner_allowed_when_conditions_good():
    plan = engine().partial_plan(
        long_state(2310.0),
        conditions=RunnerConditions(structure_valid=True, opposite_displacement=False, spread_safe=True),
    )
    assert plan.runner_allowed is True


def test_runner_blocked_on_opposite_displacement():
    plan = engine().partial_plan(
        long_state(2310.0),
        conditions=RunnerConditions(structure_valid=True, opposite_displacement=True, spread_safe=True),
    )
    assert plan.runner_allowed is False


def test_runner_blocked_on_invalid_structure():
    plan = engine().partial_plan(
        long_state(2310.0), conditions=RunnerConditions(structure_valid=False)
    )
    assert plan.runner_allowed is False
