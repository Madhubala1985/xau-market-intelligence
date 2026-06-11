"""Tests for BROKER-EXECUTION-001: order rejection diagnostics, live-price/
filling-mode request building, stops-level guard, journal execution events,
and honest terminal wording.

Root cause being guarded against (live evidence 2026-06-11): demo_challenge
found valid entries, the gateway built the market order with the ANALYSED
CANDLE CLOSE as price (stale by the time momentum fires) and NO type_filling,
the broker rejected, and nothing was persisted — the terminal printed the
contradictory "decision=BLOCKED reason: all risk checks passed".
"""

import json
from datetime import datetime, timedelta, timezone
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.data.enums import Direction
from src.data.schemas import TradeDecision
from src.execution.demo_session import CycleOutcome, CycleStat
from src.execution.gateway import (
    ExecutionCheck,
    ExecutionFlags,
    ExecutionGateway,
    ExecutionStatus,
    RETCODE_NAMES,
)
from src.execution.trading_service import ProgressPrinter
from src.journal.journal import TradeJournal
from src.risk.governor import RiskContext, RiskGovernor
from src.risk.state_tracker import RiskStateSnapshot
from src.strategy.challenge_momentum import make_challenge_limits
from tests.test_demo_challenge import (
    BROKER_SYMBOL,
    SYMBOL,
    broker_state,
    challenge_decision,
)

NOW = datetime(2026, 6, 11, 10, 26, tzinfo=timezone.utc)


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class RichFakeMT5:
    """MT5 stand-in WITH symbol_info / symbol_info_tick / margin calc."""

    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    TRADE_RETCODE_DONE = 10009

    def __init__(self, *, retcode=10009, comment="done", filling_mode=2,
                 stops_level=0, bid=3352.20, ask=3352.45):
        self._retcode = retcode
        self._comment = comment
        self._filling_mode = filling_mode
        self._stops_level = stops_level
        self._bid, self._ask = bid, ask
        self.requests = []

    def symbol_info(self, symbol):
        return _Obj(
            filling_mode=self._filling_mode, trade_stops_level=self._stops_level,
            trade_freeze_level=0, point=0.01, volume_min=0.01,
            volume_max=200.0, volume_step=0.01, trade_mode=4,
        )

    def symbol_info_tick(self, symbol):
        return _Obj(bid=self._bid, ask=self._ask,
                    time=int(NOW.timestamp()), volume=5)

    def order_calc_margin(self, order_type, symbol, volume, price):
        return volume * 100.0 * price / 200.0

    def order_send(self, request):
        self.requests.append(request)
        return _Obj(retcode=self._retcode, comment=self._comment, order=888001)


def enabled_flags():
    return ExecutionFlags(trading_mode="DEMO", allow_demo_orders=True,
                          allow_mt5_order_send=True)


def make_gateway(client, *, flags=None):
    return ExecutionGateway(
        RiskGovernor(make_challenge_limits(SYMBOL)),
        flags or enabled_flags(), client,
        expected_symbol=SYMBOL, broker_symbol=BROKER_SYMBOL,
        kill_switch=SimpleNamespace(engaged=False),
    )


def risk_context(lot=0.05):
    return RiskContext(
        broker=broker_state(NOW), current_spread=0.25, lot_size=lot,
        intended_risk_pct=lot * 100.0 * 2.75 / 2000.0,
    )


# -- request building: live price + broker filling mode ------------------------------

def test_market_buy_uses_live_ask_not_the_candle_close():
    client = RichFakeMT5(ask=3352.45)
    gateway = make_gateway(client)
    decision = challenge_decision(Direction.LONG, lot=0.05,
                                  entry=3350.0, stop=3347.5)
    result = gateway.execute(decision, risk_context())
    assert result.status is ExecutionStatus.FILLED
    # entry_price (candle close) was 3350.0; the request must carry the
    # live ask (root cause of the REQUOTE/INVALID_PRICE rejections).
    assert client.requests[0]["price"] == pytest.approx(3352.45)


