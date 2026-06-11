"""Tests for the demo_challenge aggressive momentum profile
(Task DEMO-CHALLENGE-001).

Proves the owner-directed behavior:
- the demo_challenge profile exists with the challenge envelope (3 open max,
  fixed-lot survival cap) and the envelope is reserved for that ONE profile,
- fixed lots: 0.05 for NORMAL momentum, 0.10 for very STRONG momentum,
- macro/futures/news-unknown never block (only an actual news RISK state),
- low liquidity demotes 0.10 -> 0.05 but never hard-blocks strong momentum,
- the tactical stop is mandatory and LOCAL: no stop candidate => skip the
  cycle; the huge structural stop is never used as a fallback,
- same-direction add-ons only while every open trade is in floating profit;
  adding to a loser, after a loss, against direction (hedge), or beyond 3
  open positions is blocked (no martingale/grid/averaging structurally),
- the kill switch blocks execution,
- orders carry the EXACT broker symbol case (XAUUSDm).
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
    SessionProfile,
    get_profile,
)
from src.risk.governor import RiskContext, RiskGovernor
from src.risk.leverage_sizing import AccountSnapshot
from src.risk.news_guard import NewsRiskState
from src.strategy.challenge_momentum import (
    LOT_NORMAL,
    LOT_STRONG,
    MomentumState,
    make_challenge_limits,
    make_challenge_pipeline,
)
from src.strategy.pipeline import PipelineInput, PipelineStage
from src.strategy.scoring import ConfidenceResult, ScoreRecommendation

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


def m5_breakdown(final_body):
    """40 declining candles, a 4-candle pullback (local swing high), two
    small drifts, then a breakdown candle with the given body."""
    closes = [3400.0 - 0.5 * (i + 1) for i in range(40)]        # -> 3380.0
    closes += [3380.6, 3381.2, 3381.8, 3382.4]                  # pullback top
    closes += [3382.2, 3382.0]                                  # drift
    closes += [3382.0 - final_body]                             # breakdown
    return make_candles(closes)


def m15_bearish():
    return make_candles(
        [3440.0 - 1.5 * i for i in range(30)], timeframe="M15", minutes=15,
        start=START - timedelta(hours=6),
    )


def m1_with_local_swing(entry_zone=3381.0):
    closes = [entry_zone + d for d in
              (1.0, 0.6, 0.2, -0.2, 0.2, 0.6, -0.1, -0.8, -1.2, -1.6,
               -1.8, -2.0)]
    return make_candles(closes, timeframe="M1", minutes=1,
                        start=START + timedelta(hours=3, minutes=43))


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
        decision_id="chal-test", time_utc=START, symbol=SYMBOL,
        direction=direction,
        setup_type=f"challenge_breakout[STRONG,lot={lot:.2f}]",
        thesis="test momentum", invalidation_price=stop,
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
                  entry=3360.0, stop=3363.0):
    return BrokerPosition(
        ticket=ticket, symbol=BROKER_SYMBOL, direction=direction,
        lot_size=0.05, entry_price=entry, stop_loss=stop,
        take_profit=None, current_price=3355.0, profit=profit,
    )


def planner():
    return ChallengeTradePlanner(limits=make_challenge_limits(SYMBOL))


def plan(p, decision, *, positions=(), news=None, risk_inputs=None,
         account=None, broker=None):
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
    )


# -- profile / envelope -----------------------------------------------------------

def test_demo_challenge_profile_exists_with_challenge_envelope():
    profile = get_profile(CHALLENGE_PROFILE_NAME)
    assert profile.envelope == "demo_challenge"
    assert profile.max_open_positions == CHALLENGE_MAX_OPEN_POSITIONS == 3
    assert profile.max_risk_per_trade == CHALLENGE_MAX_RISK_PER_TRADE
    assert profile.duration_minutes is None  # continuous service profile
    assert profile.max_orders is None
    limits = profile.risk_limits(SYMBOL)
    challenge_limits = make_challenge_limits(SYMBOL)
    assert limits.max_open_trades == challenge_limits.max_open_trades == 3
    assert limits.max_risk_per_trade == challenge_limits.max_risk_per_trade
    assert limits.max_daily_loss == challenge_limits.max_daily_loss
    assert limits.max_weekly_loss == challenge_limits.max_weekly_loss


def test_challenge_envelope_is_reserved_for_the_demo_challenge_profile():
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


# -- fixed-lot momentum sizing -----------------------------------------------------

def test_normal_momentum_chooses_005():
    pipe = make_challenge_pipeline(SYMBOL)
    lot, why = pipe._fixed_lot(
        MomentumState.NORMAL, SessionType.LONDON, 2000.0, 2.5, 0.2
    )
    assert lot == LOT_NORMAL == 0.05
    assert "NORMAL" in why


def test_very_strong_momentum_chooses_010():
    pipe = make_challenge_pipeline(SYMBOL)
    lot, _ = pipe._fixed_lot(
        MomentumState.STRONG, SessionType.LONDON, 2000.0, 2.5, 0.2
    )
    assert lot == LOT_STRONG == 0.10


def test_low_liquidity_demotes_010_to_005_but_does_not_block():
    pipe = make_challenge_pipeline(SYMBOL)
    lot, why = pipe._fixed_lot(
        MomentumState.STRONG, SessionType.LOW_LIQUIDITY, 2000.0, 2.5, 0.2
    )
    assert lot == LOT_NORMAL  # demoted, NOT blocked
    assert "demoted" in why


def test_survival_cap_demotes_then_skips_never_resizes_the_stop():
    pipe = make_challenge_pipeline(SYMBOL)
    # 0.10 lot at a 7.0 stop risks $72 > $60 cap -> demote to 0.05 ($36).
    lot, why = pipe._fixed_lot(
        MomentumState.STRONG, SessionType.LONDON, 2000.0, 7.0, 0.2
    )
    assert lot == LOT_NORMAL
    assert "demotes" in why
    # Even 0.05 over the cap -> skip the cycle (no shrunken stop, no 0.01).
    lot, why = pipe._fixed_lot(
        MomentumState.STRONG, SessionType.LONDON, 2000.0, 12.5, 0.2
    )
    assert lot is None
    assert "survival cap" in why


# -- end-to-end momentum decisions ---------------------------------------------------

def test_strong_breakdown_produces_a_short_with_tactical_stop_and_010():
    pipe = make_challenge_pipeline(SYMBOL)
    result = pipe.decide(pipeline_input(
        m5_breakdown(3.0), m15=m15_bearish(), m1=m1_with_local_swing(),
    ))
    assert result.stage is PipelineStage.RISK_EVALUATED
    assert result.approved, result.reason
    decision = result.decision
    assert decision.direction is Direction.SHORT
    assert decision.stop_loss is not None and decision.take_profits
    stop_distance = decision.stop_loss - decision.entry_price
    assert 0 < stop_distance <= 8.0  # tactical/local, never structural
    assert result.lot_size == LOT_STRONG
    assert "lot=0.10" in decision.setup_type
    ch = result.context.challenge
    assert ch["momentum_state"] == "STRONG"
    assert ch["lot_decision"] == "0.10"
    assert ch["tactical_stop_source"] in (
        "m1_local_swing", "m5_local_swing", "rejection_wick",
        "pullback_extreme",
    )


def test_normal_momentum_produces_005_lot():
    pipe = make_challenge_pipeline(SYMBOL)
    result = pipe.decide(pipeline_input(
        m5_breakdown(1.2), m15=m15_bearish(),
        m1=m1_with_local_swing(entry_zone=3381.4),
    ))
    assert result.approved, result.reason
    assert result.context.challenge["momentum_state"] == "NORMAL"
    assert result.lot_size == LOT_NORMAL
    assert "lot=0.05" in result.decision.setup_type


def test_no_local_stop_means_skip_not_a_structural_stop():
    # A vertical collapse with no pullback: momentum is real but no local
    # M1/M5 invalidation exists nearby. demo_challenge must SKIP the cycle,
    # never fall back to a huge structural stop.
    closes = [3400.0 - 0.5 * (i + 1) for i in range(40)]
    closes += [3380.0 - 7.0]  # 7-dollar breakdown candle
    result = make_challenge_pipeline(SYMBOL).decide(pipeline_input(
        make_candles(closes), m15=m15_bearish(),
    ))
    assert not result.approved
    assert result.stage is PipelineStage.HYPOTHESIS
    assert "waiting for local swing stop" in result.reason
    assert "structural stop is NOT used" in result.reason


def test_weak_momentum_waits_with_an_exact_reason():
    closes = [3390.0 + (0.4 if i % 2 == 0 else -0.4) for i in range(50)]
    result = make_challenge_pipeline(SYMBOL).decide(pipeline_input(
        make_candles(closes),
        m15=make_candles([3390.0 + (0.5 if i % 2 else -0.5)
                          for i in range(30)],
                         timeframe="M15", minutes=15,
                         start=START - timedelta(hours=6)),
    ))
    assert not result.approved
    assert "momentum weak" in result.reason
    assert result.context.challenge["direction"] == "NONE"


def test_macro_futures_unavailable_never_blocks_the_challenge_pipeline():
    # The challenge pipeline consults NO macro/futures/news provider at all:
    # a fully-approved decision with zero external context proves
    # unavailability is neutral.
    result = make_challenge_pipeline(SYMBOL).decide(pipeline_input(
        m5_breakdown(3.0), m15=m15_bearish(), m1=m1_with_local_swing(),
        futures_candles=None,
    ))
    assert result.approved, result.reason


def test_spread_too_high_waits():
    result = make_challenge_pipeline(SYMBOL).decide(pipeline_input(
        m5_breakdown(3.0), m15=m15_bearish(), m1=m1_with_local_swing(),
        spread=1.5,
    ))
    assert not result.approved
    assert "spread too high" in result.reason


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


def test_addon_allowed_only_when_first_trade_is_in_floating_profit():
    result = plan(planner(), challenge_decision(lot=0.05),
                  positions=[open_position(profit=15.0)])
    assert result.approved, result.reasons
    assert result.is_addon
    assert result.pyramid is not None and result.pyramid.allowed


def test_addon_blocked_when_first_trade_is_losing():
    result = plan(planner(), challenge_decision(lot=0.05),
                  positions=[open_position(profit=-8.0)])
    assert not result.approved
    assert PlanCheck.PYRAMIDING_BLOCKED in result.failed_checks
    assert "not in profit" in result.reasons[0]


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
    positions = [open_position(ticket=i, profit=10.0 + i) for i in (1, 2, 3)]
    result = plan(planner(), challenge_decision(lot=0.05),
                  positions=positions)
    assert not result.approved
    assert PlanCheck.MAX_POSITIONS in result.failed_checks


def test_001_fallback_only_on_margin_refusal():
    # Free margin refuses 0.05 -> the broker-minimum 0.01 fallback engages.
    tight = AccountSnapshot(balance=2000.0, free_margin=50.0, leverage=200)
    result = plan(planner(), challenge_decision(lot=0.05), account=tight)
    assert result.approved
    assert result.lot_size == 0.01
    assert "fallback" in result.sizing.reason
    # With normal margin the challenge lot is used; 0.01 is never a default.
    result = plan(planner(), challenge_decision(lot=0.05))
    assert result.lot_size == 0.05


def test_planner_survival_cap_blocks_never_a_structural_widening():
    wide = challenge_decision(lot=0.05, entry=3350.0, stop=3363.0)  # $13 stop
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
    assert not client.requests  # nothing reached order_send


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
    ChallengeTradePlanner + gateway, with a challenge-style decision."""
    from unittest.mock import MagicMock

    from src.broker.mt5_data_adapter import MT5DataAdapter
    from src.broker.mt5_settings import load_mt5_settings
    from src.execution.demo_session import (
        CONFIRMATION_TOKEN,
        SupervisedDemoSession,
    )
    from src.execution.kill_switch import KillSwitch
    from src.journal.journal import TradeJournal
    from src.strategy.pipeline import PipelineContext, PipelineResult
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
        decision_id="chal-e2e", time_utc=NOW, symbol=SYMBOL,
        direction=Direction.SHORT,
        setup_type="challenge_breakout[STRONG,lot=0.10]",
        thesis="strong short momentum", invalidation_price=stop,
        entry_price=entry, stop_loss=stop, take_profits=(2310.0,),
        confidence=0.8, uncertainty=0.2,
    )
    challenge = {"profile": "demo_challenge", "momentum_state": "STRONG",
                 "lot_decision": "0.10", "reason": "e2e"}
    result = PipelineResult(
        stage=PipelineStage.RISK_EVALUATED, approved=True, reason="ok",
        decision=decision, confidence=allow_confidence(),
        context=PipelineContext(
            session=None, htf_bias=None, regime=None, structure_bias=None,
            has_setup=True, challenge=challenge,
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
        profile_name=CHALLENGE_PROFILE_NAME,
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
    assert request["volume"] == pytest.approx(0.10)  # the FIXED challenge lot
    assert request["sl"] == pytest.approx(stop)
    # The challenge reasoning is journaled per cycle, enriched with the
    # live first-trade/add-on view.
    ch = outcome.stat.intel["challenge"]
    assert ch["momentum_state"] == "STRONG"
    assert ch["first_trade_profit_state"] == "NO_OPEN_POSITION"
    assert ch["add_on_allowed"] == "n/a (no position yet)"
    records = journal.records()
    assert any(r.lot_size == pytest.approx(0.10) for r in records)
