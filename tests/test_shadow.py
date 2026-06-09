"""Tests for P11-001 live shadow mode (decisions logged, real orders not sent)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.data.enums import BrokerConnectionStatus, DecisionStatus, Direction
from src.data.schemas import BrokerState, TradeDecision
from src.execution import (
    ExecutionFlags,
    ExecutionGateway,
    ShadowRunner,
)
from src.journal import TradeJournal
from src.risk import RiskContext, RiskGovernor

UTC = timezone.utc
T0 = datetime(2026, 6, 9, 0, 0, tzinfo=UTC)


def candle_at(i: int):
    from src.data.schemas import Candle

    t = T0 + i * timedelta(hours=1)
    base = 2300.0 + i
    return Candle(
        symbol="XAUUSD", timeframe="1H", broker_time=t, time_utc=t,
        open=base, high=base + 1, low=base - 1, close=base, tick_volume=100,
    )


def series(n: int):
    return [candle_at(i) for i in range(n)]


def long_then_notrade_strategy():
    """Emit a LONG on bar 0, a NO_TRADE on bar 1, nothing afterwards."""
    def strategy(history):
        t = len(history) - 1
        last = history[-1]
        if t == 0:
            return TradeDecision(
                decision_id="D-long", time_utc=last.time_utc, symbol="XAUUSD",
                direction=Direction.LONG, status=DecisionStatus.PROPOSED, thesis="t",
                invalidation_price=last.close - 5, entry_price=last.close,
                stop_loss=last.close - 5, take_profits=(last.close + 10,),
            )
        if t == 1:
            return TradeDecision(
                decision_id="D-nt", time_utc=last.time_utc, symbol="XAUUSD",
                direction=Direction.NO_TRADE, status=DecisionStatus.NO_TRADE,
                reason="regime unclear",
            )
        return None
    return strategy


class FakeMT5:
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_RETCODE_DONE = 10009

    def __init__(self):
        self.order_send = MagicMock()


def context_builder(candle, decision):
    broker = BrokerState(
        time_utc=candle.time_utc, connection_status=BrokerConnectionStatus.CONNECTED,
        symbol="XAUUSD", balance=2000.0, equity=2000.0, open_positions=0,
        trade_allowed=True,
    )
    return RiskContext(
        broker=broker, current_spread=20.0, lot_size=0.1, intended_risk_pct=0.004,
    )


# ---------------------------------------------------------------------------
# Live decisions logged
# ---------------------------------------------------------------------------

def test_decisions_logged(tmp_path):
    journal = TradeJournal(tmp_path / "shadow.jsonl")
    runner = ShadowRunner(long_then_notrade_strategy(), journal)
    report = runner.run(series(4))
    assert report.decisions_logged == 2  # LONG + NO_TRADE
    ids = [d.decision_id for d in journal.decisions()]
    assert ids == ["D-long", "D-nt"]


def test_no_trade_decisions_are_logged(tmp_path):
    journal = TradeJournal(tmp_path / "shadow.jsonl")
    ShadowRunner(long_then_notrade_strategy(), journal).run(series(4))
    assert any(d.direction is Direction.NO_TRADE for d in journal.decisions())


def test_decisions_persisted_restart_safe(tmp_path):
    path = tmp_path / "shadow.jsonl"
    ShadowRunner(long_then_notrade_strategy(), TradeJournal(path)).run(series(4))
    # A fresh journal on the same path reloads the logged decisions.
    assert len(TradeJournal(path).decisions()) == 2


# ---------------------------------------------------------------------------
# Real orders not sent
# ---------------------------------------------------------------------------

def test_pure_shadow_sends_nothing(tmp_path):
    journal = TradeJournal(tmp_path / "shadow.jsonl")
    report = ShadowRunner(long_then_notrade_strategy(), journal).run(series(4))
    assert report.orders_sent == 0
    # The runner holds no MT5 client at all.
    assert not hasattr(ShadowRunner, "order_send")


def test_routed_gateway_never_sends(tmp_path):
    journal = TradeJournal(tmp_path / "shadow.jsonl")
    client = FakeMT5()
    # Default flags -> demo send disabled -> dry-run only.
    gateway = ExecutionGateway(RiskGovernor(), ExecutionFlags(), client)
    runner = ShadowRunner(
        long_then_notrade_strategy(), journal,
        gateway=gateway, context_builder=context_builder,
    )
    report = runner.run(series(4))
    client.order_send.assert_not_called()
    assert report.orders_sent == 0
    assert all(not e.sent for e in report.executions)


def test_refuses_sending_enabled_gateway(tmp_path):
    journal = TradeJournal(tmp_path / "shadow.jsonl")
    sending_flags = ExecutionFlags(
        trading_mode="DEMO", allow_demo_orders=True, allow_mt5_order_send=True,
    )  # demo_send_enabled == True
    gateway = ExecutionGateway(RiskGovernor(), sending_flags, FakeMT5())
    with pytest.raises(ValueError):
        ShadowRunner(
            long_then_notrade_strategy(), journal,
            gateway=gateway, context_builder=context_builder,
        )


def test_gateway_requires_context_builder(tmp_path):
    journal = TradeJournal(tmp_path / "shadow.jsonl")
    gateway = ExecutionGateway(RiskGovernor(), ExecutionFlags(), FakeMT5())
    with pytest.raises(ValueError):
        ShadowRunner(long_then_notrade_strategy(), journal, gateway=gateway)
