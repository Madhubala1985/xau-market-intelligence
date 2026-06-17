"""Tests for the DEMO forward-test runner (src/execution/research_forward.py).

Uses fake adapter + fake gateway so the runner's state machine is exercised on
Linux without MT5: signal arming on a fresh bar, fill firing through the gateway
with the intent's SL/TP, invalidation cancelling WITHOUT an order, and the
hard demo-lock.
"""

from datetime import timedelta, timezone
from types import SimpleNamespace

import pytest

from src.data.enums import (
    BrokerConnectionStatus,
    Direction,
    Timeframe,
)
from src.data.schemas import BrokerState, Tick
from src.execution.gateway import ExecutionFlags, ExecutionStatus
from src.execution.research_forward import ResearchForwardRunner, intent_to_decision
from src.risk.position_sizing import PositionSizer
from research.setups.london_sweep_reclaim import LondonSweepReclaimLong

# Reuse the synthetic builders proven in the lab tests.
from tests.test_research_lab import _build_winning_day, _c

UTC = timezone.utc
DEMO_FLAGS = ExecutionFlags(
    trading_mode="DEMO", real_trading_enabled=False, allow_demo_orders=True,
    allow_real_orders=False, allow_mt5_order_send=True,
)


class FakeGateway:
    def __init__(self, flags=DEMO_FLAGS, status=ExecutionStatus.FILLED):
        self.flags = flags
        self.status = status
        self.calls = []

    def execute(self, decision, context):
        self.calls.append((decision, context))
        return SimpleNamespace(status=self.status, reason="fake demo accept")


class FakeAdapter:
    def __init__(self, m5, h1=None, balance=2000.0):
        self._m5 = m5
        self._h1 = h1 or []
        self.k = 0
        self.balance = balance

    def fetch_candles(self, tf, count):
        if tf == Timeframe.M5:
            return self._m5[max(0, self.k - count):self.k]
        return list(self._h1)

    def fetch_broker_state(self, now):
        return BrokerState(
            time_utc=now, connection_status=BrokerConnectionStatus.CONNECTED,
            symbol="XAUUSD", balance=self.balance, equity=self.balance,
            open_positions=0, trade_allowed=True,
        )

    def fetch_tick(self):
        last = self._m5[self.k - 1]
        return Tick(symbol="XAUUSD", broker_time=last.time_utc, time_utc=last.time_utc,
                    bid=last.close - 0.1, ask=last.close + 0.1)


def _drive(adapter, runner):
    """Feed bars one at a time; collect every emitted event."""
    events = []
    for k in range(1, len(adapter._m5) + 1):
        adapter.k = k
        events.extend(runner.step(now=adapter._m5[k - 1].time_utc + timedelta(seconds=1)))
    return events


def test_demo_lock_refuses_real():
    real_flags = ExecutionFlags(trading_mode="REAL")
    with pytest.raises(RuntimeError):
        ResearchForwardRunner(setups=[LondonSweepReclaimLong()],
                              adapter=FakeAdapter([]), gateway=FakeGateway(real_flags))


def test_signal_arms_then_fills_through_gateway():
    from datetime import datetime
    candles = _build_winning_day(datetime(2026, 6, 1, tzinfo=UTC))
    adapter = FakeAdapter(candles, balance=20000.0)  # enough for a >= min lot
    gw = FakeGateway()
    runner = ResearchForwardRunner(
        setups=[LondonSweepReclaimLong()], adapter=adapter, gateway=gw,
        sizer=PositionSizer(),
    )
    events = _drive(adapter, runner)

    kinds = [e.kind for e in events]
    assert "SIGNAL_ARMED" in kinds
    assert "FILL_ATTEMPT" in kinds
    # exactly one order routed through the gateway
    assert len(gw.calls) == 1
    decision, ctx = gw.calls[0]
    assert decision.direction == Direction.LONG
    assert decision.stop_loss < decision.entry_price          # long stop below entry
    assert decision.take_profits[0] > decision.entry_price    # long target above
    assert ctx.lot_size > 0
    assert "forward-test" in decision.thesis


def test_invalidation_cancels_without_order():
    from datetime import datetime
    day = datetime(2026, 6, 2, tzinfo=UTC)
    full = _build_winning_day(day)
    # Keep asian + sweep/reclaim/displacement + arm bar, then a bar that craters
    # below the swept low (1988) BEFORE any mitigation fill.
    london0 = day.replace(hour=0, minute=0).replace(hour=7)
    crash = _c(london0, 20, 2008, 2009, 1985, 1986)   # low 1985 <= invalidation 1988
    candles = full[:-3] + [crash]                      # drop mitigation+target bars
    adapter = FakeAdapter(candles)
    gw = FakeGateway()
    runner = ResearchForwardRunner(setups=[LondonSweepReclaimLong()],
                                   adapter=adapter, gateway=gw)
    events = _drive(adapter, runner)

    assert "SIGNAL_ARMED" in [e.kind for e in events]
    assert "INVALIDATED" in [e.kind for e in events]
    assert gw.calls == []                              # no order ever sent


def test_heartbeat_on_quiet_bar():
    from datetime import datetime
    day = datetime(2026, 6, 4, tzinfo=UTC).replace(hour=0)
    # A few calm Asian bars: no setup can trigger -> heartbeat each new bar.
    candles = [_c(day, i * 5, 2000, 2000.5, 1999.5, 2000) for i in range(3)]
    adapter = FakeAdapter(candles)
    runner = ResearchForwardRunner(setups=[LondonSweepReclaimLong()],
                                   adapter=adapter, gateway=FakeGateway())
    events = _drive(adapter, runner)
    assert events and all(e.kind == "HEARTBEAT" for e in events)
    # same-bar re-poll emits nothing (no duplicate heartbeat)
    assert runner.step(now=candles[-1].time_utc) == []


def test_intent_to_decision_carries_sl_tp():
    from datetime import datetime
    candles = _build_winning_day(datetime(2026, 6, 3, tzinfo=UTC))
    intent = LondonSweepReclaimLong().scan(
        __import__("research.setups.base", fromlist=["MarketData"]).MarketData(
            by_tf={Timeframe.M5: candles}))[0]
    now = candles[-1].time_utc
    d = intent_to_decision(intent, now, "XAUUSD")
    assert d.direction == Direction.LONG
    assert d.stop_loss == intent.stop
    assert d.take_profits == (intent.target,)
    assert d.invalidation_price == intent.invalidation_price
    assert d.symbol == "XAUUSD"
