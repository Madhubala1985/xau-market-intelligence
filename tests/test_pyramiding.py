"""Tests for RISK-001 protected pyramiding guard.

Required (10_TASK_QUEUE.md RISK-001):
- pyramiding allowed only into protected winning trades,
- averaging down / adding into loss is blocked,
- total open XAU/USD exposure enforced.
"""

from datetime import datetime, timezone

from src.data.enums import DecisionStatus, Direction
from src.data.schemas import TradeDecision
from src.risk import (
    OpenTrade,
    PyramidAction,
    PyramidCheck,
    PyramidLimits,
    PyramidingGuard,
)

UTC = timezone.utc
NOW = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)


def addon(entry: float = 2320.0, stop: float = 2312.0, direction=Direction.LONG) -> TradeDecision:
    return TradeDecision(
        decision_id="ADD-1",
        time_utc=NOW,
        symbol="XAUUSD",
        direction=direction,
        status=DecisionStatus.PROPOSED,
        thesis="continuation after BOS, fresh discount entry",
        invalidation_price=stop,
        entry_price=entry,
        stop_loss=stop,
        take_profits=(entry + 12,),
    )


def protected_long(lot: float = 0.05, current: float = 2315.0) -> OpenTrade:
    # Stop trailed to break-even (entry), price in profit -> protected winner.
    return OpenTrade(
        symbol="XAUUSD", direction=Direction.LONG,
        entry_price=2300.0, stop_loss=2300.0, current_price=current, lot_size=lot,
    )


def guard(**limit_overrides) -> PyramidingGuard:
    return PyramidingGuard(PyramidLimits(**limit_overrides))


# ---------------------------------------------------------------------------
# Allowed only into a protected winning trade
# ---------------------------------------------------------------------------

def test_addon_into_protected_winner_allowed():
    r = guard().evaluate(
        addon(), addon_lot=0.05, addon_risk_usd=40.0,
        existing_trades=[protected_long()],
        fresh_setup=True, continuation_supported=True,
    )
    assert r.action is PyramidAction.ALLOW
    assert r.allowed


def test_addon_when_first_not_protected_blocked():
    # Stop still below entry (original SL) -> not protected.
    unprotected = OpenTrade(
        symbol="XAUUSD", direction=Direction.LONG,
        entry_price=2300.0, stop_loss=2290.0, current_price=2305.0, lot_size=0.05,
    )
    r = guard().evaluate(
        addon(), 0.05, 40.0, [unprotected],
        fresh_setup=True, continuation_supported=True,
    )
    assert r.action is PyramidAction.BLOCK
    assert PyramidCheck.EXISTING_NOT_PROTECTED in r.failed_checks


# ---------------------------------------------------------------------------
# Adding to a loser / averaging down is blocked
# ---------------------------------------------------------------------------

def test_adding_to_losing_trade_blocked():
    # Price below entry -> in loss / moving toward stop.
    losing = OpenTrade(
        symbol="XAUUSD", direction=Direction.LONG,
        entry_price=2300.0, stop_loss=2290.0, current_price=2294.0, lot_size=0.05,
    )
    r = guard().evaluate(
        addon(), 0.05, 40.0, [losing],
        fresh_setup=True, continuation_supported=True,
    )
    assert r.action is PyramidAction.BLOCK
    assert PyramidCheck.ADDING_TO_LOSS in r.failed_checks
    assert PyramidCheck.EXISTING_NOT_PROTECTED in r.failed_checks


def test_averaging_down_short_blocked():
    # SHORT in loss: price above entry.
    losing_short = OpenTrade(
        symbol="XAUUSD", direction=Direction.SHORT,
        entry_price=2300.0, stop_loss=2310.0, current_price=2306.0, lot_size=0.05,
    )
    r = guard().evaluate(
        addon(entry=2295.0, stop=2303.0, direction=Direction.SHORT),
        0.05, 40.0, [losing_short],
        fresh_setup=True, continuation_supported=True,
    )
    assert r.action is PyramidAction.BLOCK
    assert PyramidCheck.ADDING_TO_LOSS in r.failed_checks


# ---------------------------------------------------------------------------
# Fresh setup / continuation / own risk plan required
# ---------------------------------------------------------------------------

def test_no_fresh_setup_blocked():
    r = guard().evaluate(
        addon(), 0.05, 40.0, [protected_long()],
        fresh_setup=False, continuation_supported=True,
    )
    assert r.action is PyramidAction.BLOCK
    assert PyramidCheck.NO_FRESH_SETUP in r.failed_checks


