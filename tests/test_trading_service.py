"""Tests for the continuous MT5 trading service (CONTINUOUS-001).

Proves:
- a startup banner prints immediately (service never sits blank) with the
  required credential-free fields,
- per-cycle live progress prints (cycle number, decision, reason, totals),
- NO fixed duration: cycles continue far past the old 8-hour session ceiling,
- NO artificial order cap: order count is bounded by the risk policy
  (3 trades/day) — the 4th approved entry is blocked by the GOVERNOR,
- a closed market (schedule) or a stale feed waits + heartbeats instead of
  crashing, and the service resumes when the market opens,
- a restart picks up journal state: matched positions reconcile cleanly and a
  position that closed while the service was down is journaled with real P&L,
- the kill switch, weekly-loss risk shutdown, and Ctrl+C all stop cleanly
  (service report written); the DAILY loss limit pauses entries without
  stopping the service,
- the daily rollover writes evaluation + reflection reports per UTC day,
- dry-run runs the identical loop and can never reach order_send,
- nothing printed/reported/heartbeated contains credentials.

All cycles run against the in-memory FakeMT5Trading; no terminal is contacted.
"""

import json
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest.mock import MagicMock

from src.data.enums import Direction, TradeOutcome
from src.data.schemas import TradeRecord
from src.execution import (
    BannerInfo,
    ExecutionFlags,
    MarketSchedule,
    ProgressPrinter,
    StopReason,
    TradingService,
    get_profile,
    mask_login,
)
from src.journal import TradeJournal
from tests.test_demo_session import (
    FakeMT5Trading,
    NOW,
    _Obj,
    approved_result,
    approved_result_with_id,
    closing_sleep,
    make_session,
    no_trade_result,
)
from tests.test_live_shadow import LOGIN_VALUE, SECRET_PASSWORD

UTC = timezone.utc
# NOW is Tuesday 2026-06-09 12:01 UTC — inside normal trading hours.
SATURDAY = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)


def seq_now(times):
    """A now() that walks through `times` and then repeats the last one."""
    it = iter(list(times))
    state = {"last": list(times)[-1]}

    def _now():
        try:
            state["last"] = next(it)
        except StopIteration:
            pass
        return state["last"]

    return _now


def banner_info(mode="EXECUTION — orders WILL be sent to the .env account (DEMO)"):
    return BannerInfo(
        profile="continuous",
        execution_mode=mode,
        account_login_masked=mask_login(LOGIN_VALUE),
        account_type="DEMO",
        server="Exness-MT5Trial",
        symbol="XAUUSDm",
        risk_summary="0.50%/trade, daily 2.0%, weekly 5.0%, 3 trades/day",
        news_status="clear (calendar)",
        kill_switch_status="absent",
        journal_path="logs/demo_trade_journal.jsonl",
        report_dir="reports/runtime",
    )


def make_service(tmp_path, *, results=None, flags=None, fake=None, journal=None,
                 max_cycles=1, now=None, schedule=None, tick_age=None,
                 service_sleep=None, banner=None, profile=None):
    session, fake, journal, kill_switch = make_session(
        tmp_path, results=results, flags=flags, fake=fake, journal=journal,
        max_orders=None, profile_name="continuous",
    )
    stream = StringIO()
    service = TradingService(
        session=session,
        journal=journal,
        kill_switch=kill_switch,
        profile=profile or get_profile("continuous"),
        printer=ProgressPrinter(stream=stream),
        banner=banner or banner_info(),
        report_dir=tmp_path / "reports",
        heartbeat_path=tmp_path / "heartbeat.jsonl",
        schedule=schedule or MarketSchedule(),
        tick_age=tick_age,
        max_cycles=max_cycles,
        now=now or (lambda: NOW),
        sleep=service_sleep or MagicMock(),
    )
    return service, session, fake, journal, kill_switch, stream


# ---------------------------------------------------------------------------
# Terminal observability
# ---------------------------------------------------------------------------

def test_startup_banner_prints_required_fields(tmp_path):
    service, *_, stream = make_service(tmp_path, max_cycles=1)
    service.run()
    out = stream.getvalue()
    assert "Continuous MT5 Service" in out
    assert "profile:      continuous" in out
    assert "EXECUTION — orders WILL be sent" in out
    assert "type=DEMO" in out
    assert "Exness-MT5Trial" in out
    assert "XAUUSDm" in out
    assert "risk limits:" in out and "0.50%/trade" in out
    assert "news:" in out
    assert "kill switch:  absent" in out
    assert "journal:      logs/demo_trade_journal.jsonl" in out
    assert "KILL_SWITCH" in out  # how to stop safely
    assert "Service is ALIVE" in out


