"""Tests for P7-003 MT5 demo execution gateway.

Required:
- wrong symbol blocked,
- no SL blocked,
- duplicate blocked,
- order state logged,
- no credentials printed.

Plus real-money refusal and the safe (no-send) default.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.data.enums import BrokerConnectionStatus, DecisionStatus, Direction
from src.data.schemas import BrokerState, TradeDecision
from src.execution import (
    ExecutionCheck,
    ExecutionFlags,
    ExecutionGateway,
    ExecutionStatus,
    OrderState,
    load_execution_flags,
)
from src.risk import RiskContext, RiskGovernor

UTC = timezone.utc
NOW = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)

SECRET = "S3cr3t-PW"  # must never appear anywhere in gateway output


class FakeMT5:
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_RETCODE_DONE = 10009

    def __init__(self, accept: bool = True):
        retcode = self.TRADE_RETCODE_DONE if accept else 10004
        self.order_send = MagicMock(return_value=_SendResult(retcode, 555111))


class _SendResult:
    def __init__(self, retcode: int, order: int):
        self.retcode = retcode
        self.order = order


def long_decision(**overrides) -> TradeDecision:
    kwargs = dict(
        decision_id="D-1",
        time_utc=NOW,
        symbol="XAUUSD",
        direction=Direction.LONG,
        status=DecisionStatus.PROPOSED,
        thesis="sweep reclaim with displacement",
        invalidation_price=2295.0,
        entry_price=2300.0,
        stop_loss=2295.0,
        take_profits=(2310.0,),
    )
    kwargs.update(overrides)
    return TradeDecision(**kwargs)


def good_broker(**overrides) -> BrokerState:
    kwargs = dict(
        time_utc=NOW, connection_status=BrokerConnectionStatus.CONNECTED,
        symbol="XAUUSD", balance=2000.0, equity=2000.0, open_positions=0,
        trade_allowed=True,
    )
    kwargs.update(overrides)
    return BrokerState(**kwargs)


def good_context(**overrides) -> RiskContext:
    kwargs = dict(
        broker=good_broker(), current_spread=20.0, lot_size=0.02,
        intended_risk_pct=0.004, daily_loss_pct=0.0, weekly_loss_pct=0.0,
        trades_today=0, consecutive_losses=0, open_symbols=frozenset(),
        size_factor_hint=1.0,
    )
    kwargs.update(overrides)
    return RiskContext(**kwargs)


DEMO_FLAGS = ExecutionFlags(
    trading_mode="DEMO", real_trading_enabled=False, allow_demo_orders=True,
    allow_real_orders=False, allow_mt5_order_send=True,
)


def gateway(flags=DEMO_FLAGS, client=None) -> ExecutionGateway:
    return ExecutionGateway(RiskGovernor(), flags, client if client else FakeMT5())


# ---------------------------------------------------------------------------
# Happy path (demo, fully enabled) -> order sent
# ---------------------------------------------------------------------------

def test_demo_order_sent_when_approved_and_enabled():
    client = FakeMT5()
    r = gateway(client=client).execute(long_decision(), good_context())
    assert r.status is ExecutionStatus.FILLED
    assert r.sent is True
    assert r.order_ticket == 555111
    client.order_send.assert_called_once()


def test_order_state_logged():
    client = FakeMT5()
    r = gateway(client=client).execute(long_decision(), good_context())
    assert r.states == (
        OrderState.SIGNAL_CREATED,
        OrderState.RISK_APPROVED,
        OrderState.ORDER_PREPARED,
        OrderState.ORDER_SENT,
        OrderState.ORDER_ACCEPTED,
    )


def test_rejected_order_logged():
    client = FakeMT5(accept=False)
    r = gateway(client=client).execute(long_decision(), good_context())
    assert r.status is ExecutionStatus.REJECTED
    assert OrderState.ORDER_REJECTED in r.states
    assert r.sent is True


# ---------------------------------------------------------------------------
# Safe default: sending disabled -> dry-run, never calls order_send
# ---------------------------------------------------------------------------

def test_default_flags_never_send():
    client = FakeMT5()
    gw = ExecutionGateway(RiskGovernor(), ExecutionFlags(), client)  # default flags
    r = gw.execute(long_decision(), good_context())
    assert r.status is ExecutionStatus.DRY_RUN
    assert r.sent is False
    client.order_send.assert_not_called()
    assert r.states[-1] is OrderState.ORDER_PREPARED


# ---------------------------------------------------------------------------
# Real-money refusal
# ---------------------------------------------------------------------------

def test_real_orders_refused():
    client = FakeMT5()
    flags = ExecutionFlags(
        trading_mode="DEMO", allow_demo_orders=True, allow_mt5_order_send=True,
        allow_real_orders=True,  # real requested -> refuse
    )
    r = ExecutionGateway(RiskGovernor(), flags, client).execute(long_decision(), good_context())
    assert r.status is ExecutionStatus.REAL_FORBIDDEN
    assert r.sent is False
    client.order_send.assert_not_called()


def test_real_trading_enabled_refused():
    client = FakeMT5()
    flags = ExecutionFlags(
        trading_mode="DEMO", allow_demo_orders=True, allow_mt5_order_send=True,
        real_trading_enabled=True,
    )
    r = ExecutionGateway(RiskGovernor(), flags, client).execute(long_decision(), good_context())
    assert r.status is ExecutionStatus.REAL_FORBIDDEN
    client.order_send.assert_not_called()


def test_non_demo_mode_refused():
    client = FakeMT5()
    flags = ExecutionFlags(trading_mode="REAL", allow_demo_orders=True, allow_mt5_order_send=True)
    r = ExecutionGateway(RiskGovernor(), flags, client).execute(long_decision(), good_context())
    assert r.status is ExecutionStatus.REAL_FORBIDDEN
    client.order_send.assert_not_called()


# ---------------------------------------------------------------------------
# Pre-execution blocks (never send)
# ---------------------------------------------------------------------------

def test_wrong_symbol_blocked():
    client = FakeMT5()
    r = gateway(client=client).execute(long_decision(symbol="EURUSD"), good_context())
    assert r.status is ExecutionStatus.BLOCKED
    assert ExecutionCheck.WRONG_SYMBOL in r.failed_checks
    client.order_send.assert_not_called()


def test_no_stop_loss_blocked():
    client = FakeMT5()
    r = gateway(client=client).execute(long_decision(stop_loss=None), good_context())
    assert r.status is ExecutionStatus.BLOCKED
    assert ExecutionCheck.NO_STOP_LOSS in r.failed_checks
    client.order_send.assert_not_called()


def test_duplicate_blocked():
    client = FakeMT5()
    r = gateway(client=client).execute(
        long_decision(), good_context(open_symbols=frozenset({"XAUUSD"}))
    )
    assert r.status is ExecutionStatus.BLOCKED
    assert ExecutionCheck.DUPLICATE in r.failed_checks
    client.order_send.assert_not_called()


def test_blocked_state_logged():
    r = gateway().execute(long_decision(symbol="EURUSD"), good_context())
    assert r.states[-1] is OrderState.BLOCKED


def test_risk_block_prevents_send():
    client = FakeMT5()
    # Excessive risk -> governor blocks -> gateway blocks, no send.
    r = gateway(client=client).execute(long_decision(), good_context(intended_risk_pct=0.02))
    assert r.status is ExecutionStatus.BLOCKED
    assert ExecutionCheck.RISK_BLOCKED in r.failed_checks
    client.order_send.assert_not_called()


# ---------------------------------------------------------------------------
# No credentials printed / present
# ---------------------------------------------------------------------------

def test_no_credentials_in_request_or_result():
    client = FakeMT5()
    r = gateway(client=client).execute(long_decision(), good_context())
    request = client.order_send.call_args.args[0]
    blob = (repr(r) + " " + repr(request)).lower()
    for token in ("password", "login", "server", "secret", "token", SECRET.lower()):
        assert token not in blob


def test_flags_loader_reads_no_credentials():
    flags = load_execution_flags({
        "TRADING_MODE": "DEMO",
        "REAL_TRADING_ENABLED": "false",
        "ALLOW_DEMO_ORDERS": "true",
        "ALLOW_MT5_ORDER_SEND": "true",
        "ALLOW_REAL_ORDERS": "false",
        "MT5_PASSWORD": SECRET,  # must be ignored
    })
    blob = repr(flags).lower()
    assert SECRET.lower() not in blob
    assert flags.demo_send_enabled is True
