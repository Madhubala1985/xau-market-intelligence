"""Tests for WINMT5-001 MT5 demo connectivity validation.

Proves the validator:
- runs all 10 read-only proofs against an injected client,
- NEVER calls order_send / order_check,
- refuses a REAL account,
- reports a clear failure on a wrong/missing symbol,
- never leaks credential values into the report,
and that the runner classifies a no-MetaTrader5 host as ENVIRONMENT_ISSUE
(no faked validation).
"""

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.broker import (
    CheckStatus,
    MT5ConnectivityValidator,
    MT5Settings,
    load_mt5_settings,
)

UTC = timezone.utc
SECRET_PASSWORD = "S3cr3t-PW-do-not-leak"
LOGIN_VALUE = "99887766"
BASE_EPOCH = int(datetime(2026, 6, 9, 12, 0, tzinfo=UTC).timestamp())

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER_PATH = REPO_ROOT / "scripts" / "winmt5_validate.py"


def demo_env(**overrides) -> dict:
    env = {
        "TRADING_MODE": "DEMO",
        "MT5_ACCOUNT_TYPE": "DEMO",
        "REAL_TRADING_ENABLED": "false",
        "MT5_LOGIN": LOGIN_VALUE,
        "MT5_PASSWORD": SECRET_PASSWORD,
        "MT5_SERVER": "Exness-MT5Demo",
        "MT5_SYMBOL": "XAUUSD",
    }
    env.update(overrides)
    return env


def make_rate(epoch, o, h, l, c, tick_vol=100, spread=20, real_vol=0) -> dict:
    return {
        "time": epoch, "open": o, "high": h, "low": l, "close": c,
        "tick_volume": tick_vol, "spread": spread, "real_volume": real_vol,
    }