def test_per_cycle_progress_prints(tmp_path):
    service, *_, stream = make_service(
        tmp_path, results=[no_trade_result(), no_trade_result()], max_cycles=2,
    )
    service.run()
    out = stream.getvalue()
    assert "[cycle 1]" in out and "[cycle 2]" in out
    assert "market=OPEN" in out
    assert "bid=2315.00 ask=2315.18" in out
    assert "decision=NO_TRADE reason: no setup" in out  # exact no-trade reason
    assert "trades_today=" in out and "daily_pnl=" in out
    assert "news=" in out and "kill=off" in out and "next_poll=" in out


def test_trade_progress_prints_plan_ticket_and_toolbox_hint(tmp_path):
    fake = FakeMT5Trading()
    service, *_, stream = make_service(
        tmp_path, results=[approved_result(), no_trade_result()], fake=fake,
        max_cycles=2,
    )
    service.run()
    out = stream.getvalue()
    assert "decision=TRADE" in out
    assert "entry: SENT" in out and "lot=0.08" in out and "sl=2299.0" in out
    assert ">> ORDER SENT ticket=1000" in out
    assert "MT5 Toolbox/Trade tab" in out
    # positions are read at cycle start, so the new position is visible (and
    # managed) from the NEXT cycle on
    assert "pos 1000 LONG 0.08" in out


# ---------------------------------------------------------------------------
# No artificial limits
# ---------------------------------------------------------------------------

def test_no_fixed_duration_runs_past_eight_hours(tmp_path):
    # now() advances 6 hours per cycle: 5 cycles span 30 hours.
    times = [NOW + timedelta(hours=6 * i) for i in range(6)]
    service, *_ , stream = make_service(
        tmp_path, results=[no_trade_result()] * 5, max_cycles=5,
        now=seq_now(times),
        # keep every timestamp inside open hours by replacing weekend hits
    )
    # avoid weekend/daily-break interference: use a schedule that is always open
    class AlwaysOpen:
        def state(self, now):
            return "OPEN"
        def next_open(self, now):
            return now
    service._schedule = AlwaysOpen()
    report = service.run()
    assert report.cycles == 5
    assert report.stop_reason == StopReason.MAX_CYCLES


def test_no_artificial_order_cap_policy_governs(tmp_path):
    fake = FakeMT5Trading()
    results = [approved_result_with_id(i) for i in range(1, 6)]
    service, session, fake, journal, _, stream = make_service(
        tmp_path, results=results, fake=fake, max_cycles=5,
        service_sleep=closing_sleep(fake),
    )
    report = service.run()
    assert report.orders_sent == 3  # exactly the policy's 3 trades/day
    out = stream.getvalue()
    assert "max_orders" not in out  # never an artificial session cap
    assert "RISK_BLOCKED" in out    # the governor did the blocking


# ---------------------------------------------------------------------------
# Market closed / stale feed
# ---------------------------------------------------------------------------

def test_market_closed_waits_heartbeats_and_resumes(tmp_path):
    # first element is consumed by the service start timestamp
    times = [SATURDAY, SATURDAY, SATURDAY + timedelta(seconds=60), NOW]
    service, *_ , stream = make_service(
        tmp_path, results=[no_trade_result()], max_cycles=1, now=seq_now(times),
    )
    report = service.run()
    out = stream.getvalue()
    assert "MARKET CLOSED (CLOSED_WEEKEND)" in out
    assert "next scheduled open" in out
    assert report.market_closed_checks == 2
    assert report.cycles == 1  # resumed and ran the cycle once open
    heartbeat = (tmp_path / "heartbeat.jsonl").read_text(encoding="utf-8")
    assert "CLOSED_WEEKEND" in heartbeat
    assert report.stop_reason == StopReason.MAX_CYCLES  # no crash


def test_stale_feed_waits_instead_of_trading(tmp_path):
    ages = [9999.0, 30.0]
    service, *_ , stream = make_service(
        tmp_path, results=[no_trade_result()], max_cycles=1,
        tick_age=lambda now: ages.pop(0),
    )
    report = service.run()
    out = stream.getvalue()
    assert "FEED STALE" in out
    assert report.market_closed_checks == 1
    assert report.cycles == 1