def test_market_sell_uses_live_bid():
    client = RichFakeMT5(bid=3352.20)
    gateway = make_gateway(client)
    result = gateway.execute(challenge_decision(lot=0.05, entry=3350.0,
                                                stop=3352.5),
                             risk_context())
    assert result.status is ExecutionStatus.FILLED
    assert client.requests[0]["price"] == pytest.approx(3352.20)


def test_filling_mode_comes_from_broker_symbol_info():
    # bitmask 2 => only IOC supported (typical Exness market order)
    client = RichFakeMT5(filling_mode=2)
    make_gateway(client).execute(challenge_decision(lot=0.05), risk_context())
    assert client.requests[0]["type_filling"] == RichFakeMT5.ORDER_FILLING_IOC
    # bitmask 1 => only FOK supported
    client = RichFakeMT5(filling_mode=1)
    make_gateway(client).execute(challenge_decision(lot=0.05), risk_context())
    assert client.requests[0]["type_filling"] == RichFakeMT5.ORDER_FILLING_FOK


def test_no_symbol_info_omits_type_filling_and_falls_back_to_entry_price():
    class BareFake:
        TRADE_ACTION_DEAL = 1
        ORDER_TYPE_BUY = 0
        ORDER_TYPE_SELL = 1
        TRADE_RETCODE_DONE = 10009

        def __init__(self):
            self.order_send = MagicMock(
                return_value=_Obj(retcode=10009, order=1)
            )

    client = BareFake()
    decision = challenge_decision(lot=0.05, entry=3350.0)
    result = make_gateway(client).execute(decision, risk_context())
    assert result.status is ExecutionStatus.FILLED
    request = client.order_send.call_args.args[0]
    assert "type_filling" not in request
    assert request["price"] == pytest.approx(3350.0)
    assert request["symbol"] == "XAUUSDm"  # exact case preserved everywhere


# -- rejection diagnostics ------------------------------------------------------------

def test_rejection_carries_full_broker_diagnostics():
    client = RichFakeMT5(retcode=10030, comment="Unsupported filling mode")
    result = make_gateway(client).execute(
        challenge_decision(lot=0.05), risk_context()
    )
    assert result.status is ExecutionStatus.REJECTED
    diag = result.diagnostics
    assert diag["retcode"] == 10030
    assert diag["retcode_name"] == "INVALID_FILL"
    assert diag["comment"] == "Unsupported filling mode"
    assert "retcode=10030" in diag["retcode_label"]
    request = diag["request"]
    assert request["symbol"] == "XAUUSDm"  # exact broker case in diagnostics
    assert request["volume"] == 0.05
    assert request["sl"] is not None and request["tp"] is not None
    assert diag["bid"] == pytest.approx(3352.20)
    assert diag["ask"] == pytest.approx(3352.45)
    conditions = diag["symbol_conditions"]
    assert conditions["volume_min"] == 0.01
    assert conditions["volume_step"] == 0.01
    assert conditions["trade_mode"] == 4
    assert diag["margin_check"] is not None
    assert "retcode=10030 (INVALID_FILL)" in result.reason


def test_order_send_exception_is_diagnosed_not_swallowed():
    client = RichFakeMT5()
    client.order_send = MagicMock(side_effect=RuntimeError("ipc timeout"))
    result = make_gateway(client).execute(
        challenge_decision(lot=0.05), risk_context()
    )
    assert result.status is ExecutionStatus.REJECTED
    assert "ipc timeout" in result.reason
    assert "ipc timeout" in result.diagnostics["error"]


def test_known_retcodes_have_names():
    for code in (10004, 10015, 10016, 10019, 10030):
        assert RETCODE_NAMES[code] != "UNKNOWN"


# -- broker stops level ---------------------------------------------------------------

