"""Tests for P8-001 stop placement intelligence.

Required:
- obvious stop rejected,
- logical stop accepted.
"""

from datetime import datetime, timezone

import pytest

from src.data.enums import DecisionStatus, Direction
from src.data.schemas import TradeDecision
from src.trade_management import StopPlacementEngine, StopVerdict

UTC = timezone.utc
NOW = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)


def engine() -> StopPlacementEngine:
    # clearance = max(atr*0.5, 1.0); min distance = max(broker 0, min_buffer 1) = 1.
    return StopPlacementEngine(atr_multiple=0.5, min_buffer=1.0)


# ---------------------------------------------------------------------------
# Evaluation: obvious rejected, logical accepted
# ---------------------------------------------------------------------------

def test_obvious_stop_on_invalidation_rejected():
    # LONG entry 2300, invalidation (swing low) 2295, atr 2 -> clearance 1.
    r = engine().evaluate(Direction.LONG, 2300.0, 2295.0, proposed_stop=2295.0, atr=2.0)
    assert r.verdict is StopVerdict.REJECTED_OBVIOUS
    assert not r.accepted


def test_logical_stop_accepted():
    r = engine().evaluate(Direction.LONG, 2300.0, 2295.0, proposed_stop=2293.0, atr=2.0)
    assert r.verdict is StopVerdict.ACCEPTED
    assert r.accepted


def test_obvious_stop_on_liquidity_pool_rejected():
    # Stop beyond invalidation but parked on an equal-low pool at 2293.
    r = engine().evaluate(
        Direction.LONG, 2300.0, 2295.0, proposed_stop=2293.0, atr=2.0,
        liquidity_levels=(2293.0,),
    )
    assert r.verdict is StopVerdict.REJECTED_OBVIOUS


def test_short_obvious_stop_rejected():
    r = engine().evaluate(Direction.SHORT, 2300.0, 2305.0, proposed_stop=2305.0, atr=2.0)
    assert r.verdict is StopVerdict.REJECTED_OBVIOUS


def test_short_logical_stop_accepted():
    r = engine().evaluate(Direction.SHORT, 2300.0, 2305.0, proposed_stop=2307.0, atr=2.0)
    assert r.verdict is StopVerdict.ACCEPTED


# ---------------------------------------------------------------------------
# Other rejections
# ---------------------------------------------------------------------------

def test_wrong_side_rejected():
    r = engine().evaluate(Direction.LONG, 2300.0, 2295.0, proposed_stop=2301.0, atr=2.0)
    assert r.verdict is StopVerdict.REJECTED_WRONG_SIDE


def test_not_beyond_invalidation_rejected():
    # Long stop between invalidation (2295) and entry (2300) -> not beyond.
    r = engine().evaluate(Direction.LONG, 2300.0, 2295.0, proposed_stop=2297.0, atr=2.0)
    assert r.verdict is StopVerdict.REJECTED_NOT_BEYOND_INVALIDATION


def test_too_tight_rejected():
    # Beyond invalidation with clearance, but distance from entry too small.
    eng = StopPlacementEngine(atr_multiple=0.0, min_buffer=0.1, broker_min_stop=5.0)
    # clearance = 0.1; min distance = 5. invalidation 2299.9, stop 2299.7 -> dist 0.3 < 5.
    r = eng.evaluate(Direction.LONG, 2300.0, 2299.9, proposed_stop=2299.7, atr=0.0)
    assert r.verdict is StopVerdict.REJECTED_TOO_TIGHT


# ---------------------------------------------------------------------------
# Placement produces an accepted stop
# ---------------------------------------------------------------------------

def test_place_long_stop_beyond_invalidation():
    eng = engine()
    placement = eng.place(Direction.LONG, 2300.0, 2295.0, atr=2.0)
    # clearance 1 -> stop = 2295 - 1 = 2294.
    assert placement.stop_price == 2294.0
    assert placement.distance == 6.0
    # The computed stop must itself pass evaluation.
    assert eng.evaluate(Direction.LONG, 2300.0, 2295.0, placement.stop_price, atr=2.0).accepted


def test_place_short_stop_beyond_invalidation():
    eng = engine()
    placement = eng.place(Direction.SHORT, 2300.0, 2305.0, atr=2.0)
    assert placement.stop_price == 2306.0
    assert eng.evaluate(Direction.SHORT, 2300.0, 2305.0, placement.stop_price, atr=2.0).accepted


def test_place_pushes_beyond_liquidity_pool():
    eng = engine()
    # Pool just beyond invalidation; stop must be pushed below it with clearance.
    placement = eng.place(
        Direction.LONG, 2300.0, 2295.0, atr=2.0, liquidity_levels=(2294.0,)
    )
    # default stop 2294 collides with pool 2294 -> pushed to 2294 - 1 = 2293.
    assert placement.stop_price == 2293.0
    assert eng.evaluate(
        Direction.LONG, 2300.0, 2295.0, placement.stop_price, atr=2.0,
        liquidity_levels=(2294.0,),
    ).accepted


def test_spread_widens_buffer():
    base = engine().place(Direction.LONG, 2300.0, 2295.0, atr=2.0)
    buffered = engine().place(Direction.LONG, 2300.0, 2295.0, atr=2.0, spread=1.0)
    assert buffered.stop_price < base.stop_price  # further from invalidation


# ---------------------------------------------------------------------------
# TradeDecision convenience + invalid inputs
# ---------------------------------------------------------------------------

def test_evaluate_decision_stop():
    decision = TradeDecision(
        decision_id="D-1", time_utc=NOW, symbol="XAUUSD", direction=Direction.LONG,
        status=DecisionStatus.PROPOSED, thesis="sweep reclaim",
        invalidation_price=2295.0, entry_price=2300.0, stop_loss=2293.0,
        take_profits=(2310.0,),
    )
    assert engine().evaluate_decision(decision, atr=2.0).accepted


def test_place_rejects_bad_invalidation():
    with pytest.raises(ValueError):
        engine().place(Direction.LONG, 2300.0, 2305.0, atr=2.0)  # invalidation above entry