# ---------------------------------------------------------------------------
# Restart / state continuity
# ---------------------------------------------------------------------------

def test_restart_reconciles_open_position_from_journal(tmp_path):
    fake = FakeMT5Trading()
    fake.positions[500] = _Obj(
        ticket=500, symbol="XAUUSDm", type=0, volume=0.05,
        price_open=2300.0, sl=2295.0, tp=2330.0,
        price_current=2315.0, profit=75.0,
    )
    journal = TradeJournal(tmp_path / "journal.jsonl")
    journal.log_record(TradeRecord(
        record_id="T-500", created_at_utc=NOW - timedelta(hours=3),
        symbol="XAUUSDM", direction=Direction.LONG, outcome=TradeOutcome.OPEN,
        opened_at_utc=NOW - timedelta(hours=3), entry_price=2300.0,
        stop_loss=2295.0, lot_size=0.05, notes="ticket=500",
    ))
    # A NEW service instance (restart) over the same journal + broker state.
    service, *_ , stream = make_service(
        tmp_path, results=[no_trade_result()], fake=fake, journal=journal,
        max_cycles=1,
    )
    report = service.run()
    out = stream.getvalue()
    assert "NOT CLEAN" not in out          # the position matched its record
    assert "pos 500 LONG 0.05" in out      # and is visibly managed
    assert report.violations == 0


def test_restart_detects_close_that_happened_while_down(tmp_path):
    fake = FakeMT5Trading()           # position 500 no longer exists...
    fake.deals[500] = [_Obj(profit=15.0, commission=0.0, swap=0.0)]
    journal = TradeJournal(tmp_path / "journal.jsonl")
    journal.log_record(TradeRecord(
        record_id="T-500", created_at_utc=NOW - timedelta(hours=3),
        symbol="XAUUSDM", direction=Direction.LONG, outcome=TradeOutcome.OPEN,
        opened_at_utc=NOW - timedelta(hours=3), entry_price=2300.0,
        stop_loss=2295.0, lot_size=0.05, notes="ticket=500",
    ))
    service, *_ , stream = make_service(
        tmp_path, results=[no_trade_result()], fake=fake, journal=journal,
        max_cycles=1,
    )
    service.run()
    out = stream.getvalue()
    assert "CLOSE_DETECTED" in out and "pnl=15.0" in out
    latest = {r.record_id: r for r in journal.records()}
    assert latest["T-500"].outcome is TradeOutcome.WIN
    assert latest["T-500"].pnl == 15.0


# ---------------------------------------------------------------------------
# Clean stops
# ---------------------------------------------------------------------------

def test_kill_switch_stops_cleanly(tmp_path):
    service, _, _, _, kill_switch, stream = make_service(
        tmp_path, results=[no_trade_result()] * 10, max_cycles=10,
        service_sleep=lambda _s: kill_switch_holder["ks"].engage("stop"),
    )
    kill_switch_holder = {"ks": kill_switch}
    report = service.run()
    assert report.stop_reason == StopReason.KILL_SWITCH
    assert report.cycles == 1
    assert "SERVICE STOPPED: KILL_SWITCH" in stream.getvalue()
    payload = json.loads(
        (tmp_path / "reports" / "trading_service.json").read_text()
    )
    assert payload["stop_reason"] == "KILL_SWITCH"


def test_weekly_loss_risk_shutdown_stops_cleanly(tmp_path):
    journal = TradeJournal(tmp_path / "journal.jsonl")
    earlier = NOW - timedelta(hours=2)
    journal.log_record(TradeRecord(
        record_id="L-1", created_at_utc=earlier, symbol="XAUUSDM",
        direction=Direction.LONG, outcome=TradeOutcome.LOSS, pnl=-120.0,
        opened_at_utc=earlier, closed_at_utc=earlier,
    ))  # -120 on a 2000 balance = 6% weekly loss (limit 5%)
    service, *_ , stream = make_service(
        tmp_path, results=[no_trade_result()] * 5, journal=journal,
        max_cycles=5,
    )
    report = service.run()
    assert report.stop_reason == StopReason.RISK_SHUTDOWN
    assert report.cycles == 1
    assert "weekly loss" in report.detail
    assert "SERVICE STOPPED: RISK_SHUTDOWN" in stream.getvalue()