def test_sl_inside_broker_stops_level_blocks_and_never_sends():
    # stops_level=300 points = 3.00 USD minimum; tactical SL is 2.5+spread away
    client = RichFakeMT5(stops_level=300, bid=3350.0, ask=3350.25)
    result = make_gateway(client).execute(
        challenge_decision(lot=0.05, entry=3350.0, stop=3352.5),
        risk_context(),
    )
    assert result.status is ExecutionStatus.BLOCKED
    assert ExecutionCheck.STOPS_LEVEL in result.failed_checks
    assert "ORDER_BLOCKED_STOPS_LEVEL" in result.reason
    assert "broker minimum" in result.reason
    assert not client.requests  # an invalid SL is never sent


def test_wide_enough_stop_passes_the_stops_level_gate():
    client = RichFakeMT5(stops_level=100, bid=3350.0, ask=3350.25)  # 1.00 min
    result = make_gateway(client).execute(
        challenge_decision(lot=0.05, entry=3350.0, stop=3352.5),
        risk_context(),
    )
    assert result.status is ExecutionStatus.FILLED


# -- journal execution events ---------------------------------------------------------

def test_journal_events_roundtrip_restart_safe(tmp_path):
    journal = TradeJournal(tmp_path / "journal.jsonl")
    journal.log_event("ORDER_REJECTED", {"retcode": 10030, "broker": "order_send"})
    reloaded = TradeJournal(tmp_path / "journal.jsonl")
    events = reloaded.events()
    assert events == [
        {"event": "ORDER_REJECTED", "retcode": 10030, "broker": "order_send"}
    ]
    # decisions()/records() are unaffected by event lines
    assert reloaded.decisions() == [] and reloaded.records() == []


def _run_challenge_cycle(tmp_path, fake):
    """One real SupervisedDemoSession cycle with the challenge stack."""
    from src.broker.mt5_data_adapter import MT5DataAdapter
    from src.broker.mt5_settings import load_mt5_settings
    from src.execution.challenge_planner import ChallengeTradePlanner
    from src.execution.demo_session import (
        CONFIRMATION_TOKEN,
        SupervisedDemoSession,
    )
    from src.execution.kill_switch import KillSwitch
    from src.strategy.pipeline import (
        PipelineContext,
        PipelineResult,
        PipelineStage,
    )
    from src.strategy.scoring import ConfidenceResult, ScoreRecommendation
    from tests.test_demo_session import (
        NOW as SESSION_NOW,
        StubPipeline,
        clear_news,
        ready_preflight,
        sending_flags,
    )
    from tests.test_live_shadow import demo_env

    decision = TradeDecision(
        decision_id="chal-broker", time_utc=SESSION_NOW, symbol=SYMBOL,
        direction=Direction.SHORT,
        setup_type="challenge_breakout[NORMAL,lot=0.05]",
        thesis="momentum short", invalidation_price=2317.5,
        entry_price=2315.0, stop_loss=2317.5, take_profits=(2310.0,),
        confidence=0.65, uncertainty=0.3,
    )
    result = PipelineResult(
        stage=PipelineStage.RISK_EVALUATED, approved=True, reason="ok",
        decision=decision,
        confidence=ConfidenceResult(
            confidence=0.65, uncertainty=0.3,
            recommendation=ScoreRecommendation.ALLOW, size_factor=1.0,
            reason="x",
        ),
        context=PipelineContext(
            session=None, htf_bias=None, regime=None, structure_bias=None,
            has_setup=True, challenge={"profile": "demo_challenge"},
        ),
        lot_size=0.05,
    )
    adapter = MT5DataAdapter(load_mt5_settings(demo_env()), client=fake)
    adapter.connect()
    kill_switch = KillSwitch(tmp_path / "KILL_SWITCH")
    limits = make_challenge_limits(SYMBOL)
    journal = TradeJournal(tmp_path / "challenge_journal.jsonl")
    session = SupervisedDemoSession(
        adapter=adapter,
        pipeline=StubPipeline([result]),
        planner=ChallengeTradePlanner(limits=limits),
        gateway=ExecutionGateway(
            RiskGovernor(limits), sending_flags(), fake,
            expected_symbol=SYMBOL, broker_symbol=BROKER_SYMBOL,
            kill_switch=kill_switch,
        ),
        journal=journal,
        symbol=BROKER_SYMBOL,
        confirmation=CONFIRMATION_TOKEN,
        preflight=ready_preflight(),
        news_guard=clear_news(tmp_path),
        kill_switch=kill_switch,
        max_orders=None,
        profile_name="demo_challenge",
        hard_max_trades=10, hard_max_open=3,
        max_daily_loss=0.05, max_weekly_loss=0.10,
        risk_pct=0.03,
        now=lambda: SESSION_NOW,
        monotonic=MagicMock(side_effect=range(0, 100000, 10)),
        sleep=MagicMock(),
    )
    return session.run_cycle(), journal