class _Obj:
    """Simple attribute container mimicking MT5 named-tuple returns."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeMT5:
    """Read-only MT5 stand-in. Trade functions are mocks asserted to be unused."""

    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388
    TIMEFRAME_D1 = 16408

    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2

    def __init__(self, *, trade_mode=0, symbol_found=True, rates=None):
        self._trade_mode = trade_mode
        self._symbol_found = symbol_found
        self._rates = rates if rates is not None else [
            make_rate(BASE_EPOCH - 60, 2300.0, 2310.0, 2295.0, 2305.0),
            make_rate(BASE_EPOCH, 2305.0, 2312.0, 2301.0, 2308.0),
        ]
        self.initialize = MagicMock(return_value=True)
        self.login = MagicMock(return_value=True)
        self.shutdown = MagicMock(return_value=None)
        self.symbol_select = MagicMock(return_value=True)
        self.last_error = MagicMock(return_value=(0, "ok"))
        self.copy_rates_from_pos = MagicMock(
            side_effect=lambda symbol, tf, start, count: list(self._rates)[:count]
        )
        # Trade functions that must NEVER be called.
        self.order_send = MagicMock()
        self.order_check = MagicMock()

    def account_info(self):
        return _Obj(trade_mode=self._trade_mode, currency="USD", leverage=500,
                    balance=2000.0, server="Exness-MT5Demo", login=int(LOGIN_VALUE))

    def symbol_info(self, symbol):
        if not self._symbol_found:
            return None
        return _Obj(trade_contract_size=100.0, digits=2, point=0.01,
                    volume_min=0.01, volume_step=0.01, volume_max=200.0, spread=20)

    def symbol_info_tick(self, symbol):
        return _Obj(bid=2307.9, ask=2308.1, last=2308.0, time=BASE_EPOCH)

    def assert_no_trades(self):
        self.order_send.assert_not_called()
        self.order_check.assert_not_called()


@pytest.fixture
def settings() -> MT5Settings:
    return load_mt5_settings(demo_env())


# ---------------------------------------------------------------------------
# Full validation
# ---------------------------------------------------------------------------

def test_full_validation_passes(settings):
    client = FakeMT5()
    report = MT5ConnectivityValidator(settings).validate(client)
    assert report.all_proven
    names = {c.name: c.status for c in report.checks}
    for required in (
        "terminal_path_configured", "demo_credentials_loaded", "mt5_initialize",
        "demo_login", "account_is_demo", "symbol_detected", "symbol_info_read",
        "candles_fetched", "spread_read", "no_order_send",
    ):
        assert names[required] is CheckStatus.PASS
    client.assert_no_trades()


def test_validation_never_calls_order_send(settings):
    client = FakeMT5()
    MT5ConnectivityValidator(settings).validate(client)
    client.order_send.assert_not_called()
    client.order_check.assert_not_called()


def test_contest_account_is_accepted_as_non_real(settings):
    client = FakeMT5(trade_mode=FakeMT5.ACCOUNT_TRADE_MODE_CONTEST)
    report = MT5ConnectivityValidator(settings).validate(client)
    names = {c.name: c.status for c in report.checks}
    assert names["account_is_demo"] is CheckStatus.PASS


def test_real_account_is_refused(settings):
    client = FakeMT5(trade_mode=FakeMT5.ACCOUNT_TRADE_MODE_REAL)
    report = MT5ConnectivityValidator(settings).validate(client)
    names = {c.name: c.status for c in report.checks}
    assert names["account_is_demo"] is CheckStatus.FAIL
    assert report.passed is False
    client.assert_no_trades()


def test_missing_symbol_reports_failure(settings):
    client = FakeMT5(symbol_found=False)
    report = MT5ConnectivityValidator(settings).validate(client)
    names = {c.name: c.status for c in report.checks}
    assert names["symbol_detected"] is CheckStatus.FAIL
    assert names["symbol_info_read"] is CheckStatus.SKIPPED


def test_validator_preserves_case_sensitive_broker_symbol():
    # Exness uses a case-sensitive suffix: XAUUSDm. Every MT5 API call must
    # receive that exact case, never an uppercased XAUUSDM.
    settings = load_mt5_settings(demo_env(MT5_SYMBOL="XAUUSDm"))
    client = FakeMT5()
    # Spy on the read-only symbol calls while keeping their behaviour.
    client.symbol_info = MagicMock(side_effect=client.symbol_info)
    client.symbol_info_tick = MagicMock(side_effect=client.symbol_info_tick)

    report = MT5ConnectivityValidator(settings).validate(client)

    assert report.all_proven
    assert report.symbol == "XAUUSDm"
    assert client.symbol_select.call_args.args[0] == "XAUUSDm"
    assert client.symbol_info.call_args.args[0] == "XAUUSDm"
    assert client.symbol_info_tick.call_args.args[0] == "XAUUSDm"
    assert client.copy_rates_from_pos.call_args.args[0] == "XAUUSDm"
    client.assert_no_trades()


def test_facts_have_contract_and_spread(settings):
    report = MT5ConnectivityValidator(settings).validate(FakeMT5())
    assert report.facts["symbol_contract_size"] == 100.0
    assert report.facts["spread_price"] == pytest.approx(0.2)
    assert report.facts["candles_fetched_count"] == 5 or report.facts["candles_fetched_count"] >= 1


def test_report_contains_no_credentials(settings):
    report = MT5ConnectivityValidator(settings).validate(FakeMT5())
    blob = repr(report.to_dict())
    assert SECRET_PASSWORD not in blob
    assert LOGIN_VALUE not in blob  # login number is never written to the report


def test_connect_failure_skips_dependent_checks():
    settings = load_mt5_settings(demo_env())
    client = FakeMT5()
    client.initialize = MagicMock(return_value=False)  # initialize fails
    report = MT5ConnectivityValidator(settings).validate(client)
    names = {c.name: c.status for c in report.checks}
    assert names["mt5_initialize"] is CheckStatus.FAIL
    assert names["candles_fetched"] is CheckStatus.SKIPPED
    client.assert_no_trades()


# ---------------------------------------------------------------------------
# Runner: environment classification (no faking on a host without MetaTrader5)
# ---------------------------------------------------------------------------

def _load_runner():
    spec = importlib.util.spec_from_file_location("winmt5_validate", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runner_classifies_missing_mt5_as_environment_issue():
    runner = _load_runner()
    # On this Linux/WSL host MetaTrader5 is not importable.
    client, reason = runner.try_import_mt5()
    assert client is None
    assert runner.classify_environment(client) == "ENVIRONMENT_ISSUE"


def test_environment_issue_report_is_honest_not_faked():
    runner = _load_runner()
    report = runner.build_environment_issue_report(
        "ENVIRONMENT_ISSUE", "MetaTrader5 not importable: ModuleNotFoundError", []
    )
    assert report["outcome"] == "ENVIRONMENT_ISSUE"
    names = {c["name"]: c["status"] for c in report["checks"]}
    # Live proofs are NOT claimed: 3 is an environment issue, 4-9 are skipped.
    assert names["mt5_initialize"] == "ENVIRONMENT_ISSUE"
    for skipped in ("demo_login", "account_is_demo", "symbol_detected",
                    "symbol_info_read", "candles_fetched", "spread_read"):
        assert names[skipped] == "SKIPPED"
    assert names["no_order_send"] == "PASS"
    assert report["bridge_plan"]


def test_environment_issue_flags_missing_credentials_by_name():
    runner = _load_runner()
    report = runner.build_environment_issue_report(
        "ENVIRONMENT_ISSUE", "n/a", ["MT5_LOGIN", "MT5_SERVER"]
    )
    names = {c["name"]: c for c in report["checks"]}
    assert names["demo_credentials_loaded"]["status"] == "FAIL"
    assert "MT5_LOGIN" in names["demo_credentials_loaded"]["detail"]


def test_runner_markdown_renders_required_sections():
    runner = _load_runner()
    report = runner.build_environment_issue_report("ENVIRONMENT_ISSUE", "n/a", [])
    md = runner.render_markdown(report, generated_at="2026-06-09T00:00:00Z")
    assert "# MT5 Demo Connectivity Validation (WINMT5-001)" in md
    assert "## Proof checklist" in md
    assert "## Windows MT5 runner / bridge plan" in md
    assert "FORBIDDEN" in md


def test_runner_source_has_no_order_send_call():
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "order_send(" not in source
    assert ("REAL_TRADING_ENABLED" + "=true") not in source
    assert ("ALLOW_REAL_ORDERS" + "=true") not in source
