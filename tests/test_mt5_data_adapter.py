"""Tests for P1-002 MT5 demo data adapter.

Proves:
- settings load from env and validate required vars without leaking secrets,
- demo-only enforcement,
- connect + fetch of XAU/USD candles mapped into the Candle schema,
- timestamp normalization (broker time preserved, UTC normalized),
- non-XAUUSD symbols rejected,
- credentials are never exposed in repr/str,
- order_send (and other trade calls) are NEVER invoked.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.broker import (
    InvalidCredentialsError,
    MissingCredentialsError,
    MT5DataAdapter,
    MT5Settings,
    RealTradingForbiddenError,
    WrongSymbolError,
    load_mt5_settings,
)
from src.broker.errors import BrokerConnectionError, DataFetchError
from src.data.enums import Timeframe
from src.data.schemas import Candle

UTC = timezone.utc
SECRET_PASSWORD = "S3cr3t-PW-do-not-leak"
LOGIN_VALUE = "99887766"

# A fixed instant whose UTC rendering is 12:00.
BASE_DT_UTC = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
BASE_EPOCH = int(BASE_DT_UTC.timestamp())


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


def make_rate(epoch: int, o, h, l, c, tick_vol=100, spread=20, real_vol=0) -> dict:
    return {
        "time": epoch,
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "tick_volume": tick_vol,
        "spread": spread,
        "real_volume": real_vol,
    }


class _TickObj:
    """Attribute container mimicking MT5 named-tuple returns."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeMT5:
    """Minimal in-memory stand-in for the MetaTrader5 module.

    order_send / order_check are mocks so tests can assert they are never used.
    """

    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388
    TIMEFRAME_D1 = 16408

    def __init__(self, rates=None):
        self._rates = rates if rates is not None else [
            make_rate(BASE_EPOCH - 3600, 2300.0, 2310.0, 2295.0, 2305.0),
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
        self.symbol_info_tick = MagicMock(
            side_effect=lambda symbol: _TickObj(
                bid=2307.9, ask=2308.1, last=2308.0, time=BASE_EPOCH, volume=5
            )
        )
        self.account_info = MagicMock(
            side_effect=lambda: _TickObj(
                currency="USD", leverage=500, balance=2000.0, equity=2010.5,
                margin=12.5, margin_free=1998.0, margin_level=160.8,
                trade_allowed=True, login=int(LOGIN_VALUE),
            )
        )
        self.positions_total = MagicMock(return_value=0)
        # Trade functions that must NEVER be called by a data adapter.
        self.order_send = MagicMock()
        self.order_check = MagicMock()

    def assert_no_trades(self):
        self.order_send.assert_not_called()
        self.order_check.assert_not_called()


@pytest.fixture
def settings() -> MT5Settings:
    return load_mt5_settings(demo_env())


@pytest.fixture
def fake_mt5() -> FakeMT5:
    return FakeMT5()


@pytest.fixture
def adapter(settings, fake_mt5) -> MT5DataAdapter:
    return MT5DataAdapter(settings, client=fake_mt5)


# ---------------------------------------------------------------------------
# Settings loading and validation
# ---------------------------------------------------------------------------

def test_load_settings_from_env(settings):
    assert settings.login == int(LOGIN_VALUE)
    assert settings.server == "Exness-MT5Demo"
    assert settings.symbol == "XAUUSD"


@pytest.mark.parametrize("missing_var", ["MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"])
def test_missing_required_var_reports_name_only(missing_var):
    env = demo_env()
    env[missing_var] = ""
    with pytest.raises(MissingCredentialsError) as exc_info:
        load_mt5_settings(env)
    message = str(exc_info.value)
    assert missing_var in message
    # The secret value must never appear in the error.
    assert SECRET_PASSWORD not in message


def test_invalid_login_does_not_echo_value():
    env = demo_env(MT5_LOGIN="not-a-number")
    with pytest.raises(InvalidCredentialsError) as exc_info:
        load_mt5_settings(env)
    assert "not-a-number" not in str(exc_info.value)


def test_real_trading_enabled_is_rejected():
    with pytest.raises(RealTradingForbiddenError):
        load_mt5_settings(demo_env(REAL_TRADING_ENABLED="true"))


def test_non_demo_trading_mode_is_rejected():
    with pytest.raises(RealTradingForbiddenError):
        load_mt5_settings(demo_env(TRADING_MODE="REAL"))


def test_non_xau_symbol_in_config_is_rejected():
    with pytest.raises(RealTradingForbiddenError):
        load_mt5_settings(demo_env(MT5_SYMBOL="EURUSD"))


# ---------------------------------------------------------------------------
# Connection + data fetch
# ---------------------------------------------------------------------------

def test_connect_succeeds(adapter, fake_mt5):
    assert adapter.connect() is True
    fake_mt5.initialize.assert_called_once()
    fake_mt5.assert_no_trades()


def test_fetch_requires_connection(adapter):
    with pytest.raises(BrokerConnectionError):
        adapter.fetch_candles(Timeframe.H1, count=2)


def test_fetch_returns_candles(adapter, fake_mt5):
    adapter.connect()
    candles = adapter.fetch_candles(Timeframe.H1, count=2)
    assert len(candles) == 2
    assert all(isinstance(c, Candle) for c in candles)
    assert candles[-1].symbol == "XAUUSD"
    assert candles[-1].timeframe == "1H"
    assert candles[-1].close == pytest.approx(2308.0)
    fake_mt5.assert_no_trades()


def test_fetch_count_must_be_positive(adapter):
    adapter.connect()
    with pytest.raises(DataFetchError):
        adapter.fetch_candles(Timeframe.H1, count=0)


def test_fetch_handles_no_data(settings):
    client = FakeMT5()
    client.copy_rates_from_pos = MagicMock(return_value=None)
    adapter = MT5DataAdapter(settings, client=client)
    adapter.connect()
    with pytest.raises(DataFetchError):
        adapter.fetch_candles(Timeframe.H1, count=2)
    client.assert_no_trades()


def test_fetch_handles_empty_data(settings):
    client = FakeMT5(rates=[])
    adapter = MT5DataAdapter(settings, client=client)
    adapter.connect()
    with pytest.raises(DataFetchError):
        adapter.fetch_candles(Timeframe.H1, count=2)


# ---------------------------------------------------------------------------
# Symbol rejection
# ---------------------------------------------------------------------------

def test_wrong_symbol_rejected(adapter, fake_mt5):
    adapter.connect()
    with pytest.raises(WrongSymbolError):
        adapter.fetch_candles(Timeframe.H1, count=2, symbol="EURUSD")
    # Rejection must happen before any data call.
    fake_mt5.copy_rates_from_pos.assert_not_called()
    fake_mt5.assert_no_trades()


def test_symbol_case_insensitive_accepted(adapter):
    adapter.connect()
    candles = adapter.fetch_candles(Timeframe.H1, count=1, symbol="xauusd")
    assert candles[0].symbol == "XAUUSD"


# ---------------------------------------------------------------------------
# Case-sensitive broker symbols (e.g. Exness XAUUSDm) must be preserved
# ---------------------------------------------------------------------------

def test_settings_preserve_broker_symbol_case():
    settings = load_mt5_settings(demo_env(MT5_SYMBOL="XAUUSDm"))
    # Exact broker case is preserved for MT5 API calls...
    assert settings.symbol == "XAUUSDm"
    # ...while the canonical form (uppercase) is used only for validation.
    assert settings.canonical_symbol == "XAUUSDM"


def test_fetch_uses_exact_broker_symbol_case(fake_mt5):
    settings = load_mt5_settings(demo_env(MT5_SYMBOL="XAUUSDm"))
    adapter = MT5DataAdapter(settings, client=fake_mt5)
    adapter.connect()
    candles = adapter.fetch_candles(Timeframe.H1, count=2)

    # The MT5 API calls MUST receive the exact broker case (the bug fix).
    assert fake_mt5.symbol_select.call_args.args[0] == "XAUUSDm"
    assert fake_mt5.copy_rates_from_pos.call_args.args[0] == "XAUUSDm"
    # The Candle data-model field is canonicalized (uppercase) by the schema;
    # this is the canonical representation, NOT a value passed to MT5.
    assert candles[-1].symbol == "XAUUSDM"
    fake_mt5.assert_no_trades()


def test_canonical_match_still_uses_broker_case(fake_mt5):
    # Caller passes the uppercase canonical form; the adapter accepts it but
    # must still call MT5 with the exact configured broker case.
    settings = load_mt5_settings(demo_env(MT5_SYMBOL="XAUUSDm"))
    adapter = MT5DataAdapter(settings, client=fake_mt5)
    adapter.connect()
    adapter.fetch_candles(Timeframe.H1, count=1, symbol="XAUUSDM")

    assert fake_mt5.symbol_select.call_args.args[0] == "XAUUSDm"
    assert fake_mt5.copy_rates_from_pos.call_args.args[0] == "XAUUSDm"


# ---------------------------------------------------------------------------
# Timestamp normalization
# ---------------------------------------------------------------------------

def test_timestamp_default_offset_is_utc(adapter):
    adapter.connect()
    candle = adapter.fetch_candles(Timeframe.H1, count=2)[-1]
    assert candle.time_utc == BASE_DT_UTC
    assert candle.broker_time == BASE_DT_UTC
    assert candle.time_utc.utcoffset() == timedelta(0)


def test_timestamp_with_server_offset(fake_mt5):
    # Broker server is UTC+2: epoch wall-clock 12:00 is really 10:00 UTC.
    settings = load_mt5_settings(demo_env(MT5_SERVER_UTC_OFFSET_MINUTES="120"))
    adapter = MT5DataAdapter(settings, client=fake_mt5)
    adapter.connect()
    candle = adapter.fetch_candles(Timeframe.H1, count=2)[-1]
    assert candle.broker_time.utcoffset() == timedelta(hours=2)
    assert candle.broker_time.hour == 12  # preserved server wall-clock
    assert candle.time_utc.utcoffset() == timedelta(0)
    assert candle.time_utc.hour == 10  # normalized to UTC


# ---------------------------------------------------------------------------
# Credential exposure
# ---------------------------------------------------------------------------

def test_settings_repr_masks_credentials(settings):
    text = repr(settings) + str(settings)
    assert SECRET_PASSWORD not in text
    assert LOGIN_VALUE not in text
    assert "masked" in text.lower()


def test_adapter_repr_does_not_leak_credentials(adapter):
    assert SECRET_PASSWORD not in repr(adapter)


def test_order_send_never_called_in_full_cycle(adapter, fake_mt5):
    adapter.connect()
    adapter.fetch_candles(Timeframe.H1, count=2)
    adapter.fetch_candles(Timeframe.M5, count=1)
    adapter.fetch_tick()
    adapter.fetch_broker_state(BASE_DT_UTC)
    adapter.shutdown()
    fake_mt5.assert_no_trades()


# ---------------------------------------------------------------------------
# Read-only tick + broker state (LIVE-001)
# ---------------------------------------------------------------------------

def test_fetch_tick_returns_bid_ask_spread(adapter, fake_mt5):
    adapter.connect()
    tick = adapter.fetch_tick()
    assert tick.bid == pytest.approx(2307.9)
    assert tick.ask == pytest.approx(2308.1)
    assert tick.spread == pytest.approx(0.2)
    assert tick.time_utc == BASE_DT_UTC
    fake_mt5.assert_no_trades()


def test_fetch_tick_requires_connection(adapter):
    with pytest.raises(BrokerConnectionError):
        adapter.fetch_tick()


def test_fetch_tick_uses_exact_broker_symbol_case(fake_mt5):
    settings = load_mt5_settings(demo_env(MT5_SYMBOL="XAUUSDm"))
    adapter = MT5DataAdapter(settings, client=fake_mt5)
    adapter.connect()
    adapter.fetch_tick()
    assert fake_mt5.symbol_info_tick.call_args.args[0] == "XAUUSDm"


def test_fetch_tick_handles_no_data(settings):
    client = FakeMT5()
    client.symbol_info_tick = MagicMock(return_value=None)
    adapter = MT5DataAdapter(settings, client=client)
    adapter.connect()
    with pytest.raises(DataFetchError):
        adapter.fetch_tick()


def test_fetch_broker_state_reads_account_safely(adapter, fake_mt5):
    adapter.connect()
    state = adapter.fetch_broker_state(BASE_DT_UTC)
    assert state.connection_status.value == "CONNECTED"
    assert state.balance == pytest.approx(2000.0)
    assert state.equity == pytest.approx(2010.5)
    assert state.leverage == 500
    assert state.open_positions == 0
    assert state.trade_allowed is True
    # BrokerState carries no credential fields; its serialization must not
    # contain the login value or password.
    blob = state.model_dump_json()
    assert SECRET_PASSWORD not in blob
    assert LOGIN_VALUE not in blob
    fake_mt5.assert_no_trades()


def test_fetch_broker_state_disconnected_when_no_account_info(settings):
    client = FakeMT5()
    client.account_info = MagicMock(return_value=None)
    adapter = MT5DataAdapter(settings, client=client)
    adapter.connect()
    state = adapter.fetch_broker_state(BASE_DT_UTC)
    assert state.connection_status.value == "DISCONNECTED"
    assert state.trade_allowed is False
