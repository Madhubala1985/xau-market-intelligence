"""Tests for the supervised demo session (DEMO-002).

Proves:
- preflight READY and the exact confirmation token are required to construct,
- a real-requesting gateway is refused,
- the full entry path: pipeline -> planner -> governor -> gateway -> fake MT5
  order_send with a stop-loss attached, journaled with its ticket,
- max_orders is enforced (first run: ONE order),
- kill switch halts the session and prevents entries,
- unknown news state and orphan positions block entries (fail closed),
- no averaging down: an add-on onto a losing position is refused,
- governor stays final authority (journaled daily loss blocks new entries),
- close detection: a vanished position is journaled closed with real P&L and
  reconciliation stays clean (no deadlock),
- stop protection flows ONLY through gateway.modify_stop (TRADE_ACTION_SLTP),
  which never widens and never removes a stop,
- dry-run mode (sending disabled) never calls order_send,
- the session report contains no credentials.

All "orders" here hit an in-memory FakeMT5 — no real or demo terminal is ever
contacted by tests.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.broker.mt5_data_adapter import MT5DataAdapter
from src.broker.mt5_settings import load_mt5_settings
from src.data.enums import DecisionStatus, Direction, TradeOutcome
from src.data.schemas import TradeDecision, TradeRecord
from src.execution import (
    CONFIRMATION_TOKEN,
    DemoTradePlanner,
    ExecutionFlags,
    ExecutionGateway,
    KillSwitch,
    SupervisedDemoSession,
)
from src.execution.preflight import GateStatus, PreflightReport
from src.journal import TradeJournal
from src.risk import NewsRiskGuard, RiskGovernor, RiskLimits
from src.strategy.pipeline import PipelineResult, PipelineStage, PipelineContext
from src.strategy.scoring import ConfidenceResult, ScoreRecommendation
from tests.test_live_shadow import (  # reuse the data fixtures
    BASE_DT,
    SECRET_PASSWORD,
    LOGIN_VALUE,
    demo_env,
    m5_series,
)

UTC = timezone.utc
NOW = BASE_DT + timedelta(seconds=60)


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeMT5Trading:
    """In-memory MT5 stand-in with a position book and deal history."""

    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388
    TIMEFRAME_D1 = 16408
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 2
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_SLTP = 6
    TRADE_RETCODE_DONE = 10009

    def __init__(self, rates=None):
        self._rates = rates if rates is not None else m5_series(60)
        self.positions = {}     # ticket -> position _Obj
        self.deals = {}         # ticket -> list of deal _Objs
        self._next_ticket = 1000
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
                bid=2315.0, ask=2315.18, last=2315.1,
                time=int(BASE_DT.timestamp()), volume=10,
            )
        )
        self.account_info = MagicMock(
            side_effect=lambda: _Obj(
                trade_mode=0, currency="USD", leverage=500,
                balance=2000.0, equity=2000.0, margin=0.0, margin_free=2000.0,
                margin_level=0.0, trade_allowed=True,
                server="Exness-MT5Demo", login=int(LOGIN_VALUE),
            )
        )
        self.order_send = MagicMock(side_effect=self._order_send)
        self.order_check = MagicMock()

    # -- trading simulation -------------------------------------------------
    def _order_send(self, request):
        if request["action"] == self.TRADE_ACTION_SLTP:
            pos = self.positions.get(request["position"])
            if pos is None:
                return _Obj(retcode=0)
            pos.sl = request["sl"]
            return _Obj(retcode=self.TRADE_RETCODE_DONE, order=request["position"])
        # market order: open a position
        ticket = self._next_ticket
        self._next_ticket += 1
        self.positions[ticket] = _Obj(
            ticket=ticket, symbol=request["symbol"],
            type=(self.POSITION_TYPE_BUY if request["type"] == self.ORDER_TYPE_BUY
                  else self.POSITION_TYPE_SELL),
            volume=request["volume"], price_open=request["price"],
            sl=request["sl"], tp=request["tp"],
            price_current=request["price"], profit=0.0,
        )
        return _Obj(retcode=self.TRADE_RETCODE_DONE, order=ticket)

    def close_position(self, ticket, pnl, *, price=2310.0, reason=4,
                       time_utc=None, extra_deals=None):
        """Close a fake position leaving an MT5-shaped OUT deal behind.

        reason follows MT5 DEAL_REASON_* (4=SL, 5=TP). extra_deals lets a
        test inject unrelated deals (e.g. a balance operation) to prove the
        accounting cannot be contaminated (SMC-EXECUTION-001).
        """
        self.positions.pop(ticket, None)
        stamp = int((time_utc or BASE_DT).timestamp())
        self.deals[ticket] = [
            _Obj(profit=pnl, commission=0.0, swap=0.0, type=1, entry=1,
                 position_id=ticket, price=price, time=stamp, reason=reason,
                 symbol="XAUUSDm"),
        ] + list(extra_deals or [])

    def positions_total(self):
        return len(self.positions)

    def positions_get(self, symbol=None):
        return [p for p in self.positions.values()
                if symbol is None or p.symbol == symbol]

    def history_deals_get(self, t_from=None, t_to=None, position=None):
        """MT5-shaped history access: position= variant OR date range."""
        if position is not None:
            return self.deals.get(position)
        out = []
        for deals in self.deals.values():
            for d in deals:
                stamp = getattr(d, "time", None)
                if stamp is not None and t_from is not None and t_to is not None:
                    when = datetime.fromtimestamp(stamp, tz=timezone.utc)
                    if not (t_from <= when <= t_to):
                        continue
                out.append(d)
        return out


def ready_preflight() -> PreflightReport:
    pf = PreflightReport(symbol="XAUUSDm")
    pf.add("all", GateStatus.PASS, "ok")
    return pf


def failed_preflight() -> PreflightReport:
    pf = PreflightReport(symbol="XAUUSDm")
    pf.add("env_demo_orders_enabled", GateStatus.FAIL, "disabled")
    return pf


def sending_flags() -> ExecutionFlags:
    return ExecutionFlags(trading_mode="DEMO", allow_demo_orders=True,
                          allow_mt5_order_send=True)


def approved_result(*, stop=2299.0, entry=2300.0, take=2330.0,
                    direction=Direction.LONG, with_stop=True) -> PipelineResult:
    decision = TradeDecision(
        decision_id=f"D-{int(NOW.timestamp())}", time_utc=NOW, symbol="XAUUSDM",
        direction=direction, status=DecisionStatus.PROPOSED,
        thesis="sweep reclaimed", invalidation_price=stop, entry_price=entry,
        stop_loss=stop if with_stop else None, take_profits=(take,),
        confidence=0.75, uncertainty=0.2,
    )
    confidence = ConfidenceResult(
        confidence=0.75, uncertainty=0.2,
        recommendation=ScoreRecommendation.ALLOW, size_factor=1.0, reason="ok",
    )
    return PipelineResult(
        stage=PipelineStage.RISK_EVALUATED, approved=True, reason="ok",
        decision=decision, confidence=confidence,
        context=PipelineContext(
            session=None, htf_bias=None, regime=None,
            structure_bias=None, has_setup=True,
        ),
        lot_size=0.08,
    )


def no_trade_result() -> PipelineResult:
    return PipelineResult(
        stage=PipelineStage.HYPOTHESIS, approved=False, reason="no setup",
    )


class StubPipeline:
    """Returns queued PipelineResults; defaults to NO_TRADE."""

    def __init__(self, results=None):
        self.results = list(results or [])
        self.inputs = []

    def decide(self, inp):
        self.inputs.append(inp)
        if self.results:
            return self.results.pop(0)
        return no_trade_result()


def clear_news(tmp_path) -> NewsRiskGuard:
    import json
    cal = tmp_path / "news_windows.json"
    cal.write_text(json.dumps({"windows": []}), encoding="utf-8")
    return NewsRiskGuard(block_path=tmp_path / "NEWS_BLOCK", calendar_path=cal)


def make_session(tmp_path, *, results=None, flags=None, max_orders=1,
                 news_guard=None, confirmation=CONFIRMATION_TOKEN,
                 preflight=None, fake=None, journal=None, **overrides):
    fake = fake or FakeMT5Trading()
    adapter = MT5DataAdapter(load_mt5_settings(demo_env()), client=fake)
    adapter.connect()
    kill_switch = KillSwitch(tmp_path / "KILL_SWITCH")
    limits = RiskLimits(expected_symbol="XAUUSDM", max_open_trades=2,
                        max_spread=1.0)
    gateway = ExecutionGateway(
        RiskGovernor(limits), flags or sending_flags(), fake,
        expected_symbol="XAUUSDM", broker_symbol="XAUUSDm",
        kill_switch=kill_switch,
    )
    journal = journal or TradeJournal(tmp_path / "demo_journal.jsonl")
    kwargs = dict(
        adapter=adapter,
        pipeline=StubPipeline(results),
        planner=DemoTradePlanner(limits=limits),
        gateway=gateway,
        journal=journal,
        symbol="XAUUSDm",
        confirmation=confirmation,
        preflight=preflight or ready_preflight(),
        news_guard=news_guard or clear_news(tmp_path),
        kill_switch=kill_switch,
        max_orders=max_orders,
        now=lambda: NOW,
        monotonic=MagicMock(side_effect=range(0, 100000, 10)),
        sleep=MagicMock(),
    )
    kwargs.update(overrides)
    return SupervisedDemoSession(**kwargs), fake, journal, kill_switch


# ---------------------------------------------------------------------------
# Hard preconditions
# ---------------------------------------------------------------------------

def test_refuses_without_ready_preflight(tmp_path):
    with pytest.raises(ValueError, match="preflight"):
        make_session(tmp_path, preflight=failed_preflight())


def test_refuses_wrong_confirmation_token(tmp_path):
    with pytest.raises(ValueError, match="confirmation"):
        make_session(tmp_path, confirmation="yes please")


def test_refuses_real_requesting_gateway(tmp_path):
    real_flags = ExecutionFlags(trading_mode="REAL")
    with pytest.raises(ValueError, match="real"):
        make_session(tmp_path, flags=real_flags)


# ---------------------------------------------------------------------------
# Entry path: order sent, stop attached, ticket journaled
# ---------------------------------------------------------------------------

def test_full_entry_path_sends_one_demo_order_with_stop(tmp_path):
    session, fake, journal, _ = make_session(tmp_path, results=[approved_result()])
    report = session.run(duration_seconds=1.0, poll_seconds=1.0, max_cycles=1)

    assert report.orders_sent == 1
    assert fake.order_send.call_count == 1
    request = fake.order_send.call_args.args[0]
    assert request["sl"] == pytest.approx(2299.0)  # stop-loss attached
    # the request must carry the EXACT broker symbol case, not the canonical
    # form — MT5 symbols are case-sensitive (defect found by CONTINUOUS-001)
    assert request["symbol"] == "XAUUSDm"
    # Journaled with the MT5 ticket for reconciliation.
    records = journal.records()
    assert len(records) == 1
    assert records[0].outcome is TradeOutcome.OPEN
    assert "ticket=1000" in records[0].notes
    assert records[0].lot_size == pytest.approx(0.16)  # $20 cap over $125/lot
    assert report.verdict == "CLEAN"


def test_max_orders_is_enforced(tmp_path):
    session, fake, _, _ = make_session(
        tmp_path, results=[approved_result(), approved_result()], max_orders=1,
    )
    report = session.run(duration_seconds=100.0, poll_seconds=1.0, max_cycles=2)
    assert report.orders_sent == 1
    assert fake.order_send.call_count == 1  # second entry never reaches MT5
    assert report.entries_blocked >= 1


def test_stop_loss_is_mandatory(tmp_path):
    session, fake, _, _ = make_session(
        tmp_path, results=[approved_result(with_stop=False)],
    )
    report = session.run(duration_seconds=1.0, poll_seconds=1.0, max_cycles=1)
    assert report.orders_sent == 0
    fake.order_send.assert_not_called()


# ---------------------------------------------------------------------------
# Fail-closed gates during the session
# ---------------------------------------------------------------------------

def test_kill_switch_halts_session_before_any_entry(tmp_path):
    session, fake, _, ks = make_session(tmp_path, results=[approved_result()])
    ks.engage("operator stop")
    report = session.run(duration_seconds=100.0, poll_seconds=1.0)
    assert report.verdict == "HALTED_BY_KILL_SWITCH"
    assert report.cycles == 0
    fake.order_send.assert_not_called()


def test_unknown_news_blocks_entries(tmp_path):
    no_source = NewsRiskGuard(block_path=tmp_path / "NB",
                              calendar_path=tmp_path / "missing.json")
    session, fake, _, _ = make_session(
        tmp_path, results=[approved_result()], news_guard=no_source,
    )
    report = session.run(duration_seconds=1.0, poll_seconds=1.0, max_cycles=1)
    assert report.orders_sent == 0
    fake.order_send.assert_not_called()
    assert any("NEWS_UNKNOWN" in e.detail for e in report.events
               if e.kind == "PLAN_BLOCKED")


def test_orphan_broker_position_blocks_entries(tmp_path):
    fake = FakeMT5Trading()
    # A manual position the journal knows nothing about.
    fake.positions[9999] = _Obj(
        ticket=9999, symbol="XAUUSDm", type=0, volume=0.05,
        price_open=2290.0, sl=2285.0, tp=2330.0,
        price_current=2315.0, profit=12.5,
    )
    session, fake, _, _ = make_session(
        tmp_path, results=[approved_result()], fake=fake,
    )
    report = session.run(duration_seconds=1.0, poll_seconds=1.0, max_cycles=1)
    assert report.orders_sent == 0
    assert any("ORPHAN_POSITIONS" in e.detail for e in report.events
               if e.kind == "PLAN_BLOCKED")
    assert report.verdict == "ATTENTION_REQUIRED"


def test_no_averaging_down_into_losing_position(tmp_path):
    fake = FakeMT5Trading()
    journal = TradeJournal(tmp_path / "demo_journal.jsonl")
    # Open LONG position now in LOSS, known to the journal (ticket matched).
    fake.positions[500] = _Obj(
        ticket=500, symbol="XAUUSDm", type=0, volume=0.05,
        price_open=2320.0, sl=2315.5, tp=2360.0,
        price_current=2316.0, profit=-20.0,  # below entry: losing
    )
    journal.log_record(TradeRecord(
        record_id="T-500", created_at_utc=NOW, symbol="XAUUSDM",
        direction=Direction.LONG, outcome=TradeOutcome.OPEN,
        opened_at_utc=NOW, entry_price=2320.0, stop_loss=2315.5,
        lot_size=0.05, notes="ticket=500",
    ))
    session, fake, journal, _ = make_session(
        tmp_path, results=[approved_result()], fake=fake, journal=journal,
    )
    report = session.run(duration_seconds=1.0, poll_seconds=1.0, max_cycles=1)
    assert report.orders_sent == 0
    assert fake.order_send.call_count == 0
    assert any("PYRAMIDING_BLOCKED" in e.detail or "RISK_BLOCKED" in e.detail
               for e in report.events if e.kind == "PLAN_BLOCKED")


def test_governor_daily_loss_blocks_new_entries(tmp_path):
    journal = TradeJournal(tmp_path / "demo_journal.jsonl")
    # A -$60 loss closed earlier today = 3% of $2000 (over the 2% demo cap).
    earlier = NOW - timedelta(hours=2)
    journal.log_record(TradeRecord(
        record_id="L-1", created_at_utc=earlier, symbol="XAUUSDM",
        direction=Direction.LONG, outcome=TradeOutcome.LOSS, pnl=-60.0,
        opened_at_utc=earlier, closed_at_utc=earlier,
    ))
    session, fake, _, _ = make_session(
        tmp_path, results=[approved_result()], journal=journal,
    )
    report = session.run(duration_seconds=1.0, poll_seconds=1.0, max_cycles=1)
    assert report.orders_sent == 0
    fake.order_send.assert_not_called()


# ---------------------------------------------------------------------------
# Close detection: no deadlock, real P&L reaches the journal
# ---------------------------------------------------------------------------

def test_close_detection_journals_pnl_and_keeps_reconciliation_clean(tmp_path):
    session, fake, journal, _ = make_session(
        tmp_path, results=[approved_result(), no_trade_result()], max_orders=1,
    )
    # Cycle 1: order opens (ticket 1000). Then the stop is hit at -$9.60.
    report1 = session.run(duration_seconds=1.0, poll_seconds=1.0, max_cycles=1)
    assert report1.orders_sent == 1
    fake.close_position(1000, pnl=-9.60)

    report2 = session.run(duration_seconds=1.0, poll_seconds=1.0, max_cycles=1)
    assert any(e.kind == "CLOSE_DETECTED" for e in report2.events)
    # The latest record for T-* is now a LOSS with the real P&L.
    from src.risk.state_tracker import collapse_records
    latest = collapse_records(journal.records())
    closed = [r for r in latest if r.outcome is TradeOutcome.LOSS]
    assert len(closed) == 1
    assert closed[0].pnl == pytest.approx(-9.60)
    # No orphan deadlock: reconciliation is clean again.
    assert report2.final_reconciliation["clean"] is True
    # And the loss now feeds the risk tracker (daily loss > 0).
    snap = session._risk_state.snapshot(NOW, 2000.0)
    assert snap.daily_loss_pct == pytest.approx(9.60 / 2000.0)


def test_unknown_close_pnl_fails_closed_as_violation(tmp_path):
    journal = TradeJournal(tmp_path / "demo_journal.jsonl")
    journal.log_record(TradeRecord(
        record_id="T-77", created_at_utc=NOW, symbol="XAUUSDM",
        direction=Direction.LONG, outcome=TradeOutcome.OPEN,
        opened_at_utc=NOW, entry_price=2300.0, stop_loss=2295.0,
        lot_size=0.01, notes="ticket=77",
    ))
    session, fake, _, _ = make_session(
        tmp_path, results=[approved_result()], journal=journal,
    )  # no broker position 77 and no deal history
    report = session.run(duration_seconds=1.0, poll_seconds=1.0, max_cycles=1)
    assert report.violations >= 1
    assert report.orders_sent == 0  # orphan keeps entries blocked
    assert report.verdict == "ATTENTION_REQUIRED"


# ---------------------------------------------------------------------------
# Stop protection through the gateway only
# ---------------------------------------------------------------------------

def test_break_even_protection_applied_via_gateway(tmp_path):
    fake = FakeMT5Trading()
    journal = TradeJournal(tmp_path / "demo_journal.jsonl")
    # Open LONG from 2300 with stop 2295, now at 2315 (3R) -> BE earned.
    fake.positions[600] = _Obj(
        ticket=600, symbol="XAUUSDm", type=0, volume=0.05,
        price_open=2300.0, sl=2295.0, tp=2360.0,
        price_current=2315.0, profit=75.0,
    )
    journal.log_record(TradeRecord(
        record_id="T-600", created_at_utc=NOW, symbol="XAUUSDM",
        direction=Direction.LONG, outcome=TradeOutcome.OPEN,
        opened_at_utc=NOW, entry_price=2300.0, stop_loss=2295.0,
        lot_size=0.05, notes="ticket=600",
    ))
    session, fake, journal, _ = make_session(tmp_path, fake=fake, journal=journal)
    report = session.run(duration_seconds=1.0, poll_seconds=1.0, max_cycles=1)

    assert report.stop_updates == 1
    sltp_calls = [c.args[0] for c in fake.order_send.call_args_list
                  if c.args[0]["action"] == FakeMT5Trading.TRADE_ACTION_SLTP]
    assert len(sltp_calls) == 1
    assert sltp_calls[0]["position"] == 600
    assert sltp_calls[0]["sl"] == pytest.approx(2300.0)  # break-even
    assert sltp_calls[0]["symbol"] == "XAUUSDm"  # exact broker case
    assert fake.positions[600].sl == pytest.approx(2300.0)


def test_gateway_modify_stop_never_widens_or_removes(tmp_path):
    fake = FakeMT5Trading()
    gateway = ExecutionGateway(
        RiskGovernor(RiskLimits(expected_symbol="XAUUSDM")), sending_flags(),
        fake, expected_symbol="XAUUSDM",
        kill_switch=KillSwitch(tmp_path / "KS"),
    )
    widen = gateway.modify_stop(
        ticket=1, symbol="XAUUSDm", direction=Direction.LONG,
        current_stop=2300.0, new_stop=2290.0,  # widening
    )
    assert widen.sent is False and "widen" in widen.reason
    remove = gateway.modify_stop(
        ticket=1, symbol="XAUUSDm", direction=Direction.LONG,
        current_stop=2300.0, new_stop=0.0,  # removal
    )
    assert remove.sent is False
    fake.order_send.assert_not_called()


def test_gateway_modify_stop_blocked_by_kill_switch(tmp_path):
    fake = FakeMT5Trading()
    ks = KillSwitch(tmp_path / "KS")
    ks.engage()
    gateway = ExecutionGateway(
        RiskGovernor(RiskLimits(expected_symbol="XAUUSDM")), sending_flags(),
        fake, expected_symbol="XAUUSDM", kill_switch=ks,
    )
    result = gateway.modify_stop(
        ticket=1, symbol="XAUUSDm", direction=Direction.LONG,
        current_stop=2295.0, new_stop=2300.0,
    )
    assert result.sent is False
    fake.order_send.assert_not_called()


# ---------------------------------------------------------------------------
# Dry-run and hygiene
# ---------------------------------------------------------------------------

def test_dry_run_flags_never_call_order_send(tmp_path):
    session, fake, journal, _ = make_session(
        tmp_path, results=[approved_result()], flags=ExecutionFlags(),
        max_orders=0,
    )
    report = session.run(duration_seconds=1.0, poll_seconds=1.0, max_cycles=1)
    assert report.orders_sent == 0
    fake.order_send.assert_not_called()
    assert len(journal.records()) == 0  # no trade record without a fill


def test_report_contains_no_credentials(tmp_path):
    import json as _json
    session, _, _, _ = make_session(tmp_path, results=[approved_result()])
    report = session.run(duration_seconds=1.0, poll_seconds=1.0, max_cycles=1)
    blob = _json.dumps(report.to_dict())
    assert SECRET_PASSWORD not in blob
    assert LOGIN_VALUE not in blob

# ---------------------------------------------------------------------------
# DEMO-EVAL: policy-governed limits, dry-run rehearsal, cycle stats
# ---------------------------------------------------------------------------

from dataclasses import replace as _dc_replace


def approved_result_with_id(i: int) -> PipelineResult:
    base = approved_result()
    decision = base.decision.model_copy(update={"decision_id": f"D-{i}"})
    return _dc_replace(base, decision=decision)


def closing_sleep(fake, pnl=+10.0):
    """Between cycles, close every open fake position with the given P&L."""
    def _sleep(_seconds):
        for ticket in list(fake.positions):
            fake.close_position(ticket, pnl)
    return _sleep


def test_no_artificial_cap_policy_governs_order_count(tmp_path):
    """max_orders=None: order count is bounded by the RISK POLICY (3/day),
    not by a hardcoded one-order session cap."""
    fake = FakeMT5Trading()
    results = [approved_result_with_id(i) for i in range(1, 6)]
    session, fake, journal, _ = make_session(
        tmp_path, results=results, fake=fake, max_orders=None,
        sleep=closing_sleep(fake),
    )
    report = session.run(duration_seconds=1000.0, poll_seconds=1.0, max_cycles=5)

    # Exactly the policy's max_trades_per_day fills, never more.
    assert report.orders_sent == 3
    assert report.max_orders is None
    # The 4th/5th attempts were blocked by the GOVERNOR, not a session cap.
    assert not any("max_orders" in e.detail for e in report.events)
    assert any(
        e.kind == "PLAN_BLOCKED" and "RISK_BLOCKED" in e.detail
        for e in report.events
    )
    # All three closes were detected with real P&L.
    closed = [r for r in journal.records() if r.outcome is TradeOutcome.WIN]
    assert len(closed) == 3


def test_smoke_cap_remains_available_for_smoke_runs(tmp_path):
    session, fake, _, _ = make_session(
        tmp_path, results=[approved_result_with_id(1), approved_result_with_id(2)],
        max_orders=1,
    )
    report = session.run(duration_seconds=100.0, poll_seconds=1.0, max_cycles=2)
    assert report.orders_sent == 1
    assert any(
        e.kind == "ENTRY_BLOCKED" and "max_orders=1" in e.detail
        for e in report.events
    )


def test_dry_run_rehearses_full_entry_path_without_order_send(tmp_path):
    """DRY_RUN must exercise planner -> gateway and count SIMULATED orders;
    nothing reaches order_send and nothing is journaled as an open trade."""
    session, fake, journal, _ = make_session(
        tmp_path, results=[approved_result()], flags=ExecutionFlags(),
        max_orders=None,
    )
    report = session.run(duration_seconds=1.0, poll_seconds=1.0, max_cycles=1)
    assert report.mode == "DRY_RUN"
    assert report.orders_simulated == 1
    assert report.orders_sent == 0
    fake.order_send.assert_not_called()
    assert any(e.kind == "ORDER_SIMULATED" for e in report.events)
    assert journal.records() == []


def test_dry_run_rehearses_the_smoke_cap(tmp_path):
    """Simulated orders count against the session cap, so a dry run shows the
    exact cap behavior the live run will have."""
    session, fake, _, _ = make_session(
        tmp_path,
        results=[approved_result_with_id(1), approved_result_with_id(2)],
        flags=ExecutionFlags(), max_orders=1,
    )
    report = session.run(duration_seconds=100.0, poll_seconds=1.0, max_cycles=2)
    assert report.orders_simulated == 1
    fake.order_send.assert_not_called()
    assert any(
        e.kind == "ENTRY_BLOCKED" and "max_orders=1" in e.detail
        for e in report.events
    )


def test_cycle_stats_capture_evaluation_data(tmp_path):
    session, _, _, _ = make_session(
        tmp_path, results=[approved_result(), no_trade_result()],
        max_orders=None, profile_name="evaluation",
    )
    report = session.run(duration_seconds=100.0, poll_seconds=1.0, max_cycles=2)
    assert report.profile == "evaluation"
    assert report.mode == "DEMO_LIVE"
    assert len(report.cycle_stats) == 2
    first, second = report.cycle_stats
    assert first.direction == "LONG"
    assert first.approved is True
    assert first.confidence == pytest.approx(0.75)
    assert first.entry_action == "SENT"
    assert first.news_known is True
    assert first.spread_price == pytest.approx(0.18)
    assert second.entry_action == "NONE"
    assert second.stage == "HYPOTHESIS"
    payload = report.to_dict()
    assert len(payload["cycle_stats"]) == 2
    assert payload["mode"] == "DEMO_LIVE"
    assert payload["orders_simulated"] == 0

def test_session_fetches_true_mtf_timeframes(tmp_path):
    """INTELLIGENCE-002: the live cycle requests real M15/H1/M1 candles from
    MT5 and hands them to the pipeline (no silent M5-only operation)."""
    session, fake, _, _ = make_session(
        tmp_path, results=[no_trade_result()], max_orders=None,
    )
    session.run(duration_seconds=1.0, poll_seconds=1.0, max_cycles=1)
    pipeline = session._pipeline  # StubPipeline records its inputs
    inp = pipeline.inputs[0]
    assert inp.m15_candles is not None and len(inp.m15_candles) > 0
    assert inp.h1_candles is not None and len(inp.h1_candles) > 0
    assert inp.m1_candles is not None and len(inp.m1_candles) > 0
    requested = {call.args[1] for call in fake.copy_rates_from_pos.call_args_list}
    assert fake.TIMEFRAME_M15 in requested
    assert fake.TIMEFRAME_H1 in requested
    assert fake.TIMEFRAME_M1 in requested


def test_session_degrades_when_extra_timeframes_fail(tmp_path):
    """A failed M15/H1/M1 fetch must degrade to None, never crash the cycle."""
    fake = FakeMT5Trading()
    original = fake.copy_rates_from_pos.side_effect

    def flaky(symbol, tf, start, count):
        if tf in (fake.TIMEFRAME_M15, fake.TIMEFRAME_H1, fake.TIMEFRAME_M1):
            raise RuntimeError("timeframe unavailable")
        return original(symbol, tf, start, count)

    fake.copy_rates_from_pos.side_effect = flaky
    session, fake, _, _ = make_session(
        tmp_path, results=[no_trade_result()], fake=fake, max_orders=None,
    )
    report = session.run(duration_seconds=1.0, poll_seconds=1.0, max_cycles=1)
    assert report.cycles == 1  # no crash
    inp = session._pipeline.inputs[0]
    assert inp.m15_candles is None
    assert inp.h1_candles is None
    assert inp.m1_candles is None

def test_defensive_budget_with_wide_stop_sends_promoted_min_lot(tmp_path):
    """SIZING-001 end-to-end regression: a DEFENSIVE adaptive budget smaller
    than the min-lot loss must still produce a 0.01-lot MT5 order when the
    phase ceiling allows it — not 'invalid lot size 0.0'."""
    from src.risk.adaptive_risk import (
        AdaptiveRiskDecision,
        CapitalPhase,
        RiskTier,
    )
    from src.risk.lot_sizer import resolve_lot

    base = approved_result(stop=2294.0, entry=2300.0)  # ~6.2 stop distance
    lot_decision = resolve_lot(equity=2000.0, risk_pct=0.002,
                               ceiling_pct=0.010, stop_distance=6.18)
    assert lot_decision.verdict == "MIN_LOT_PROMOTED_TO_0.01"
    from dataclasses import replace as dc_replace
    result = dc_replace(
        base,
        adaptive_risk=AdaptiveRiskDecision(
            risk_pct=0.002, tier=RiskTier.DEFENSIVE,
            phase=CapitalPhase.PHASE_1, reasons=("defensive",),
            ceiling_pct=0.010,
        ),
        lot_decision=lot_decision,
    )
    session, fake, journal, _ = make_session(
        tmp_path, results=[result], max_orders=None,
    )
    report = session.run(duration_seconds=1.0, poll_seconds=1.0, max_cycles=1)
    assert report.orders_sent == 1
    request = fake.order_send.call_args.args[0]
    assert request["volume"] == pytest.approx(0.01)   # promoted minimum lot
    assert request["symbol"] == "XAUUSDm"             # exact broker case
    assert request["sl"] == pytest.approx(2294.0)
    # sizing diagnostics reach the cycle stats / journal trail
    stat = report.cycle_stats[0]
    assert stat.intel["sizing"]["verdict"] == "MIN_LOT_PROMOTED_TO_0.01"

def test_warmstart_is_read_only(tmp_path):
    """OPERATIONAL-001: build_warmstart analyses full history but journals
    nothing, sends nothing, and mutates no positions."""
    session, fake, journal, _ = make_session(
        tmp_path, results=[approved_result()], max_orders=None,
    )
    data = session.build_warmstart()
    assert data["candles"]["m5"] > 0
    assert set(data["candles"]) == {"d1", "h4", "h1", "m15", "m5", "m1"}
    fake.order_send.assert_not_called()
    assert len(journal.entries()) == 0          # nothing journaled
    assert fake.positions == {}                 # nothing opened/mutated
