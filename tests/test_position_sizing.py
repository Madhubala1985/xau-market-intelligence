"""Tests for P7-002 position sizing.

Required:
- correct lot calculation,
- excessive risk blocked.
"""

from datetime import datetime, timezone

import pytest

from src.data.enums import DecisionStatus, Direction
from src.data.schemas import BrokerState, TradeDecision
from src.data.enums import BrokerConnectionStatus
from src.risk import (
    PositionSizer,
    RiskContext,
    RiskGovernor,
    RiskLimits,
    SizingStatus,
)
from src.risk import RiskAction

UTC = timezone.utc
NOW = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)


def long_decision(entry: float = 2300.0, stop: float = 2295.0, **overrides) -> TradeDecision:
    kwargs = dict(
        decision_id="D-1",
        time_utc=NOW,
        symbol="XAUUSD",
        direction=Direction.LONG,
        status=DecisionStatus.PROPOSED,
        thesis="sweep reclaim with displacement",
        invalidation_price=stop,
        entry_price=entry,
        stop_loss=stop,
        take_profits=(entry + 10,),
    )
    kwargs.update(overrides)
    return TradeDecision(**kwargs)


def sizer(**limit_overrides) -> PositionSizer:
    return PositionSizer(RiskLimits(**limit_overrides), contract_size=100.0)


# ---------------------------------------------------------------------------
# Correct lot calculation
# ---------------------------------------------------------------------------

def test_correct_lot_calculation():
    # balance 2000, risk 0.5% -> $10 budget; stop 5; contract 100 -> $500/lot.
    r = sizer().size(long_decision(2300.0, 2295.0), balance=2000.0, requested_risk_pct=0.005)
    assert r.status is SizingStatus.OK
    assert r.lot_size == 0.02            # 10 / (5 * 100)
    assert r.risk_amount == pytest.approx(10.0)
    assert r.risk_pct == pytest.approx(0.005)


def test_lot_snapped_down_to_step():
    # $10 budget, stop 6 -> raw 0.01667 -> snapped down to 0.01.
    r = sizer().size(long_decision(2300.0, 2294.0), balance=2000.0, requested_risk_pct=0.005)
    assert r.status is SizingStatus.OK
    assert r.lot_size == 0.01
    assert r.risk_pct <= 0.005 + 1e-9    # floored, never exceeds target


def test_spread_slippage_buffer_reduces_lot():
    base = sizer().size(long_decision(2300.0, 2295.0), 2000.0, 0.005)
    buffered = sizer().size(
        long_decision(2300.0, 2295.0), 2000.0, 0.005, spread_price=1.0, slippage_price=1.0
    )
    assert buffered.effective_stop > base.effective_stop
    assert buffered.lot_size <= base.lot_size


def test_clamped_to_max_lot():
    # Huge balance, tiny stop -> raw lot far above max_lot -> clamped.
    r = sizer(max_lot=1.0).size(long_decision(2300.0, 2299.0), balance=10_000_000.0, requested_risk_pct=0.005)
    assert r.status is SizingStatus.OK
    assert r.lot_size == 1.0


# ---------------------------------------------------------------------------
# Excessive risk blocked
# ---------------------------------------------------------------------------

def test_excessive_requested_risk_blocked():
    r = sizer().size(long_decision(), balance=2000.0, requested_risk_pct=0.02)  # > 0.5%
    assert r.status is SizingStatus.RISK_TOO_HIGH
    assert r.approved is False
    assert r.lot_size == 0.0


# ---------------------------------------------------------------------------
# Stop too wide -> skip (never shrink the stop)
# ---------------------------------------------------------------------------

def test_stop_too_wide_is_blocked_not_shrunk():
    # $10 budget, stop 11 -> raw 0.00909 < min_lot 0.01 -> skip.
    r = sizer().size(long_decision(2300.0, 2289.0), balance=2000.0, requested_risk_pct=0.005)
    assert r.status is SizingStatus.STOP_TOO_WIDE
    assert r.lot_size == 0.0
    # The stop distance on the decision is untouched (sizer never modifies it).


def test_wider_stop_never_increases_lot():
    narrow = sizer().size(long_decision(2300.0, 2295.0), 2000.0, 0.005)  # stop 5
    wider = sizer().size(long_decision(2300.0, 2290.0), 2000.0, 0.005)   # stop 10
    assert wider.lot_size <= narrow.lot_size  # size down, never shrink the stop


# ---------------------------------------------------------------------------
# Invalid input
# ---------------------------------------------------------------------------

def test_zero_balance_invalid():
    r = sizer().size(long_decision(), balance=0.0, requested_risk_pct=0.005)
    assert r.status is SizingStatus.INVALID_INPUT


def test_missing_stop_invalid():
    d = TradeDecision(
        decision_id="D-x", time_utc=NOW, symbol="XAUUSD",
        direction=Direction.NO_TRADE, status=DecisionStatus.NO_TRADE,
    )
    r = sizer().size(d, balance=2000.0, requested_risk_pct=0.005)
    assert r.status is SizingStatus.INVALID_INPUT


# ---------------------------------------------------------------------------
# Integration: sizing output feeds the risk governor
# ---------------------------------------------------------------------------

def test_sizing_output_passes_risk_governor():
    decision = long_decision(2300.0, 2295.0)
    result = sizer().size(decision, balance=2000.0, requested_risk_pct=0.005)
    assert result.approved

    broker = BrokerState(
        time_utc=NOW, connection_status=BrokerConnectionStatus.CONNECTED,
        symbol="XAUUSD", balance=2000.0, equity=2000.0, open_positions=0,
        trade_allowed=True,
    )
    context = RiskContext(
        broker=broker,
        current_spread=20.0,
        lot_size=result.lot_size,
        intended_risk_pct=result.risk_pct,
    )
    verdict = RiskGovernor().evaluate(decision, context)
    assert verdict.action is RiskAction.APPROVE
