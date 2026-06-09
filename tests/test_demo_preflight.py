"""Tests for DEMO-001: demo execution preflight (gates only, no orders).

Proves:
- all 12 gates PASS with a correct demo environment + demo account,
- each wrong env flag fails its gate and blocks readiness,
- a REAL account fails the account gate,
- a missing broker symbol fails the symbol gate,
- the governor and gateway block a no-stop-loss decision (nothing sent),
- the kill switch engages/releases and the gateway honors it,
- journal probe round-trips (writable + restart-safe),
- order_send / order_check are NEVER called during preflight,
- the report is credential-free,
- without an MT5 client the MT5 gates are SKIPPED and readiness is blocked.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.data.enums import Direction
from src.data.schemas import TradeDecision
from src.execution import (
    DemoPreflight,
    ExecutionCheck,
    ExecutionFlags,
    ExecutionGateway,
    GateStatus,
    KillSwitch,
)
from src.risk import RiskGovernor, RiskLimits

UTC = timezone.utc
SECRET_PASSWORD = "S3cr3t-PW-do-not-leak"
LOGIN_VALUE = "99887766"


def ready_env(**overrides) -> dict:
    env = {
        "TRADING_MODE": "DEMO",
        "REAL_TRADING_ENABLED": "false",
        "ALLOW_REAL_ORDERS": "false",
        "ALLOW_DEMO_ORDERS": "true",
        "ALLOW_MT5_ORDER_SEND": "true",
        # Present in a real environment; the preflight must never echo them.
        "MT5_LOGIN": LOGIN_VALUE,
        "MT5_PASSWORD": SECRET_PASSWORD,
        "MT5_SERVER": "Exness-MT5Demo",
        "MT5_SYMBOL": "XAUUSDm",
    }
    env.update(overrides)
    return env


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2

    def __init__(self, *, trade_mode=0, symbol_found=True):
        self._trade_mode = trade_mode
        self._symbol_found = symbol_found
        self.symbol_select = MagicMock(return_value=True)
        self.order_send = MagicMock()
        self.order_check = MagicMock()

    def account_info(self):
        return _Obj(trade_mode=self._trade_mode, currency="USD",
                    balance=2000.0, login=int(LOGIN_VALUE))

    def symbol_info(self, symbol):
        if not self._symbol_found:
            return None
        return _Obj(volume_min=0.01, volume_step=0.01, trade_contract_size=100.0)

    def assert_no_trades(self):
        self.order_send.assert_not_called()
        self.order_check.assert_not_called()


def make_preflight(tmp_path, *, env=None, client="default", **overrides) -> DemoPreflight:
    if client == "default":
        client = FakeMT5()
    kwargs = dict(
        env=env or ready_env(),
        broker_symbol="XAUUSDm",
        client=client,
        journal_probe_path=tmp_path / "probe.jsonl",
        kill_switch=KillSwitch(tmp_path / "KILL_SWITCH"),
    )
    kwargs.update(overrides)
    return DemoPreflight(**kwargs)


def gate_map(report):
    return {g.name: g.status for g in report.gates}


# ---------------------------------------------------------------------------
# Full readiness
# ---------------------------------------------------------------------------

def test_all_gates_pass_with_ready_environment(tmp_path):
    client = FakeMT5()
    report = make_preflight(tmp_path, client=client).run()
    assert gate_map(report) == {
        "env_trading_mode_demo": GateStatus.PASS,
        "env_real_trading_disabled": GateStatus.PASS,
        "env_real_orders_disabled": GateStatus.PASS,
        "env_demo_orders_enabled": GateStatus.PASS,
        "env_mt5_order_send_enabled": GateStatus.PASS,
        "account_is_demo": GateStatus.PASS,
        "symbol_verified": GateStatus.PASS,
        "risk_governor_blocks_unsafe": GateStatus.PASS,
        "stop_loss_mandatory": GateStatus.PASS,
        "journal_writable": GateStatus.PASS,
        "state_persistence": GateStatus.PASS,
        "kill_switch_available": GateStatus.PASS,
    }
    assert report.ready is True
    client.assert_no_trades()


def test_preflight_never_calls_order_send(tmp_path):
    client = FakeMT5()
    make_preflight(tmp_path, client=client).run()
    client.assert_no_trades()


# ---------------------------------------------------------------------------
# Env flag gates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("override,gate", [
    (dict(TRADING_MODE="REAL"), "env_trading_mode_demo"),
    (dict(REAL_TRADING_ENABLED="true"), "env_real_trading_disabled"),
    (dict(ALLOW_REAL_ORDERS="true"), "env_real_orders_disabled"),
    (dict(ALLOW_DEMO_ORDERS="false"), "env_demo_orders_enabled"),
    (dict(ALLOW_MT5_ORDER_SEND="false"), "env_mt5_order_send_enabled"),
])
def test_wrong_env_flag_fails_its_gate(tmp_path, override, gate):
    report = make_preflight(tmp_path, env=ready_env(**override)).run()
    assert gate_map(report)[gate] is GateStatus.FAIL
    assert report.ready is False


# ---------------------------------------------------------------------------
# Account / symbol gates
# ---------------------------------------------------------------------------

def test_real_account_fails_preflight(tmp_path):
    client = FakeMT5(trade_mode=FakeMT5.ACCOUNT_TRADE_MODE_REAL)
    report = make_preflight(tmp_path, client=client).run()
    assert gate_map(report)["account_is_demo"] is GateStatus.FAIL
    assert report.ready is False
    client.assert_no_trades()


def test_contest_account_is_accepted_as_non_real(tmp_path):
    client = FakeMT5(trade_mode=FakeMT5.ACCOUNT_TRADE_MODE_CONTEST)
    report = make_preflight(tmp_path, client=client).run()
    assert gate_map(report)["account_is_demo"] is GateStatus.PASS


def test_missing_symbol_fails_preflight(tmp_path):
    client = FakeMT5(symbol_found=False)
    report = make_preflight(tmp_path, client=client).run()
    assert gate_map(report)["symbol_verified"] is GateStatus.FAIL
    assert report.ready is False


def test_symbol_gate_uses_exact_broker_case(tmp_path):
    client = FakeMT5()
    make_preflight(tmp_path, client=client).run()
    assert client.symbol_select.call_args.args[0] == "XAUUSDm"


def test_no_mt5_client_skips_mt5_gates_and_blocks_readiness(tmp_path):
    report = make_preflight(tmp_path, client=None).run()
    gates = gate_map(report)
    assert gates["account_is_demo"] is GateStatus.SKIPPED
    assert gates["symbol_verified"] is GateStatus.SKIPPED
    assert report.ready is False  # SKIPPED gates block readiness


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------

def test_kill_switch_engage_release_cycle(tmp_path):
    ks = KillSwitch(tmp_path / "KILL_SWITCH")
    assert ks.engaged is False
    ks.engage("test")
    assert ks.engaged is True
    ks.release()
    assert ks.engaged is False


def test_gateway_blocks_while_kill_switch_engaged(tmp_path):
    ks = KillSwitch(tmp_path / "KILL_SWITCH")
    ks.engage("halt")
    gateway = ExecutionGateway(
        RiskGovernor(RiskLimits(expected_symbol="XAUUSDM")),
        ExecutionFlags(), client=None,
        expected_symbol="XAUUSDM", kill_switch=ks,
    )
    now = datetime.now(UTC)
    decision = TradeDecision(
        decision_id="ks-probe", time_utc=now, symbol="XAUUSDM",
        direction=Direction.LONG, thesis="t", invalidation_price=2300.0,
        entry_price=2310.0, stop_loss=2300.0, take_profits=(2330.0,),
    )
    pf = DemoPreflight(env=ready_env(), broker_symbol="XAUUSDm",
                       journal_probe_path=tmp_path / "p.jsonl", kill_switch=ks)
    result = gateway.execute(decision, pf._probe_context(now))
    assert result.sent is False
    assert ExecutionCheck.KILL_SWITCH in result.failed_checks


def test_preflight_respects_already_engaged_kill_switch(tmp_path):
    # If the user has the kill switch engaged, preflight must not release it.
    ks = KillSwitch(tmp_path / "KILL_SWITCH")
    ks.engage("user halt")
    report = make_preflight(tmp_path, kill_switch=ks).run()
    assert ks.engaged is True  # untouched
    # Stop-loss gate is evaluated independently of the kill switch.
    assert gate_map(report)["stop_loss_mandatory"] is GateStatus.PASS


# ---------------------------------------------------------------------------
# Report hygiene
# ---------------------------------------------------------------------------

def test_report_contains_no_credentials(tmp_path):
    report = make_preflight(tmp_path).run()
    blob = repr(report.to_dict())
    assert SECRET_PASSWORD not in blob
    assert LOGIN_VALUE not in blob


def test_journal_probe_round_trips(tmp_path):
    report = make_preflight(tmp_path).run()
    gates = gate_map(report)
    assert gates["journal_writable"] is GateStatus.PASS
    assert gates["state_persistence"] is GateStatus.PASS
    assert (tmp_path / "probe.jsonl").exists()