def test_daily_loss_pauses_but_service_keeps_running(tmp_path):
    journal = TradeJournal(tmp_path / "journal.jsonl")
    earlier = NOW - timedelta(hours=2)
    journal.log_record(TradeRecord(
        record_id="L-1", created_at_utc=earlier, symbol="XAUUSDM",
        direction=Direction.LONG, outcome=TradeOutcome.LOSS, pnl=-50.0,
        opened_at_utc=earlier, closed_at_utc=earlier,
    ))  # -50 = 2.5% daily (limit 2%) but only 2.5% weekly (limit 5%)
    service, *_ , stream = make_service(
        tmp_path, results=[no_trade_result()] * 2, journal=journal,
        max_cycles=2,
    )
    report = service.run()
    assert report.stop_reason == StopReason.MAX_CYCLES  # did NOT stop
    assert report.cycles == 2
    out = stream.getvalue()
    assert "DAY_PAUSED" in out


def test_ctrl_c_stops_cleanly(tmp_path):
    def interrupt(_seconds):
        raise KeyboardInterrupt

    service, *_ , stream = make_service(
        tmp_path, results=[no_trade_result()] * 5, max_cycles=5,
        service_sleep=interrupt,
    )
    report = service.run()
    assert report.stop_reason == StopReason.OPERATOR_INTERRUPT
    assert "stopped cleanly" in report.detail
    assert (tmp_path / "reports" / "trading_service.md").exists()


def test_fatal_error_is_reported_not_swallowed(tmp_path):
    service, session, *_ , stream = make_service(
        tmp_path, results=[no_trade_result()], max_cycles=3,
    )
    session._pipeline.decide = MagicMock(side_effect=RuntimeError("boom"))
    report = service.run()
    assert report.stop_reason == StopReason.FATAL_ERROR
    assert "RuntimeError" in report.detail
    assert "SERVICE STOPPED: FATAL_ERROR" in stream.getvalue()


# ---------------------------------------------------------------------------
# Daily rollover reports
# ---------------------------------------------------------------------------

def test_daily_rollover_writes_evaluation_and_reflection(tmp_path):
    day2 = NOW + timedelta(days=1)

    class AlwaysOpen:
        def state(self, now):
            return "OPEN"
        def next_open(self, now):
            return now

    service, *_ = make_service(
        tmp_path, results=[no_trade_result()] * 2, max_cycles=2,
        now=seq_now([NOW, NOW, day2]),  # start, cycle 1 (day 1), cycle 2 (day 2)
    )
    service._schedule = AlwaysOpen()
    service.run()
    reports = tmp_path / "reports"
    assert (reports / "service_eval_20260609.md").exists()
    assert (reports / "service_eval_20260609.json").exists()
    assert (reports / "service_reflection_20260609.md").exists()
    assert (reports / "service_eval_20260610.json").exists()  # final flush
    payload = json.loads((reports / "service_eval_20260609.json").read_text())
    assert payload["cycles"] == 1


# ---------------------------------------------------------------------------
# Dry-run and credential hygiene
# ---------------------------------------------------------------------------

def test_dry_run_runs_identical_loop_but_cannot_send(tmp_path):
    service, _, fake, _, _, stream = make_service(
        tmp_path, results=[approved_result()], flags=ExecutionFlags(),
        max_cycles=1, banner=banner_info(mode="DRY_RUN — sending disabled"),
    )
    report = service.run()
    out = stream.getvalue()
    assert report.orders_simulated == 1
    assert report.orders_sent == 0
    fake.order_send.assert_not_called()
    assert "decision=TRADE_SIMULATED" in out
    assert "DRY_RUN" in out


def test_no_credentials_in_terminal_reports_or_heartbeat(tmp_path):
    times = [SATURDAY, SATURDAY, NOW]  # start, one heartbeat, one cycle
    service, *_ , stream = make_service(
        tmp_path, results=[approved_result()], max_cycles=1,
        now=seq_now(times),
    )
    service.run()
    out = stream.getvalue()
    files = [stream.getvalue()]
    for path in (tmp_path / "reports").glob("*"):
        files.append(path.read_text(encoding="utf-8"))
    files.append((tmp_path / "heartbeat.jsonl").read_text(encoding="utf-8"))
    for blob in files:
        assert SECRET_PASSWORD not in blob
        assert LOGIN_VALUE not in blob
    # the banner shows only a masked login
    assert mask_login(LOGIN_VALUE) in out
    assert mask_login("12345678") == "******78"