def test_continuation_not_supported_blocked():
    r = guard().evaluate(
        addon(), 0.05, 40.0, [protected_long()],
        fresh_setup=True, continuation_supported=False,
    )
    assert r.action is PyramidAction.BLOCK
    assert PyramidCheck.CONTINUATION_NOT_SUPPORTED in r.failed_checks


def test_no_existing_trade_blocked():
    r = guard().evaluate(
        addon(), 0.05, 40.0, [],
        fresh_setup=True, continuation_supported=True,
    )
    assert r.action is PyramidAction.BLOCK
    assert PyramidCheck.NO_EXISTING_TRADE in r.failed_checks


def test_opposing_position_is_not_pyramiding():
    opposing = OpenTrade(
        symbol="XAUUSD", direction=Direction.SHORT,
        entry_price=2300.0, stop_loss=2300.0, current_price=2295.0, lot_size=0.05,
    )
    r = guard().evaluate(
        addon(direction=Direction.LONG), 0.05, 40.0, [opposing],
        fresh_setup=True, continuation_supported=True,
    )
    assert r.action is PyramidAction.BLOCK
    assert PyramidCheck.DIRECTION_MISMATCH in r.failed_checks
    assert PyramidCheck.NO_EXISTING_TRADE in r.failed_checks


# ---------------------------------------------------------------------------
# Total open XAU/USD exposure enforced
# ---------------------------------------------------------------------------

def test_total_lot_exposure_cap_enforced():
    # Existing 0.25 + add-on 0.10 = 0.35 > max_total_lots 0.30.
    r = guard(max_total_lots=0.30, max_total_risk_usd=1_000.0).evaluate(
        addon(), 0.10, 40.0, [protected_long(lot=0.25)],
        fresh_setup=True, continuation_supported=True,
    )
    assert r.action is PyramidAction.BLOCK
    assert PyramidCheck.EXPOSURE_CAP_EXCEEDED in r.failed_checks
    assert r.total_lots == 0.35


def test_total_risk_exposure_cap_enforced():
    # Existing trade still has open risk (price above current stop) + add-on risk.
    risky = OpenTrade(
        symbol="XAUUSD", direction=Direction.LONG,
        entry_price=2300.0, stop_loss=2300.0, current_price=2330.0, lot_size=0.10,
    )
    # open risk = (2330-2300)*0.10*100 = $300; add-on $40 -> $340 > cap $200.
    r = guard(max_total_lots=10.0, max_total_risk_usd=200.0).evaluate(
        addon(), 0.05, 40.0, [risky],
        fresh_setup=True, continuation_supported=True,
    )
    assert r.action is PyramidAction.BLOCK
    assert PyramidCheck.EXPOSURE_CAP_EXCEEDED in r.failed_checks


def test_protected_trade_at_breakeven_has_zero_open_risk():
    # Stop at break-even and price at break-even -> open risk 0, within cap.
    be = OpenTrade(
        symbol="XAUUSD", direction=Direction.LONG,
        entry_price=2300.0, stop_loss=2300.0, current_price=2300.0, lot_size=0.10,
    )
    r = guard(max_total_lots=10.0, max_total_risk_usd=50.0).evaluate(
        addon(), 0.05, 40.0, [be],
        fresh_setup=True, continuation_supported=True,
    )
    assert r.action is PyramidAction.ALLOW
    assert r.total_risk_usd == 40.0


# ---------------------------------------------------------------------------
# Add-on must carry its own risk plan; guard has no order method
# ---------------------------------------------------------------------------

def test_addon_missing_risk_plan_blocked():
    # WAIT direction cannot carry a full actionable plan.
    wait = TradeDecision(
        decision_id="ADD-W", time_utc=NOW, symbol="XAUUSD",
        direction=Direction.WAIT, status=DecisionStatus.PROPOSED,
    )
    r = guard().evaluate(
        wait, 0.05, 40.0, [protected_long()],
        fresh_setup=True, continuation_supported=True,
    )
    assert r.action is PyramidAction.BLOCK
    assert PyramidCheck.ADDON_NOT_ACTIONABLE in r.failed_checks
    assert PyramidCheck.ADDON_MISSING_RISK_PLAN in r.failed_checks


def test_guard_has_no_order_method():
    g = guard()
    for attr in ("execute", "order_send", "send", "place_order", "buy", "sell"):
        assert not hasattr(g, attr)
