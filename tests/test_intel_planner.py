"""IntelTradePlanner tests (LIQUIDITY-INTEL-001): the single planner enforces
mandatory SL, no hedging, no averaging down, protected add-ons, equity-scaled
sizing and the survival cap. It never sends — the gateway is the only path."""

from datetime import datetime, timezone

import pytest

from src.broker.mt5_data_adapter import BrokerPosition
from src.data.enums import Direction
from src.execution.intel_planner import IntelTradePlanner
from src.execution.positions import ReconciliationReport
from src.risk.leverage_sizing import AccountSnapshot, TradingMode
from src.risk.news_guard import NewsRiskState
from src.strategy.liquidity_intel import make_intel_limits
from src.strategy.scoring import ConfidenceResult, ScoreRecommendation
from tests.intel_helpers import SYMBOL, broker_state, intel_decision

NOW = datetime(2026, 6, 15, 13, 0, tzinfo=timezone.utc)


def _planner():
    return IntelTradePlanner(make_intel_limits(SYMBOL))


def _account():
    return AccountSnapshot(balance=2000.0, free_margin=2000.0, leverage=200)


def _confidence():
    return ConfidenceResult(
        confidence=0.8, uncertainty=0.2,
        recommendation=ScoreRecommendation.ALLOW, size_factor=1.0, reason="ok")


def _clean():
    return ReconciliationReport(matched=(), orphan_broker=(), orphan_journal=())


def _news_clear():
    return NewsRiskState(known=True, risky=False, source="calendar",
                         detail="clear")


def _position(direction="SHORT", profit=50.0, stop=3352.5, entry=3350.0):
    return BrokerPosition(
        ticket=1, symbol="XAUUSDm", direction=direction, lot_size=0.05,
        entry_price=entry, stop_loss=stop, take_profit=None,
        current_price=entry, profit=profit)


def _plan(p, decision, *, positions=()):
    return p.plan(
        decision, _confidence(), broker=broker_state(NOW), account=_account(),
        spread_price=0.2, open_positions=list(positions),
        reconciliation=_clean(), news=_news_clear(), fresh_setup=True)


def test_real_mode_is_forbidden():
    with pytest.raises(ValueError, match="DEMO-only"):
        IntelTradePlanner(make_intel_limits(SYMBOL), mode=TradingMode.REAL)


def test_missing_stop_loss_is_never_planned():
    d = intel_decision(stop=None)
    d = d.model_copy(update={"stop_loss": None, "invalidation_price": None})
    plan = _plan(_planner(), d)
    assert not plan.approved
    assert any("stop" in r.lower() for r in plan.reasons)


def test_equity_scaled_size_within_survival_cap():
    p = _planner()
    plan = _plan(p, intel_decision(direction=Direction.SHORT, lot=0.05))
    assert plan.approved
    assert plan.lot_size >= 0.01
    # loss-at-stop never exceeds the 3% survival cap.
    assert plan.sizing.implied_loss <= 2000.0 * 0.030 + 1e-6


def test_opposite_direction_position_blocks_no_hedging():
    p = _planner()
    long_decision = intel_decision(direction=Direction.LONG, entry=3350.0,
                                   stop=3347.5)
    plan = _plan(p, long_decision, positions=[_position(direction="SHORT")])
    assert not plan.approved
    assert any("hedging is forbidden" in r for r in plan.reasons)


def test_losing_open_position_blocks_addon_no_averaging_down():
    p = _planner()
    plan = _plan(p, intel_decision(direction=Direction.SHORT),
                 positions=[_position(direction="SHORT", profit=-5.0)])
    assert not plan.approved
    assert any("NOT_PROTECTED" in r or "average down" in r for r in plan.reasons)


def test_protected_winner_allows_a_same_direction_addon():
    p = _planner()
    # an open winner with stop already at break-even (protected).
    protected = _position(direction="SHORT", profit=20.0, stop=3350.0,
                          entry=3350.0)
    plan = p.plan(
        intel_decision(direction=Direction.SHORT), _confidence(),
        broker=broker_state(NOW, open_positions=1), account=_account(),
        spread_price=0.2, open_positions=[protected],
        reconciliation=_clean(), news=_news_clear(), fresh_setup=True,
        risk_inputs={"seconds_since_last_entry": 600.0})
    assert plan.approved
    assert plan.is_addon


def test_news_risk_blocks():
    p = _planner()
    risky = NewsRiskState(known=True, risky=True, source="manual", detail="NFP")
    plan = p.plan(
        intel_decision(), _confidence(), broker=broker_state(NOW),
        account=_account(), spread_price=0.2, open_positions=[],
        reconciliation=_clean(), news=risky, fresh_setup=True)
    assert not plan.approved
    assert any("news" in r.lower() for r in plan.reasons)


def test_orphan_positions_fail_closed():
    p = _planner()
    dirty = ReconciliationReport(matched=(), orphan_broker=(99,),
                                 orphan_journal=(), detail="ticket 99 unknown")
    plan = p.plan(
        intel_decision(), _confidence(), broker=broker_state(NOW),
        account=_account(), spread_price=0.2, open_positions=[],
        reconciliation=dirty, news=_news_clear(), fresh_setup=True)
    assert not plan.approved
    assert any("reconciliation" in r.lower() for r in plan.reasons)
