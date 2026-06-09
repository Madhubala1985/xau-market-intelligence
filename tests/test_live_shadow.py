"""Tests for LIVE-001: live MT5 read-only data -> DecisionPipeline -> ShadowRunner.

Proves:
- live cycles fetch read-only MT5 data and journal every decision,
- the exact broker symbol case (XAUUSDm) is used for every MT5 API call,
- the live pipeline config accepts session-gapped live data and expects the
  canonical symbol,
- order_send / order_check are NEVER called,
- no credentials appear in the report payload or journal file,
- a sending-enabled gateway is refused,
- the session requires a stop condition (never unbounded),
- the runner script reports an honest ENVIRONMENT_ISSUE off-Windows.
"""

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.broker.mt5_data_adapter import MT5DataAdapter
from src.broker.mt5_settings import load_mt5_settings
from src.data.enums import Direction
from src.execution import (
    ExecutionFlags,
    ExecutionGateway,
    LiveShadowSession,
    make_live_pipeline,
)
from src.journal import TradeJournal
from src.risk import RiskGovernor
from src.strategy import PipelineStage

UTC = timezone.utc
SECRET_PASSWORD = "S3cr3t-PW-do-not-leak"
LOGIN_VALUE = "99887766"
BASE_DT = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
BASE_EPOCH = int(BASE_DT.timestamp())

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER_PATH = REPO_ROOT / "scripts" / "live_shadow_run.py"


def demo_env(**overrides) -> dict:
    env = {
        "TRADING_MODE": "DEMO",
        "MT5_ACCOUNT_TYPE": "DEMO",
        "REAL_TRADING_ENABLED": "false",
        "MT5_LOGIN": LOGIN_VALUE,
        "MT5_PASSWORD": SECRET_PASSWORD,
        "MT5_SERVER": "Exness-MT5Demo",
        "MT5_SYMBOL": "XAUUSDm",  # exact Exness case
    }
    env.update(overrides)
    return env


def make_rate(epoch, o, h, l, c, tick_vol=100, spread=20, real_vol=0) -> dict:
    return {
        "time": epoch, "open": o, "high": h, "low": l, "close": c,
        "tick_volume": tick_vol, "spread": spread, "real_volume": real_vol,
    }


def m5_series(n: int, *, gap_after: int = -1) -> list:
    """n M5 rates ending at BASE_EPOCH; optionally a session gap mid-series."""
    rates = []
    epoch = BASE_EPOCH - (n - 1) * 300 - (3600 if gap_after >= 0 else 0)
    for i in range(n):
        base = 2300.0 + 0.25 * i
        rates.append(make_rate(epoch, base, base + 1.0, base - 1.0, base + 0.5))
        epoch += 300
        if i == gap_after:
            epoch += 3600  # one-hour trading-break gap
    return rates


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeMT5:
    """Read-only MT5 stand-in; trade functions are mocks asserted unused."""

    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388
    TIMEFRAME_D1 = 16408
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2

    def __init__(self, rates=None, trade_mode=0):
        self._rates = rates if rates is not None else m5_series(60)
        self._trade_mode = trade_mode
        self.initialize = MagicMock(return_value=True)
        self.login = MagicMock(return_value=True)
        self.shutdown = MagicMock(return_value=None)
        self.symbol_select = MagicMock(return_value=True)
        self.last_error = MagicMock(return_value=(0, "ok"))
        self.copy_rates_from_pos = MagicMock(
            side_effect=lambda symbol, tf, start, count: list(self._rates)[-count:]
        )
        self.symbol_info_tick = MagicMock(
            side_effect=lambda symbol: _Obj(
                bid=2315.0, ask=2315.18, last=2315.1, time=BASE_EPOCH, volume=10
            )
        )
        self.account_info = MagicMock(
            side_effect=lambda: _Obj(
                trade_mode=self._trade_mode, currency="USD", leverage=500,
                balance=2000.0, equity=2000.0, margin=0.0, margin_free=2000.0,
                margin_level=0.0, trade_allowed=True,
                server="Exness-MT5Demo", login=int(LOGIN_VALUE),
            )
        )
        self.positions_total = MagicMock(return_value=0)
        # Trade functions that must NEVER be called in shadow mode.
        self.order_send = MagicMock()
        self.order_check = MagicMock()

    def assert_no_trades(self):
        self.order_send.assert_not_called()
        self.order_check.assert_not_called()


@pytest.fixture
def fake_mt5() -> FakeMT5:
    return FakeMT5()


@pytest.fixture
def adapter(fake_mt5) -> MT5DataAdapter:
    settings = load_mt5_settings(demo_env())
    a = MT5DataAdapter(settings, client=fake_mt5)
    a.connect()
    return a


def make_session(adapter, journal, **overrides) -> LiveShadowSession:
    kwargs = dict(
        adapter=adapter,
        pipeline=make_live_pipeline("XAUUSDM"),
        journal=journal,
        symbol="XAUUSDm",
        now=lambda: BASE_DT + timedelta(seconds=60),
        monotonic=MagicMock(side_effect=range(0, 10_000, 10)),
        sleep=MagicMock(),
    )
    kwargs.update(overrides)
    return LiveShadowSession(**kwargs)


# ---------------------------------------------------------------------------
# Live data -> pipeline -> journal wiring
# ---------------------------------------------------------------------------

def test_cycles_journal_every_decision(adapter, fake_mt5, tmp_path):
    journal = TradeJournal(tmp_path / "live.jsonl")
    session = make_session(adapter, journal)
    report = session.run(poll_seconds=1.0, max_cycles=3)
    assert report.cycles == 3
    assert report.decisions_logged == 3
    assert len(journal.decisions()) == 3
    fake_mt5.assert_no_trades()


