"""Tests for the demo trade planner (Audit F-3): sizing + pyramiding + governor.

Proves:
- sizing integration: lot derives from min(tier cap, governor budget) and the
  structural stop; no fixed lots; margin can only block, never enlarge,
- the Risk Governor remains final authority (planner cannot approve past it),
- one active thesis: a second same-symbol entry needs PyramidingGuard ALLOW,
- adding to losers / unprotected positions is blocked; a third position never,
- orphan positions block planning (fail closed),
- unknown or risky news state blocks planning (fail closed),
- stop-loss is mandatory; NO_TRADE tier plans nothing,
- the gateway still blocks an approved plan when the kill switch is engaged,
- nothing in the planner path calls order_send.
"""

from datetime import datetime, timezone

import pytest

from src.broker.mt5_data_adapter import BrokerPosition
from src.data.enums import BrokerConnectionStatus, Direction
from src.data.schemas import BrokerState, TradeDecision
from src.execution import (
    DemoTradePlanner,
    PlanCheck,
    PositionReconciler,
    confidence_tier,
)
from src.risk import (
    AccountSnapshot,
    ConfidenceTier,
    NewsRiskGuard,
    RiskGovernor,
    RiskLimits,
)
from src.risk.leverage_sizing import TradingMode
from src.strategy.scoring import ConfidenceResult, ScoreRecommendation

UTC = timezone.utc
NOW = datetime(2026, 6, 10, 13, 0, tzinfo=UTC)

# Balance $2000; governor budget = 0.5% = $10. Entry 2300 / stop 2299 with
# spread 0.2 -> effective stop 1.2 -> loss/lot $120 -> lot 0.08 / loss $9.60.
BALANCE = 2000.0
SPREAD = 0.2


def decision(*, stop=2299.0, entry=2300.0, direction=Direction.LONG) -> TradeDecision:
    return TradeDecision(
        decision_id="P1", time_utc=NOW, symbol="XAUUSDM", direction=direction,
        thesis="sweep reclaimed", invalidation_price=stop, entry_price=entry,
        stop_loss=stop, take_profits=(entry + 10 if direction is Direction.LONG
                                      else entry - 10,),
    )


def allow_confidence(conf=0.75, unc=0.2) -> ConfidenceResult:
    return ConfidenceResult(
        confidence=conf, uncertainty=unc,
        recommendation=ScoreRecommendation.ALLOW, size_factor=1.0, reason="ok",
    )


def broker_state(open_positions=0) -> BrokerState:
    return BrokerState(
        time_utc=NOW, connection_status=BrokerConnectionStatus.CONNECTED,
        symbol="XAUUSDM", balance=BALANCE, equity=BALANCE,
        open_positions=open_positions, trade_allowed=True,
    )


def account(free_margin=BALANCE, leverage=500) -> AccountSnapshot:
    return AccountSnapshot(balance=BALANCE, free_margin=free_margin,
                           leverage=leverage)


def clean_reconciliation():
    return PositionReconciler().reconcile([], [])


def clear_news(tmp_path):
    import json
    cal = tmp_path / "cal.json"
    cal.write_text(json.dumps({"windows": []}), encoding="utf-8")
    return NewsRiskGuard(block_path=tmp_path / "NB", calendar_path=cal).assess(NOW)


def unknown_news(tmp_path):
    return NewsRiskGuard(block_path=tmp_path / "NB",
                         calendar_path=tmp_path / "missing.json").assess(NOW)


def protected_position(*, direction="LONG", sl=2300.0, price=2310.0) -> BrokerPosition:
    # Entry 2300 with stop at/above entry == protected at break-even.
    return BrokerPosition(
        ticket=11, symbol="XAUUSDm", direction=direction, lot_size=0.05,
        entry_price=2300.0, stop_loss=sl, take_profit=2330.0,
        current_price=price, profit=10.0,
    )


