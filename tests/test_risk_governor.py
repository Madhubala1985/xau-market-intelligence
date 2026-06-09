"""Tests for P7-001 Risk Governor.

Proves every mandatory risk-blocking case (07_TEST_POLICY.md):
no stop-loss, too much risk, daily loss, weekly loss, spread too high,
invalid lot size, broker state unknown, duplicate trade, wrong symbol.
Plus approve/reduce paths and that the governor never executes orders.
"""

from datetime import datetime, timezone

import pytest

from src.data.enums import BrokerConnectionStatus, DecisionStatus, Direction
from src.data.schemas import BrokerState, TradeDecision
from src.risk import (
    RiskAction,
    RiskCheck,
    RiskContext,
    RiskGovernor,
    RiskLimits,
)

UTC = timezone.utc
NOW = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)


def good_decision(**overrides) -> TradeDecision:
    kwargs = dict(
        decision_id="D-1",
        time_utc=NOW,
        symbol="XAUUSD",
        direction=Direction.LONG,
        status=DecisionStatus.PROPOSED,
        thesis="sell-side sweep reclaimed with bullish displacement",
        invalidation_price=2295.0,
        entry_price=2300.0,
        stop_loss=2295.0,
        take_profits=(2310.0,),
        confidence=0.7,
        uncertainty=0.2,
    )
    kwargs.update(overrides)
    return TradeDecision(**kwargs)


def good_broker(**overrides) -> BrokerState:
    kwargs = dict(
        time_utc=NOW,
        connection_status=BrokerConnectionStatus.CONNECTED,
        symbol="XAUUSD",
        balance=2000.0,
        equity=2000.0,
        open_positions=0,
        trade_allowed=True,
    )
    kwargs.update(overrides)
    return BrokerState(**kwargs)


def good_context(**overrides) -> RiskContext:
    kwargs = dict(
        broker=good_broker(),
        current_spread=20.0,
        lot_size=0.10,
        intended_risk_pct=0.004,
        daily_loss_pct=0.0,
        weekly_loss_pct=0.0,
        trades_today=0,
        consecutive_losses=0,
        open_symbols=frozenset(),
        size_factor_hint=1.0,
    )
    kwargs.update(overrides)
    return RiskContext(**kwargs)


def gov() -> RiskGovernor:
    return RiskGovernor()


# ---------------------------------------------------------------------------
# Approve / reduce
# ---------------------------------------------------------------------------

def test_clean_trade_is_approved():
    r = gov().evaluate(good_decision(), good_context())
    assert r.action is RiskAction.APPROVE
    assert r.approved is True
    assert r.size_factor == 1.0
    assert r.failed_checks == ()


def test_scoring_hint_reduces_size():
    r = gov().evaluate(good_decision(), good_context(size_factor_hint=0.5))
    assert r.action is RiskAction.REDUCE
    assert r.size_factor == 0.5
    assert r.approved is True


def test_scoring_hint_zero_blocks():
    r = gov().evaluate(good_decision(), good_context(size_factor_hint=0.0))
    assert r.action is RiskAction.BLOCK
    assert RiskCheck.SCORING_BLOCKED in r.failed_checks


# ---------------------------------------------------------------------------
# Mandatory blocking checks (07_TEST_POLICY.md)
# ---------------------------------------------------------------------------

def test_no_stop_loss_blocked():
    # Build a decision without a stop (NO_TRADE avoids schema's stop-side rule),
    # then it is still actionable? Use a LONG with stop_loss None.
    d = good_decision(stop_loss=None)
    r = gov().evaluate(d, good_context())
    assert r.is_blocked
    assert RiskCheck.NO_STOP_LOSS in r.failed_checks


def test_too_much_risk_blocked():
    r = gov().evaluate(good_decision(), good_context(intended_risk_pct=0.02))
    assert r.is_blocked
    assert RiskCheck.RISK_TOO_HIGH in r.failed_checks


def test_daily_loss_reached_blocked():
    r = gov().evaluate(good_decision(), good_context(daily_loss_pct=0.02))
    assert r.is_blocked
    assert RiskCheck.DAILY_LOSS_REACHED in r.failed_checks