def test_live_pipeline_accepts_session_gapped_data(fake_mt5, tmp_path):
    # Real XAU/USD M5 data spans daily trading breaks; the live validator
    # config must not reject it as MISSING_CANDLES.
    fake_mt5._rates = m5_series(60, gap_after=30)
    settings = load_mt5_settings(demo_env())
    adapter = MT5DataAdapter(settings, client=fake_mt5)
    adapter.connect()
    session = make_session(adapter, TradeJournal(tmp_path / "live.jsonl"))
    result = session.decide_once()
    assert result.stage != PipelineStage.DATA_REJECTED.value


def test_stale_live_data_is_rejected_as_no_trade(adapter, tmp_path):
    journal = TradeJournal(tmp_path / "live.jsonl")
    # Feed is frozen: "now" is 2 hours after the last candle (> max_staleness).
    session = make_session(
        adapter, journal, now=lambda: BASE_DT + timedelta(hours=2)
    )
    result = session.decide_once()
    assert result.stage == PipelineStage.DATA_REJECTED.value
    assert result.direction == Direction.NO_TRADE.value
    # The rejection is still journaled (every decision is logged).
    assert len(journal.decisions()) == 1


def test_exact_broker_symbol_case_in_all_live_calls(adapter, fake_mt5, tmp_path):
    session = make_session(adapter, TradeJournal(tmp_path / "live.jsonl"))
    session.decide_once()
    for call in fake_mt5.copy_rates_from_pos.call_args_list:
        assert call.args[0] == "XAUUSDm"
    for call in fake_mt5.symbol_info_tick.call_args_list:
        assert call.args[0] == "XAUUSDm"
    for call in fake_mt5.symbol_select.call_args_list:
        assert call.args[0] == "XAUUSDm"


def test_cycle_result_reads_live_spread(adapter, tmp_path):
    session = make_session(adapter, TradeJournal(tmp_path / "live.jsonl"))
    result = session.decide_once()
    assert result.spread_price == pytest.approx(0.18)


# ---------------------------------------------------------------------------
# No orders, ever
# ---------------------------------------------------------------------------

def test_no_order_send_across_full_session(adapter, fake_mt5, tmp_path):
    session = make_session(adapter, TradeJournal(tmp_path / "live.jsonl"))
    report = session.run(poll_seconds=1.0, max_cycles=5)
    assert report.orders_sent == 0
    assert all(r.sent is False for r in report.results)
    fake_mt5.assert_no_trades()


def test_refuses_sending_enabled_gateway(adapter, tmp_path):
    sending_flags = ExecutionFlags(
        trading_mode="DEMO", allow_demo_orders=True, allow_mt5_order_send=True,
    )
    gateway = ExecutionGateway(RiskGovernor(), sending_flags, FakeMT5())
    with pytest.raises(ValueError):
        make_session(adapter, TradeJournal(tmp_path / "live.jsonl"), gateway=gateway)


def test_run_requires_stop_condition(adapter, tmp_path):
    session = make_session(adapter, TradeJournal(tmp_path / "live.jsonl"))
    with pytest.raises(ValueError):
        session.run(poll_seconds=1.0)  # no duration and no max_cycles


# ---------------------------------------------------------------------------
# No credentials exposed
# ---------------------------------------------------------------------------

def test_report_and_journal_contain_no_credentials(adapter, tmp_path):
    journal_path = tmp_path / "live.jsonl"
    session = make_session(adapter, TradeJournal(journal_path))
    report = session.run(poll_seconds=1.0, max_cycles=2)
    blob = json.dumps(report.to_dict())
    assert SECRET_PASSWORD not in blob
    assert LOGIN_VALUE not in blob
    journal_text = journal_path.read_text(encoding="utf-8")
    assert SECRET_PASSWORD not in journal_text
    assert LOGIN_VALUE not in journal_text


# ---------------------------------------------------------------------------
# Runner script (off-Windows behaviour + demo verification)
# ---------------------------------------------------------------------------

def _load_runner():
    spec = importlib.util.spec_from_file_location("live_shadow_run", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runner_reports_environment_issue_off_windows():
    runner = _load_runner()
    client, reason = runner.try_import_mt5()
    assert client is None  # this Linux/WSL host cannot import MetaTrader5
    assert "not importable" in reason


def test_runner_refuses_real_account():
    runner = _load_runner()
    with pytest.raises(RuntimeError, match="REAL"):
        runner.verify_demo_account(FakeMT5(trade_mode=2))


def test_runner_accepts_demo_and_contest_accounts():
    runner = _load_runner()
    assert runner.verify_demo_account(FakeMT5(trade_mode=0)) == "DEMO"
    assert runner.verify_demo_account(FakeMT5(trade_mode=1)) == "CONTEST"


def test_runner_markdown_has_no_credentials_and_forbidden_banner():
    runner = _load_runner()
    payload = {
        "task": "LIVE-001", "outcome": "COMPLETED", "symbol": "XAUUSDm",
        "account_mode": "DEMO", "generated_at": "2026-06-09T00:00:00Z",
        "report": {
            "started_at_utc": "x", "ended_at_utc": "y", "cycles": 1,
            "decisions_logged": 1, "actionable_decisions": 0,
            "approved_decisions": 0, "orders_sent": 0, "journal_path": "logs/j.jsonl",
            "results": [],
        },
    }
    md = runner.render_markdown(payload)
    assert "FORBIDDEN" in md
    assert "XAUUSDm" in md
    assert SECRET_PASSWORD not in md
    assert LOGIN_VALUE not in md