def plan(planner=None, *, dec=None, conf=None, open_positions=(), recon=None,
         news=None, tmp_path=None, broker=None, acct=None, **kwargs):
    planner = planner or DemoTradePlanner()
    return planner.plan(
        dec or decision(),
        conf or allow_confidence(),
        broker=broker or broker_state(open_positions=len(open_positions)),
        account=acct or account(),
        spread_price=SPREAD,
        open_positions=list(open_positions),
        reconciliation=recon or clean_reconciliation(),
        news=news or clear_news(tmp_path),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Confidence tier mapping
# ---------------------------------------------------------------------------

def test_tier_mapping():
    block = ConfidenceResult(confidence=0.9, uncertainty=0.8,
                             recommendation=ScoreRecommendation.BLOCK,
                             size_factor=0.0, reason="r")
    reduce = ConfidenceResult(confidence=0.9, uncertainty=0.5,
                              recommendation=ScoreRecommendation.REDUCE,
                              size_factor=0.5, reason="r")
    assert confidence_tier(block) is ConfidenceTier.NO_TRADE
    assert confidence_tier(reduce) is ConfidenceTier.NORMAL_SETUP
    assert confidence_tier(allow_confidence(0.9, 0.1)) is ConfidenceTier.ELITE_A_PLUS_SETUP
    assert confidence_tier(allow_confidence(0.75, 0.2)) is ConfidenceTier.HIGH_CONFLUENCE_SETUP
    assert confidence_tier(allow_confidence(0.5, 0.3)) is ConfidenceTier.NORMAL_SETUP


# ---------------------------------------------------------------------------
# Sizing integration (F-3)
# ---------------------------------------------------------------------------

def test_approved_plan_sizes_from_governor_clamped_cap(tmp_path):
    result = plan(tmp_path=tmp_path)
    assert result.approved is True
    # Cap = min(tier $80 HIGH_CONFLUENCE, $2000 * 0.5% = $10) = $10.
    assert result.sizing.max_loss_cap == pytest.approx(10.0)
    assert result.lot_size == pytest.approx(0.08)
    assert result.sizing.implied_loss <= 10.0
    assert result.risk is not None and result.risk.approved


def test_tier_cap_governs_when_tighter_than_budget(tmp_path):
    # Huge balance: governor budget $500 >> tier caps -> tier cap binds.
    big = AccountSnapshot(balance=100_000.0, free_margin=100_000.0, leverage=500)
    broker = BrokerState(
        time_utc=NOW, connection_status=BrokerConnectionStatus.CONNECTED,
        symbol="XAUUSDM", balance=100_000.0, equity=100_000.0,
        open_positions=0, trade_allowed=True,
    )
    result = plan(tmp_path=tmp_path, acct=big, broker=broker)
    assert result.approved
    assert result.sizing.max_loss_cap == pytest.approx(80.0)  # HIGH_CONFLUENCE


def test_wide_stop_blocks_instead_of_shrinking(tmp_path):
    # Stop 50 USD away: even 0.01 lot loses ~$50.2 > $10 budget -> block.
    result = plan(tmp_path=tmp_path, dec=decision(stop=2250.0))
    assert result.approved is False
    assert PlanCheck.SIZING_BLOCKED in result.failed_checks


def test_margin_can_block_but_never_enlarge(tmp_path):
    # Free margin too small for the 0.08 lot at 1:500 (margin ~ $36.8).
    result = plan(tmp_path=tmp_path, acct=account(free_margin=5.0))
    assert result.approved is False
    assert PlanCheck.SIZING_BLOCKED in result.failed_checks
    assert "margin" in result.reasons[0].lower()


def test_no_trade_tier_plans_nothing(tmp_path):
    block = ConfidenceResult(confidence=0.2, uncertainty=0.9,
                             recommendation=ScoreRecommendation.BLOCK,
                             size_factor=0.0, reason="uncertain")
    result = plan(tmp_path=tmp_path, conf=block)
    assert result.approved is False
    assert PlanCheck.NO_TRADE_TIER in result.failed_checks
    assert result.lot_size == 0.0


def test_stop_loss_mandatory(tmp_path):
    no_sl = TradeDecision(
        decision_id="P2", time_utc=NOW, symbol="XAUUSDM",
        direction=Direction.LONG, thesis="t", invalidation_price=2299.0,
        entry_price=2300.0, stop_loss=None, take_profits=(2310.0,),
    )
    result = plan(tmp_path=tmp_path, dec=no_sl)
    assert result.approved is False
    assert PlanCheck.NO_STOP_LOSS in result.failed_checks


# ---------------------------------------------------------------------------
# Governor remains final authority
# ---------------------------------------------------------------------------

def test_governor_blocks_past_daily_loss_limit(tmp_path):
    result = plan(
        tmp_path=tmp_path,
        risk_inputs={"daily_loss_pct": 0.03},  # over the 2% demo limit
    )
    assert result.approved is False
    assert PlanCheck.RISK_BLOCKED in result.failed_checks


def test_planner_cannot_override_governor_block(tmp_path):
    # A governor configured to block everything (max_trades 0) wins.
    strict = DemoTradePlanner(
        governor=RiskGovernor(RiskLimits(expected_symbol="XAUUSDM",
                                         max_trades_per_day=0)),
    )
    result = plan(strict, tmp_path=tmp_path)
    assert result.approved is False
    assert PlanCheck.RISK_BLOCKED in result.failed_checks


# ---------------------------------------------------------------------------
# Protected pyramiding only (F-3)
# ---------------------------------------------------------------------------

def test_addon_into_protected_winner_is_allowed(tmp_path):
    result = plan(
        tmp_path=tmp_path,
        open_positions=[protected_position()],
        risk_inputs={"open_symbols": frozenset({"XAUUSDM"})},
        fresh_setup=True, continuation_supported=True,
    )
    assert result.approved is True
    assert result.is_addon is True
    assert result.pyramid is not None and result.pyramid.allowed


def test_addon_into_unprotected_position_is_blocked(tmp_path):
    unprotected = protected_position(sl=2295.0)  # stop below entry
    result = plan(
        tmp_path=tmp_path, open_positions=[unprotected],
        risk_inputs={"open_symbols": frozenset({"XAUUSDM"})},
        fresh_setup=True, continuation_supported=True,
    )
    assert result.approved is False
    assert PlanCheck.PYRAMIDING_BLOCKED in result.failed_checks


def test_adding_to_losing_position_is_blocked(tmp_path):
    losing = protected_position(sl=2295.0, price=2296.0)  # below entry
    result = plan(
        tmp_path=tmp_path, open_positions=[losing],
        risk_inputs={"open_symbols": frozenset({"XAUUSDM"})},
        fresh_setup=True, continuation_supported=True,
    )
    assert result.approved is False
    assert PlanCheck.PYRAMIDING_BLOCKED in result.failed_checks


def test_addon_without_fresh_setup_is_blocked(tmp_path):
    result = plan(
        tmp_path=tmp_path, open_positions=[protected_position()],
        risk_inputs={"open_symbols": frozenset({"XAUUSDM"})},
        fresh_setup=False, continuation_supported=True,
    )
    assert result.approved is False
    assert PlanCheck.PYRAMIDING_BLOCKED in result.failed_checks


def test_second_entry_without_guard_approval_hits_governor_duplicate(tmp_path):
    # Same-symbol position open but the add-on path is not taken (no open
    # positions passed to the planner, yet open_symbols says one exists):
    # the governor's duplicate check must block (protected_addon is False).
    result = plan(
        tmp_path=tmp_path,
        risk_inputs={"open_symbols": frozenset({"XAUUSDM"})},
    )
    assert result.approved is False
    assert PlanCheck.RISK_BLOCKED in result.failed_checks
    assert "already open" in result.reasons[0]


def test_third_position_is_never_planned(tmp_path):
    two_open = [protected_position(),
                protected_position(sl=2305.0, price=2315.0)]
    result = plan(
        tmp_path=tmp_path, open_positions=two_open,
        risk_inputs={"open_symbols": frozenset({"XAUUSDM"})},
        fresh_setup=True, continuation_supported=True,
    )
    assert result.approved is False
    assert PlanCheck.MAX_POSITIONS in result.failed_checks


def test_open_position_without_stop_blocks_addon(tmp_path):
    no_sl = BrokerPosition(
        ticket=12, symbol="XAUUSDm", direction="LONG", lot_size=0.05,
        entry_price=2300.0, stop_loss=None, take_profit=None,
        current_price=2310.0, profit=10.0,
    )
    result = plan(
        tmp_path=tmp_path, open_positions=[no_sl],
        fresh_setup=True, continuation_supported=True,
    )
    assert result.approved is False
    assert PlanCheck.POSITION_WITHOUT_STOP in result.failed_checks


# ---------------------------------------------------------------------------
# Fail-closed gates (F-4 / F-5)
# ---------------------------------------------------------------------------

def test_orphan_positions_block_planning(tmp_path):
    dirty = PositionReconciler().reconcile([protected_position()], [])
    result = plan(tmp_path=tmp_path, recon=dirty)
    assert result.approved is False
    assert PlanCheck.ORPHAN_POSITIONS in result.failed_checks


def test_unknown_news_state_blocks_planning(tmp_path):
    result = plan(tmp_path=tmp_path, news=unknown_news(tmp_path))
    assert result.approved is False
    assert PlanCheck.NEWS_UNKNOWN in result.failed_checks


def test_active_news_window_blocks_planning(tmp_path):
    guard = NewsRiskGuard(block_path=tmp_path / "NB",
                          calendar_path=tmp_path / "none.json")
    guard.engage_manual_block("FOMC")
    result = plan(tmp_path=tmp_path, news=guard.assess(NOW))
    assert result.approved is False
    assert PlanCheck.NEWS_BLOCKED in result.failed_checks


# ---------------------------------------------------------------------------
# Mode and gateway safety
# ---------------------------------------------------------------------------

def test_planner_refuses_real_mode():
    with pytest.raises(ValueError):
        DemoTradePlanner(mode=TradingMode.REAL)


def test_kill_switch_blocks_an_approved_plan_at_the_gateway(tmp_path):
    from src.execution import ExecutionFlags, ExecutionGateway, KillSwitch
    from src.execution.gateway import ExecutionCheck
    from src.risk.governor import RiskContext

    result = plan(tmp_path=tmp_path)
    assert result.approved  # planner approved...

    ks = KillSwitch(tmp_path / "KILL_SWITCH")
    ks.engage("halt")
    gateway = ExecutionGateway(
        RiskGovernor(RiskLimits(expected_symbol="XAUUSDM")),
        ExecutionFlags(), client=None,
        expected_symbol="XAUUSDM", kill_switch=ks,
    )
    context = RiskContext(
        broker=broker_state(), current_spread=SPREAD,
        lot_size=result.lot_size, intended_risk_pct=result.sizing.implied_risk_pct,
    )
    outcome = gateway.execute(decision(), context)
    # ...but the gateway still refuses while the kill switch is engaged.
    assert outcome.sent is False
    assert ExecutionCheck.KILL_SWITCH in outcome.failed_checks


def test_planner_path_never_references_order_send(tmp_path):
    import inspect
    import src.execution.demo_planner as planner_module

    source = inspect.getsource(planner_module)
    assert "order_send" not in source
    assert "order_check" not in source