def test_weekly_loss_reached_blocked():
    r = gov().evaluate(good_decision(), good_context(weekly_loss_pct=0.05))
    assert r.is_blocked
    assert RiskCheck.WEEKLY_LOSS_REACHED in r.failed_checks


def test_spread_too_high_blocked():
    r = gov().evaluate(good_decision(), good_context(current_spread=100.0))
    assert r.is_blocked
    assert RiskCheck.SPREAD_TOO_HIGH in r.failed_checks


def test_invalid_lot_size_blocked():
    r = gov().evaluate(good_decision(), good_context(lot_size=0.0))
    assert r.is_blocked
    assert RiskCheck.INVALID_LOT_SIZE in r.failed_checks


def test_broker_state_unknown_blocked():
    broker = good_broker(connection_status=BrokerConnectionStatus.UNKNOWN, trade_allowed=False)
    r = gov().evaluate(good_decision(), good_context(broker=broker))
    assert r.is_blocked
    assert RiskCheck.BROKER_STATE_UNKNOWN in r.failed_checks


def test_duplicate_trade_blocked():
    r = gov().evaluate(good_decision(), good_context(open_symbols=frozenset({"XAUUSD"})))
    assert r.is_blocked
    assert RiskCheck.DUPLICATE_TRADE in r.failed_checks


def test_wrong_symbol_blocked():
    # Governor configured for XAUUSD; decision on a different symbol.
    r = gov().evaluate(good_decision(symbol="EURUSD"), good_context())
    assert r.is_blocked
    assert RiskCheck.WRONG_SYMBOL in r.failed_checks


# ---------------------------------------------------------------------------
# Exposure / counts / non-actionable
# ---------------------------------------------------------------------------

def test_max_open_trades_blocked():
    r = gov().evaluate(good_decision(), good_context(broker=good_broker(open_positions=1)))
    assert r.is_blocked
    assert RiskCheck.MAX_OPEN_TRADES in r.failed_checks


def test_max_trades_per_day_blocked():
    r = gov().evaluate(good_decision(), good_context(trades_today=3))
    assert r.is_blocked
    assert RiskCheck.MAX_TRADES_REACHED in r.failed_checks


def test_consecutive_losses_blocked_when_configured():
    governor = RiskGovernor(RiskLimits(max_consecutive_losses=2))
    r = governor.evaluate(good_decision(), good_context(consecutive_losses=2))
    assert r.is_blocked
    assert RiskCheck.CONSECUTIVE_LOSSES in r.failed_checks


def test_non_actionable_blocked():
    d = good_decision(direction=Direction.WAIT, thesis=None, invalidation_price=None,
                      entry_price=None, stop_loss=None, take_profits=())
    r = gov().evaluate(d, good_context())
    assert r.is_blocked
    assert RiskCheck.NON_ACTIONABLE in r.failed_checks


# ---------------------------------------------------------------------------
# Multiple simultaneous failures are all reported; confidence cannot bypass
# ---------------------------------------------------------------------------

def test_all_failures_accumulated():
    d = good_decision(stop_loss=None, symbol="EURUSD")
    ctx = good_context(intended_risk_pct=0.02, current_spread=100.0, lot_size=0.0)
    r = gov().evaluate(d, ctx)
    assert r.is_blocked
    for check in (
        RiskCheck.WRONG_SYMBOL,
        RiskCheck.NO_STOP_LOSS,
        RiskCheck.INVALID_LOT_SIZE,
        RiskCheck.SPREAD_TOO_HIGH,
        RiskCheck.RISK_TOO_HIGH,
    ):
        assert check in r.failed_checks


def test_high_confidence_cannot_bypass_block():
    # Maximum confidence/hint must not override a hard risk block.
    d = good_decision(confidence=1.0, uncertainty=0.0)
    r = gov().evaluate(d, good_context(intended_risk_pct=0.02, size_factor_hint=1.0))
    assert r.is_blocked
    assert RiskCheck.RISK_TOO_HIGH in r.failed_checks


# ---------------------------------------------------------------------------
# The governor never executes orders
# ---------------------------------------------------------------------------

def test_governor_has_no_execution_method():
    methods = dir(RiskGovernor)
    for banned in ("order", "send", "execute", "buy", "sell", "place"):
        assert not any(banned in m.lower() for m in methods)
