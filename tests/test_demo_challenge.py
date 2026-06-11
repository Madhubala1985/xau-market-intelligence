"""Tests for the challenge profiles + fixed-lot SMC planner
(DEMO-CHALLENGE-001, revised by SMC-EXECUTION-001).

Covers the envelope/profile registry, the fixed-lot rules, the tightened
add-on protection rules (>=0.5R or break-even — a +0.21 floating trade is
NOT a winner), kill switch, exact XAUUSDm symbol case, and the end-to-end
session path. The SMC pipeline gates themselves are covered in
tests/test_smc_execution.py.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.broker.mt5_data_adapter import BrokerPosition
from src.data.enums import (
    BrokerConnectionStatus,
    Direction,
    SessionType,
)
from src.data.schemas import BrokerState, Candle, TradeDecision
from src.execution.challenge_planner import ChallengeTradePlanner
from src.execution.demo_planner import PlanCheck
from src.execution.gateway import (
    ExecutionCheck,
    ExecutionFlags,
    ExecutionGateway,
    ExecutionStatus,
)
from src.execution.positions import ReconciliationReport
from src.execution.session_profiles import (
    CHALLENGE_MAX_OPEN_POSITIONS,
    CHALLENGE_MAX_RISK_PER_TRADE,
    CHALLENGE_PROFILE_NAME,
    CHALLENGE_PROFILE_NAMES,
    SMC_PROFILE_NAME,
    SessionProfile,
    get_profile,
)
from src.risk.governor import RiskContext, RiskGovernor
from src.risk.leverage_sizing import AccountSnapshot
from src.risk.news_guard import NewsRiskState
from src.strategy.pipeline import PipelineInput
from src.strategy.scoring import ConfidenceResult, ScoreRecommendation
from src.strategy.smc_execution import (
    LOT_NORMAL,
    LOT_STRONG,
    SetupGrade,
    make_challenge_limits,
    make_smc_pipeline,
)

SYMBOL = "XAUUSDM"
BROKER_SYMBOL = "XAUUSDm"  # exact Exness case
START = datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc)  # LONDON session


# -- builders -------------------------------------------------------------------

def make_candles(closes, *, timeframe="M5", start=START, minutes=5, wick=0.25):
    candles, t, prev = [], start, closes[0]
    for close in closes:
        candles.append(Candle(
            symbol=SYMBOL, timeframe=timeframe, broker_time=t, time_utc=t,
            open=prev, high=max(prev, close) + wick,
            low=min(prev, close) - wick, close=close, tick_volume=100,
        ))
        t += timedelta(minutes=minutes)
        prev = close
    return candles


def broker_state(now, *, balance=2000.0, open_positions=0):
    return BrokerState(
        time_utc=now, connection_status=BrokerConnectionStatus.CONNECTED,
        symbol=SYMBOL, balance=balance, equity=balance, free_margin=balance,
        leverage=200, open_positions=open_positions, trade_allowed=True,
    )


def pipeline_input(m5, *, m15=None, m1=None, balance=2000.0, spread=0.2,
                   open_positions=0, **kwargs):
    now = m5[-1].time_utc
    return PipelineInput(
        symbol=SYMBOL, exec_candles=m5, daily_candles=[], h4_candles=[],
        broker=broker_state(now, balance=balance,
                            open_positions=open_positions),
        current_spread=spread, m15_candles=m15, m1_candles=m1,
        risk_pct=CHALLENGE_MAX_RISK_PER_TRADE, now=now, **kwargs,
    )


def challenge_decision(direction=Direction.SHORT, *, lot=0.05,
                       entry=3350.0, stop=None):
    stop = stop if stop is not None else (
        entry + 2.5 if direction is Direction.SHORT else entry - 2.5
    )
    target = entry - 5.0 if direction is Direction.SHORT else entry + 5.0
    return TradeDecision(
        decision_id="smc-test", time_utc=START, symbol=SYMBOL,
        direction=direction,
        setup_type=f"smc_fvg_retest[STRONG,lot={lot:.2f}]",
        thesis="test smc setup", invalidation_price=stop,
        entry_price=entry, stop_loss=stop, take_profits=(target,),
        confidence=0.8, uncertainty=0.2,
    )


def allow_confidence():
    return ConfidenceResult(
        confidence=0.8, uncertainty=0.2,
        recommendation=ScoreRecommendation.ALLOW, size_factor=1.0, reason="x",
    )


def clean_reconciliation():
    return ReconciliationReport(matched=(), orphan_broker=(),
                                orphan_journal=(), detail="clean")


def news_clear():
    return NewsRiskState(known=True, risky=False, source="calendar",
                         detail="clear", status="NEWS_CLEAR")


def open_position(ticket=1, *, direction="SHORT", profit=15.0,
                  entry=3360.0, stop=3363.0, lot=0.05):
    return BrokerPosition(
        ticket=ticket, symbol=BROKER_SYMBOL, direction=direction,
        lot_size=lot, entry_price=entry, stop_loss=stop,
        take_profit=None, current_price=3355.0, profit=profit,
    )


def planner():
    return ChallengeTradePlanner(limits=make_challenge_limits(SYMBOL))


def plan(p, decision, *, positions=(), news=None, risk_inputs=None,
         account=None, broker=None, fresh_setup=True):
    return p.plan(
        decision, allow_confidence(),
        broker=broker or broker_state(START, open_positions=len(positions)),
        account=account or AccountSnapshot(balance=2000.0, free_margin=2000.0,
                                           leverage=200),
        spread_price=0.2,
        open_positions=list(positions),
        reconciliation=clean_reconciliation(),
        news=news or news_clear(),
        risk_inputs=risk_inputs or {
            "open_symbols": {SYMBOL} if positions else set()
        },
        fresh_setup=fresh_setup,
        continuation_supported=fresh_setup,
    )


# -- profile / envelope -----------------------------------------------------------

def test_challenge_profiles_exist_with_the_challenge_envelope():
    for name in CHALLENGE_PROFILE_NAMES:
        profile = get_profile(name)
        assert profile.envelope == "demo_challenge"
        assert profile.max_open_positions == CHALLENGE_MAX_OPEN_POSITIONS == 3
        assert profile.max_risk_per_trade == CHALLENGE_MAX_RISK_PER_TRADE
        assert profile.duration_minutes is None
        assert profile.max_orders is None
        limits = profile.risk_limits(SYMBOL)
        challenge_limits = make_challenge_limits(SYMBOL)
        assert limits.max_open_trades == challenge_limits.max_open_trades == 3
        assert limits.max_risk_per_trade == challenge_limits.max_risk_per_trade
        assert limits.max_daily_loss == challenge_limits.max_daily_loss
        assert limits.max_weekly_loss == challenge_limits.max_weekly_loss


def test_smc_challenge_is_the_primary_name_demo_challenge_an_alias():
    assert SMC_PROFILE_NAME == "smc_challenge"
    assert "DEPRECATED ALIAS" in get_profile(CHALLENGE_PROFILE_NAME).description
    assert "SMC" in get_profile(SMC_PROFILE_NAME).description


def test_challenge_envelope_is_reserved_for_the_challenge_profiles():
    with pytest.raises(ValueError, match="reserved"):
        SessionProfile(
            name="sneaky", description="x", duration_minutes=None,
            envelope="demo_challenge", max_risk_per_trade=0.03,
        )


def test_other_profiles_still_cannot_loosen_the_demo_policy():
    with pytest.raises(ValueError, match="looser than 03_RISK_POLICY"):
        SessionProfile(
            name="loose", description="x", duration_minutes=60,
            max_open_positions=3,  # demo envelope allows only 2
        )


# -- fixed-lot rules ---------------------------------------------------------------

def test_normal_grade_chooses_005():
    pipe = make_smc_pipeline(SYMBOL)
    lot, why = pipe._fixed_lot(
        SetupGrade.NORMAL, SessionType.LONDON, 2000.0, 2.5, 0.2
    )
    assert lot == LOT_NORMAL == 0.05
    assert "NORMAL" in why


def test_strong_grade_chooses_010():
    pipe = make_smc_pipeline(SYMBOL)
    lot, _ = pipe._fixed_lot(
        SetupGrade.STRONG, SessionType.LONDON, 2000.0, 2.5, 0.2
    )
    assert lot == LOT_STRONG == 0.10


def test_low_liquidity_demotes_010_to_005_but_does_not_block():
    pipe = make_smc_pipeline(SYMBOL)
    lot, why = pipe._fixed_lot(
        SetupGrade.STRONG, SessionType.LOW_LIQUIDITY, 2000.0, 2.5, 0.2
    )
    assert lot == LOT_NORMAL
    assert "demoted" in why


def test_survival_cap_demotes_then_skips_never_resizes_the_stop():
    pipe = make_smc_pipeline(SYMBOL)
    lot, why = pipe._fixed_lot(
        SetupGrade.STRONG, SessionType.LONDON, 2000.0, 7.0, 0.2
    )
    assert lot == LOT_NORMAL
    assert "demotes" in why
    lot, why = pipe._fixed_lot(
        SetupGrade.STRONG, SessionType.LONDON, 2000.0, 12.5, 0.2
    )
    assert lot is None
    assert "survival cap" in why


# -- planner gates -----------------------------------------------------------------

def test_news_unknown_does_not_block_challenge_plans():
    unknown = NewsRiskState(known=False, risky=False, source="none",
                            detail="no source", status="NEWS_UNKNOWN")
    result = plan(planner(), challenge_decision(lot=0.05), news=unknown)
    assert result.approved, result.reasons


def test_news_risk_still_blocks():
    blocked = NewsRiskState(known=True, risky=True, source="manual",
                            detail="NEWS_BLOCK file", status="NEWS_BLOCK")
    result = plan(planner(), challenge_decision(), news=blocked)
    assert not result.approved
    assert PlanCheck.NEWS_BLOCKED in result.failed_checks


def test_tactical_stop_is_mandatory():
    decision = challenge_decision()
    no_stop = decision.model_copy(update={"stop_loss": None})
    result = plan(planner(), no_stop)
    assert not result.approved
    assert PlanCheck.NO_STOP_LOSS in result.failed_checks


def test_planner_uses_the_pipeline_fixed_lot():
    result = plan(planner(), challenge_decision(lot=0.10))
    assert result.approved
    assert result.lot_size == 0.10
    result = plan(planner(), challenge_decision(lot=0.05))
    assert result.lot_size == 0.05


# -- add-on protection rules (SMC-EXECUTION-001) -------------------------------------

def test_addon_allowed_when_first_trade_has_half_r_protection():
    # SHORT from 3360, stop 3363 (risk $15 at 0.05): +$15 floating >= 0.5R.
    result = plan(planner(), challenge_decision(lot=0.05),
                  positions=[open_position(profit=15.0)])
    assert result.approved, result.reasons
    assert result.is_addon
    assert result.pyramid is not None and result.pyramid.allowed


def test_addon_allowed_when_stop_is_at_breakeven():
    protected = open_position(profit=2.0, entry=3360.0, stop=3360.0)
    result = plan(planner(), challenge_decision(lot=0.05),
                  positions=[protected])
    assert result.approved, result.reasons


def test_addon_blocked_when_profit_is_noise_like_021():
    # The live defect: +0.21 floating is spread noise, not a winner.
    result = plan(planner(), challenge_decision(lot=0.05),
                  positions=[open_position(profit=0.21)])
    assert not result.approved
    assert PlanCheck.PYRAMIDING_BLOCKED in result.failed_checks
    assert "ADDON_BLOCKED_PROFIT_TOO_SMALL" in result.reasons[0]


def test_addon_blocked_when_first_trade_is_losing():
    result = plan(planner(), challenge_decision(lot=0.05),
                  positions=[open_position(profit=-8.0)])
    assert not result.approved
    assert "ADDON_BLOCKED_NOT_PROTECTED" in result.reasons[0]


def test_addon_blocked_inside_the_same_m5_candle():
    result = plan(
        planner(), challenge_decision(lot=0.05),
        positions=[open_position(profit=15.0)],
        risk_inputs={"open_symbols": {SYMBOL},
                     "seconds_since_last_entry": 60.0},
    )
    assert not result.approved
    assert "ADDON_BLOCKED_SAME_CANDLE" in result.reasons[0]


def test_addon_blocked_when_smc_context_weakened():
    result = plan(planner(), challenge_decision(lot=0.05),
                  positions=[open_position(profit=15.0)], fresh_setup=False)
    assert not result.approved
    assert "ADDON_BLOCKED_SMC_CONTEXT_WEAKENED" in result.reasons[0]


def test_addon_blocked_after_a_losing_trade():
    result = plan(
        planner(), challenge_decision(lot=0.05),
        positions=[open_position(profit=15.0)],
        risk_inputs={"open_symbols": {SYMBOL}, "consecutive_losses": 1},
    )
    assert not result.approved
    assert "after a losing trade" in result.reasons[0]


def test_opposite_direction_position_blocks_no_hedging():
    result = plan(planner(), challenge_decision(Direction.LONG, lot=0.05,
                                                entry=3350.0, stop=3347.5),
                  positions=[open_position(direction="SHORT", profit=20.0)])
    assert not result.approved
    assert "hedging is forbidden" in result.reasons[0]


def test_max_three_open_positions():
    positions = [open_position(ticket=i, profit=20.0 + i) for i in (1, 2, 3)]
    result = plan(planner(), challenge_decision(lot=0.05),
                  positions=positions)
    assert not result.approved
    assert PlanCheck.MAX_POSITIONS in result.failed_checks


def test_001_fallback_only_on_margin_refusal():
    tight = AccountSnapshot(balance=2000.0, free_margin=50.0, leverage=200)
    result = plan(planner(), challenge_decision(lot=0.05), account=tight)
    assert result.approved
    assert result.lot_size == 0.01
    assert "fallback" in result.sizing.reason
    result = plan(planner(), challenge_decision(lot=0.05))
    assert result.lot_size == 0.05


def test_planner_survival_cap_blocks_never_a_structural_widening():
    wide = challenge_decision(lot=0.05, entry=3350.0, stop=3363.0)
    result = plan(planner(), wide)
    assert not result.approved
    assert PlanCheck.SIZING_BLOCKED in result.failed_checks
    assert "survival cap" in result.reasons[0]


# -- kill switch + symbol case ------------------------------------------------------

class _FakeMT5:
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_RETCODE_DONE = 10009

    def __init__(self):
        self.requests = []

    def order_send(self, request):
        self.requests.append(request)
        return SimpleNamespace(retcode=10009, order=777001)


def _enabled_flags():
    return ExecutionFlags(
        trading_mode="DEMO", real_trading_enabled=False,
        allow_demo_orders=True, allow_real_orders=False,
        allow_mt5_order_send=True,
    )


def _risk_context(lot=0.05):
    return RiskContext(
        broker=broker_state(START), current_spread=0.2, lot_size=lot,
        intended_risk_pct=lot * 100.0 * 2.7 / 2000.0,
    )


def test_kill_switch_blocks_challenge_orders():
    client = _FakeMT5()
    gateway = ExecutionGateway(
        RiskGovernor(make_challenge_limits(SYMBOL)), _enabled_flags(), client,
        expected_symbol=SYMBOL, broker_symbol=BROKER_SYMBOL,
        kill_switch=SimpleNamespace(engaged=True),
    )
    result = gateway.execute(challenge_decision(lot=0.05), _risk_context())
    assert result.status is ExecutionStatus.BLOCKED
    assert ExecutionCheck.KILL_SWITCH in result.failed_checks
    assert not client.requests


def test_orders_carry_the_exact_broker_symbol_case():
    client = _FakeMT5()
    gateway = ExecutionGateway(
        RiskGovernor(make_challenge_limits(SYMBOL)), _enabled_flags(), client,
        expected_symbol=SYMBOL, broker_symbol=BROKER_SYMBOL,
        kill_switch=SimpleNamespace(engaged=False),
    )
    result = gateway.execute(challenge_decision(lot=0.10), _risk_context(0.10))
    assert result.status is ExecutionStatus.FILLED
    request = client.requests[0]
    assert request["symbol"] == "XAUUSDm"  # exact case, never canonical
    assert request["volume"] == 0.10
    assert request["sl"] is not None


# -- end-to-end through the REAL supervised session ---------------------------------

def test_challenge_stack_sends_a_fixed_lot_order_through_the_session(tmp_path):
    """The exact stack the live service drives: SupervisedDemoSession +
    ChallengeTradePlanner + gateway, with an SMC-style decision."""
    from unittest.mock import MagicMock

    from src.broker.mt5_data_adapter import MT5DataAdapter
    from src.broker.mt5_settings import load_mt5_settings
    from src.execution.demo_session import (
        CONFIRMATION_TOKEN,
        SupervisedDemoSession,
    )
    from src.execution.kill_switch import KillSwitch
    from src.journal.journal import TradeJournal
    from src.strategy.pipeline import PipelineContext, PipelineResult, PipelineStage
    from tests.test_demo_session import (
        NOW,
        FakeMT5Trading,
        StubPipeline,
        clear_news,
        ready_preflight,
        sending_flags,
    )
    from tests.test_live_shadow import demo_env

    entry, stop = 2315.0, 2317.5
    decision = TradeDecision(
        decision_id="smc-e2e", time_utc=NOW, symbol=SYMBOL,
        direction=Direction.SHORT,
        setup_type="smc_sweep_displacement[STRONG,lot=0.10]",
        thesis="strong smc short", invalidation_price=stop,
        entry_price=entry, stop_loss=stop, take_profits=(2310.0,),
        confidence=0.8, uncertainty=0.2,
    )
    smc = {"mode": "smc", "profile": "smc_challenge", "grade": "STRONG",
           "lot_decision": "0.10", "reason": "e2e"}
    result = PipelineResult(
        stage=PipelineStage.RISK_EVALUATED, approved=True, reason="ok",
        decision=decision, confidence=allow_confidence(),
        context=PipelineContext(
            session=None, htf_bias=None, regime=None, structure_bias=None,
            has_setup=True, challenge=smc,
        ),
        lot_size=0.10,
    )

    fake = FakeMT5Trading()
    adapter = MT5DataAdapter(load_mt5_settings(demo_env()), client=fake)
    adapter.connect()
    kill_switch = KillSwitch(tmp_path / "KILL_SWITCH")
    limits = make_challenge_limits(SYMBOL)
    gateway = ExecutionGateway(
        RiskGovernor(limits), sending_flags(), fake,
        expected_symbol=SYMBOL, broker_symbol=BROKER_SYMBOL,
        kill_switch=kill_switch,
    )
    journal = TradeJournal(tmp_path / "challenge_journal.jsonl")
    session = SupervisedDemoSession(
        adapter=adapter,
        pipeline=StubPipeline([result]),
        planner=ChallengeTradePlanner(limits=limits),
        gateway=gateway,
        journal=journal,
        symbol=BROKER_SYMBOL,
        confirmation=CONFIRMATION_TOKEN,
        preflight=ready_preflight(),
        news_guard=clear_news(tmp_path),
        kill_switch=kill_switch,
        max_orders=None,
        profile_name=SMC_PROFILE_NAME,
        hard_max_trades=10,
        hard_max_open=3,
        max_daily_loss=0.05,
        max_weekly_loss=0.10,
        risk_pct=CHALLENGE_MAX_RISK_PER_TRADE,
        now=lambda: NOW,
        monotonic=MagicMock(side_effect=range(0, 100000, 10)),
        sleep=MagicMock(),
    )
    outcome = session.run_cycle()

    assert outcome.stat.entry_action == "SENT"
    request = fake.order_send.call_args.args[0]
    assert request["symbol"] == "XAUUSDm"
    assert request["volume"] == pytest.approx(0.10)
    assert request["sl"] == pytest.approx(stop)
    ch = outcome.stat.intel["challenge"]
    assert ch["grade"] == "STRONG"
    assert ch["first_trade_profit_state"] == "NO_OPEN_POSITION"
    # MT5-verified accounting is present and verified on this cycle.
    acct = outcome.stat.intel["accounting"]
    assert acct["verified"] is True
    assert acct["mt5_balance"] == pytest.approx(2000.0)
    records = journal.records()
    assert any(r.lot_size == pytest.approx(0.10) for r in records)