def test_broker_rejection_is_journaled_and_searchable(tmp_path):
    from tests.test_demo_session import FakeMT5Trading

    class RejectingFake(FakeMT5Trading):
        def __init__(self):
            super().__init__()
            self.order_send = MagicMock(side_effect=self._reject)

        def _reject(self, request):
            if request["action"] == self.TRADE_ACTION_SLTP:
                return self._order_send(request)
            return _Obj(retcode=10030, comment="Unsupported filling mode")

    outcome, journal = _run_challenge_cycle(tmp_path, RejectingFake())

    assert outcome.stat.entry_action == "REJECTED"
    # The full request is in the terminal detail — no more bare
    # "demo order rejected by broker".
    assert "retcode=10030" in outcome.stat.entry_detail
    assert "request_symbol=XAUUSDm" in outcome.stat.entry_detail
    # Persisted, typed journal events.
    events = journal.events()
    kinds = [e["event"] for e in events]
    assert "ORDER_ATTEMPTED" in kinds and "ORDER_REJECTED" in kinds
    rejected = next(e for e in events if e["event"] == "ORDER_REJECTED")
    assert rejected["retcode"] == 10030
    assert rejected["symbol"] == "XAUUSDm"  # exact broker case in the journal
    assert rejected["request"]["symbol"] == "XAUUSDm"
    # Searchable exactly as the operator greps:
    #   Select-String -Pattern "ORDER_REJECTED","retcode","broker"
    raw = journal.path.read_text(encoding="utf-8")
    assert "ORDER_REJECTED" in raw and "retcode" in raw and "broker" in raw
    # Diagnostics surfaced to the cycle intel for the terminal.
    assert outcome.stat.intel["order_rejection"]["retcode"] == 10030


def test_successful_send_journals_attempted_and_sent_events(tmp_path):
    from tests.test_demo_session import FakeMT5Trading

    outcome, journal = _run_challenge_cycle(tmp_path, FakeMT5Trading())
    assert outcome.stat.entry_action == "SENT"
    kinds = [e["event"] for e in journal.events()]
    assert kinds == ["ORDER_ATTEMPTED", "ORDER_SENT"]
    sent = journal.events()[-1]
    assert sent["symbol"] == "XAUUSDm" and sent["ticket"] is not None


def test_order_send_exception_journals_order_error(tmp_path):
    from tests.test_demo_session import FakeMT5Trading

    class ExplodingFake(FakeMT5Trading):
        def __init__(self):
            super().__init__()
            self.order_send = MagicMock(side_effect=self._maybe_explode)

        def _maybe_explode(self, request):
            if request["action"] == self.TRADE_ACTION_SLTP:
                return self._order_send(request)
            raise OSError("terminal connection lost")

    outcome, journal = _run_challenge_cycle(tmp_path, ExplodingFake())
    # the gateway converts the exception into a diagnosed REJECTED result
    assert outcome.stat.entry_action == "REJECTED"
    rejected = next(
        e for e in journal.events() if e["event"] == "ORDER_REJECTED"
    )
    assert "terminal connection lost" in rejected["error"]


# -- terminal wording -----------------------------------------------------------------

def _cycle_outcome(stat):
    return CycleOutcome(
        stat=stat, bid=4093.50, ask=4093.73, positions=(),
        reconciliation_clean=True,
        risk=RiskStateSnapshot(
            time_utc=NOW, daily_loss_pct=0.0, weekly_loss_pct=0.0,
            trades_today=0, consecutive_losses=0, open_symbols=frozenset(),
        ),
        events=(), orders_sent_total=0, orders_simulated_total=0,
        violations_total=0, decisions_total=1,
    )


def test_terminal_prints_broker_verdict_and_request_not_contradiction():
    stat = CycleStat(
        time_utc=NOW, stage="RISK_EVALUATED", direction="LONG", approved=True,
        reason="all risk checks passed",  # the old contradictory text
        spread_price=0.23, entry_action="REJECTED",
        entry_detail="retcode=10030 ...",
        intel={"order_rejection": {
            "retcode": 10030, "retcode_name": "INVALID_FILL",
            "retcode_label": "retcode=10030 (INVALID_FILL) "
                             "comment='Unsupported filling mode'",
            "request": {"symbol": "XAUUSDm", "volume": 0.05,
                        "price": 4093.73, "sl": 4090.44, "tp": 4100.31,
                        "type_filling": 1},
            "bid": 4093.50, "ask": 4093.73,
            "symbol_conditions": {"trade_mode": 4, "volume_min": 0.01,
                                  "volume_step": 0.01, "stops_level": 0,
                                  "freeze_level": 0, "filling_mode": 2},
        }},
    )
    stream = StringIO()
    ProgressPrinter(stream=stream).cycle(
        1, _cycle_outcome(stat),
        decision_label="ORDER_REJECTED_BY_BROKER", market_state="OPEN",
        daily_pnl=0.0, risk_label="OK", news_label="NEWS_CLEAR",
        kill_label="off", next_poll_seconds=30,
    )
    out = stream.getvalue()
    assert "decision=ORDER_REJECTED_BY_BROKER" in out
    assert "reason=retcode=10030 (INVALID_FILL)" in out
    assert "request_symbol=XAUUSDm" in out
    assert "request_volume=0.05" in out
    assert "request_sl=4090.44" in out
    assert "request_tp=4100.31" in out
    # the contradictory wording is gone
    assert "reason: all risk checks passed" not in out


def test_service_labels_rejection_honestly(tmp_path):
    from src.execution.session_profiles import get_profile
    from src.execution.trading_service import BannerInfo, TradingService

    stat = CycleStat(
        time_utc=NOW, stage="RISK_EVALUATED", direction="LONG", approved=True,
        reason="all risk checks passed", spread_price=0.23,
        entry_action="REJECTED", entry_detail="retcode=10030",
    )
    stream = StringIO()
    service = TradingService(
        session=SimpleNamespace(decisions_logged=1, orders_sent=0,
                                orders_simulated=0, orders_rejected=1,
                                violations=0),
        journal=TradeJournal(tmp_path / "j.jsonl"),
        kill_switch=SimpleNamespace(engaged=False),
        profile=get_profile("demo_challenge"),
        printer=ProgressPrinter(stream=stream),
        banner=BannerInfo(
            profile="demo_challenge", execution_mode="EXECUTION",
            account_login_masked="****11", account_type="DEMO",
            server="x", symbol="XAUUSDm", risk_summary="x", news_status="x",
            kill_switch_status="absent", journal_path="x", report_dir="x",
        ),
        report_dir=tmp_path,
        now=lambda: NOW,
    )
    service._print_cycle(1, _cycle_outcome(stat), NOW)
    out = stream.getvalue()
    assert "decision=ORDER_REJECTED_BY_BROKER" in out
    assert "decision=BLOCKED" not in out
