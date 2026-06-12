"""Tests for MT5-truth accounting (SMC-EXECUTION-001).

Live evidence being guarded against: MT5 closed trades NEGATIVE while the
terminal printed CLOSE_DETECTED outcome=WIN pnl=1158.62 and a fake positive
daily_pnl. Root cause: history_deals_get(date_from, date_to, position=...)
— the date-range and position= variants of the MT5 Python API are mutually
exclusive, so the position filter was dropped and EVERY account deal in the
window (other trades, balance operations) was summed as the trade's P&L.

Proven here:
- a negative MT5 deal is recorded as LOSS (and positive as WIN) — a fake
  WIN with negative net P&L is structurally impossible,
- balance operations and other positions' deals can never contaminate a
  trade's P&L or the daily realized P&L,
- daily realized P&L comes from MT5 deals of TODAY only (no double count),
- unverifiable accounting blocks new entries
  (ACCOUNTING_UNVERIFIED_BLOCK_NEW_ENTRIES) while positions stay managed,
- two consecutive MT5 losses pause new entries (LOSS_COOLDOWN),
- the terminal prints mt5_balance / mt5_equity / mt5_free_margin /
  realized_daily_pnl / floating_pnl / consecutive_losses /
  accounting_verified and the compound-growth milestone line.
"""

from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest.mock import MagicMock

import pytest

from src.broker.mt5_data_adapter import MT5DataAdapter
from src.broker.mt5_settings import load_mt5_settings
from src.data.enums import Direction, TradeOutcome
from src.data.schemas import TradeDecision, TradeRecord
from src.execution.challenge_planner import ChallengeTradePlanner
from src.execution.demo_session import (
    CONFIRMATION_TOKEN,
    CycleStat,
    SupervisedDemoSession,
)
from src.execution.gateway import ExecutionGateway
from src.execution.kill_switch import KillSwitch
from src.execution.trading_service import ProgressPrinter
from src.journal.journal import TradeJournal
from src.risk.governor import RiskGovernor
from src.strategy.pipeline import PipelineContext, PipelineResult, PipelineStage
from src.strategy.scoring import ConfidenceResult, ScoreRecommendation
from src.strategy.smc_execution import make_challenge_limits
from tests.test_broker_execution import _cycle_outcome
from tests.test_demo_challenge import BROKER_SYMBOL, SYMBOL
from tests.test_demo_session import (
    NOW,
    FakeMT5Trading,
    StubPipeline,
    _Obj,
    clear_news,
    ready_preflight,
    sending_flags,
)
from tests.test_live_shadow import demo_env

UTC = timezone.utc


def approved_smc(decision_id, *, lot=0.05):
    entry, stop = 2315.0, 2317.5
    decision = TradeDecision(
        decision_id=decision_id, time_utc=NOW, symbol=SYMBOL,
        direction=Direction.SHORT,
        setup_type=f"smc_bos[NORMAL,lot={lot:.2f}]",
        thesis="smc short", invalidation_price=stop,
        entry_price=entry, stop_loss=stop, take_profits=(2310.0,),
        confidence=0.65, uncertainty=0.3,
    )
    return PipelineResult(
        stage=PipelineStage.RISK_EVALUATED, approved=True, reason="ok",
        decision=decision,
        confidence=ConfidenceResult(
            confidence=0.65, uncertainty=0.3,
            recommendation=ScoreRecommendation.ALLOW, size_factor=1.0,
            reason="x",
        ),
        context=PipelineContext(
            session=None, htf_bias=None, regime=None, structure_bias=None,
            has_setup=True, challenge={"mode": "smc"},
        ),
        lot_size=lot,
    )


def no_trade():
    return PipelineResult(stage=PipelineStage.HYPOTHESIS, approved=False,
                          reason="no setup")


def build_session(tmp_path, fake, results):
    adapter = MT5DataAdapter(load_mt5_settings(demo_env()), client=fake)
    adapter.connect()
    kill_switch = KillSwitch(tmp_path / "KILL_SWITCH")
    limits = make_challenge_limits(SYMBOL)
    journal = TradeJournal(tmp_path / "smc_journal.jsonl")
    session = SupervisedDemoSession(
        adapter=adapter,
        pipeline=StubPipeline(list(results)),
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
        profile_name="smc_challenge",
        hard_max_trades=10, hard_max_open=3,
        max_daily_loss=0.05, max_weekly_loss=0.10,
        risk_pct=0.03,
        now=lambda: NOW,
        monotonic=MagicMock(side_effect=range(0, 100000, 10)),
        sleep=MagicMock(),
    )
    return session, journal, fake


# -- close detection: MT5 history is the only truth ----------------------------------

def test_negative_mt5_deal_is_recorded_as_loss(tmp_path):
    session, journal, fake = build_session(
        tmp_path, FakeMT5Trading(), [approved_smc("smc-1"), no_trade()],
    )
    first = session.run_cycle()
    assert first.stat.entry_action == "SENT"
    ticket = first.sent_ticket
    fake.close_position(ticket, -25.19, price=2317.5, reason=4)  # SL hit

    second = session.run_cycle()
    record = [r for r in journal.records()
              if r.outcome is not TradeOutcome.OPEN][-1]
    assert record.outcome is TradeOutcome.LOSS
    assert record.pnl == pytest.approx(-25.19)
    assert record.exit_price == pytest.approx(2317.5)
    close_events = [e for e in second.events if e.kind == "CLOSE_DETECTED"]
    assert close_events, "close must be detected from MT5 history"
    detail = close_events[0].detail
    assert "outcome=LOSS" in detail
    assert "net_pnl=-25.19" in detail
    assert "source=MT5_HISTORY" in detail
    assert "reason=SL" in detail


def test_positive_mt5_deal_is_recorded_as_win(tmp_path):
    session, journal, fake = build_session(
        tmp_path, FakeMT5Trading(), [approved_smc("smc-1"), no_trade()],
    )
    first = session.run_cycle()
    fake.close_position(first.sent_ticket, 31.40, price=2310.0, reason=5)
    second = session.run_cycle()
    record = [r for r in journal.records()
              if r.outcome is not TradeOutcome.OPEN][-1]
    assert record.outcome is TradeOutcome.WIN
    assert record.pnl == pytest.approx(31.40)
    assert any("reason=TP" in e.detail for e in second.events
               if e.kind == "CLOSE_DETECTED")


def test_fake_win_is_impossible_when_mt5_net_is_negative(tmp_path):
    """The live defect, encoded: unrelated deals (a +1158.62 balance
    operation and another position's profit) sit in history next to the
    losing close — the trade must still be a LOSS of exactly its own net."""
    session, journal, fake = build_session(
        tmp_path, FakeMT5Trading(), [approved_smc("smc-1"), no_trade()],
    )
    first = session.run_cycle()
    ticket = first.sent_ticket
    fake.close_position(
        ticket, -25.19, price=2317.5, reason=4,
        extra_deals=[
            # balance/deposit operation (deal type 2) on the same position id
            _Obj(profit=1158.62, commission=0.0, swap=0.0, type=2, entry=1,
                 position_id=ticket, price=0.0, time=int(NOW.timestamp()),
                 reason=0, symbol="XAUUSDm"),
            # another position's winning deal
            _Obj(profit=500.0, commission=0.0, swap=0.0, type=1, entry=1,
                 position_id=999999, price=2300.0, time=int(NOW.timestamp()),
                 reason=5, symbol="XAUUSDm"),
        ],
    )
    second = session.run_cycle()
    record = [r for r in journal.records()
              if r.outcome is not TradeOutcome.OPEN][-1]
    assert record.outcome is TradeOutcome.LOSS      # never WIN
    assert record.pnl == pytest.approx(-25.19)      # never 1158.62
    detail = next(e.detail for e in second.events
                  if e.kind == "CLOSE_DETECTED")
    assert "outcome=LOSS" in detail and "net_pnl=-25.19" in detail


# -- daily realized P&L: MT5 deals of today only --------------------------------------

def _connected_adapter(fake):
    adapter = MT5DataAdapter(load_mt5_settings(demo_env()), client=fake)
    adapter.connect()
    return adapter


def test_daily_pnl_comes_from_todays_mt5_trade_deals_only():
    fake = FakeMT5Trading()
    yesterday = NOW - timedelta(days=1)
    fake.deals[1] = [  # yesterday's loss: excluded from today
        _Obj(profit=-50.0, commission=0.0, swap=0.0, type=1, entry=1,
             position_id=1, price=2300.0, time=int(yesterday.timestamp()),
             reason=4, symbol="XAUUSDm"),
    ]
    fake.deals[2] = [  # today's trade: IN deal commission + OUT deal profit
        _Obj(profit=999.0, commission=-0.5, swap=0.0, type=1, entry=0,
             position_id=2, price=2315.0, time=int(NOW.timestamp()),
             reason=0, symbol="XAUUSDm"),
        _Obj(profit=10.0, commission=-0.5, swap=-0.1, type=1, entry=1,
             position_id=2, price=2310.0, time=int(NOW.timestamp()),
             reason=5, symbol="XAUUSDm"),
    ]
    fake.deals[3] = [  # a deposit today: NEVER profit
        _Obj(profit=2000.0, commission=0.0, swap=0.0, type=2, entry=0,
             position_id=0, price=0.0, time=int(NOW.timestamp()),
             reason=0, symbol=""),
    ]
    adapter = _connected_adapter(fake)
    day_start = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    realized = adapter.fetch_realized_pnl_since(day_start, now=NOW)
    # OUT profit 10.0 + swap -0.1 + commissions -0.5 -0.5; the IN deal's
    # phantom profit 999, yesterday's -50, and the 2000 deposit all excluded.
    assert realized == pytest.approx(8.9)


def test_closed_position_uses_the_position_keyword_variant():
    fake = FakeMT5Trading()
    fake.close_position(777, -12.34, price=2318.0, reason=4)
    adapter = _connected_adapter(fake)
    closed = adapter.fetch_closed_position(777)
    assert closed is not None
    assert closed.net_pnl == pytest.approx(-12.34)
    assert closed.close_reason == "SL"
    assert closed.close_price == pytest.approx(2318.0)
    # unknown ticket -> None (unknown, never zero)
    assert adapter.fetch_closed_position(123456) is None


# -- accounting verification gates -----------------------------------------------------

class _NoHistoryFake(FakeMT5Trading):
    def history_deals_get(self, *args, **kwargs):  # noqa: D401
        raise RuntimeError("history unavailable")


def test_accounting_unverified_blocks_new_entries(tmp_path):
    session, journal, _ = build_session(
        tmp_path, _NoHistoryFake(), [approved_smc("smc-1")],
    )
    outcome = session.run_cycle()
    assert outcome.stat.entry_action == "ENTRY_BLOCKED"
    assert "ACCOUNTING_UNVERIFIED_BLOCK_NEW_ENTRIES" in outcome.stat.entry_detail
    acct = outcome.stat.intel["accounting"]
    assert acct["verified"] is False
    assert journal.records() == []  # nothing was opened


def test_verified_accounting_is_reported_per_cycle(tmp_path):
    session, _, _ = build_session(
        tmp_path, FakeMT5Trading(), [no_trade()],
    )
    outcome = session.run_cycle()
    acct = outcome.stat.intel["accounting"]
    assert acct["verified"] is True
    assert acct["mt5_balance"] == pytest.approx(2000.0)
    assert acct["mt5_equity"] == pytest.approx(2000.0)
    assert acct["realized_daily_pnl"] == pytest.approx(0.0)
    assert acct["floating_pnl"] == pytest.approx(0.0)
    assert acct["capital_phase"] == "PHASE_1"
    assert acct["next_milestone"] == 10000


def test_two_mt5_losses_trigger_the_cooldown(tmp_path):
    session, journal, fake = build_session(
        tmp_path, FakeMT5Trading(),
        [approved_smc("smc-1"), approved_smc("smc-2", lot=0.05),
         approved_smc("smc-3")],
    )
    first = session.run_cycle()
    assert first.stat.entry_action == "SENT"
    fake.close_position(first.sent_ticket, -10.0, time_utc=NOW)

    second = session.run_cycle()  # one loss: still allowed to trade
    assert second.stat.entry_action == "SENT"
    fake.close_position(second.sent_ticket, -12.0, time_utc=NOW)

    third = session.run_cycle()  # two consecutive MT5 losses: cooldown
    assert third.stat.entry_action == "ENTRY_BLOCKED"
    assert "LOSS_COOLDOWN" in third.stat.entry_detail
    losses = [r for r in journal.records() if r.outcome is TradeOutcome.LOSS]
    assert len(losses) == 2


# -- terminal accounting lines ---------------------------------------------------------

def _stat_with_accounting(verified=True):
    return CycleStat(
        time_utc=NOW, stage="HYPOTHESIS", direction="NO_TRADE",
        approved=False, reason="no setup", spread_price=0.2,
        intel={"accounting": {
            "mt5_balance": 2000.0, "mt5_equity": 1987.5,
            "mt5_free_margin": 1900.0, "realized_daily_pnl": -12.5,
            "floating_pnl": -3.2, "consecutive_losses": 1,
            "verified": verified, "capital_phase": "PHASE_1",
            "next_milestone": 10000,
        }},
    )


def test_terminal_prints_mt5_accounting_and_milestone_lines():
    stream = StringIO()
    ProgressPrinter(stream=stream).cycle(
        1, _cycle_outcome(_stat_with_accounting()),
        decision_label="NO_TRADE", market_state="OPEN", daily_pnl=-12.5,
        risk_label="OK", news_label="NEWS_CLEAR", kill_label="off",
        next_poll_seconds=30,
    )
    out = stream.getvalue()
    assert "mt5_balance=2000.00" in out
    assert "mt5_equity=1987.50" in out
    assert "mt5_free_margin=1900.00" in out
    assert "realized_daily_pnl=-12.50" in out
    assert "floating_pnl=-3.20" in out
    assert "consecutive_losses=1" in out
    assert "accounting_verified=true" in out
    assert "capital_phase=PHASE_1" in out
    assert "next_milestone=10000" in out
    assert "milestone_mode=compound_growth_not_single_trade_target" in out


def test_terminal_warns_when_accounting_unverified():
    stream = StringIO()
    ProgressPrinter(stream=stream).cycle(
        1, _cycle_outcome(_stat_with_accounting(verified=False)),
        decision_label="NO_TRADE", market_state="OPEN", daily_pnl=0.0,
        risk_label="OK", news_label="NEWS_CLEAR", kill_label="off",
        next_poll_seconds=30,
    )
    out = stream.getvalue()
    assert "accounting_verified=false" in out
    assert "ACCOUNTING_UNVERIFIED_BLOCK_NEW_ENTRIES" in out


# -- D1 (SMC-EXECUTION-002): MT5 realized P&L tightens governor loss inputs -----------
#
# Live evidence 2026-06-11: the morning pre-fix run journaled real MT5 losses
# as fabricated WINs (+1158.62 etc.), so RiskStateTracker saw a profitable
# day (d=0.017) while MT5 said -176.59 (-8.8% of day start) — DAY_PAUSED
# never triggered. The fix takes the WORSE of the journal-derived and the
# MT5-derived loss percentage; it can only tighten, never loosen.


def _mt5_loss_deal(position_id, profit, when):
    return _Obj(
        profit=profit, commission=0.0, swap=0.0, type=1, entry=1,
        position_id=position_id, price=2310.0, time=int(when.timestamp()),
        reason=4, symbol="XAUUSDm",
    )


def _closed_record(record_id, *, pnl, outcome, closed_at):
    return TradeRecord(
        record_id=record_id, created_at_utc=closed_at - timedelta(minutes=5),
        symbol=SYMBOL, direction=Direction.SHORT, outcome=outcome,
        opened_at_utc=closed_at - timedelta(minutes=5),
        closed_at_utc=closed_at, entry_price=2315.0, exit_price=2310.0,
        lot_size=0.05, pnl=pnl,
    )


def test_fabricated_journal_wins_cannot_hide_mt5_daily_loss(tmp_path):
    fake = FakeMT5Trading()
    fake.deals[51] = [_mt5_loss_deal(51, -176.59, NOW - timedelta(hours=2))]
    session, journal, _ = build_session(tmp_path, fake, [approved_smc("smc-1")])
    # the pre-fix accounting wrote this real loss as a fabricated WIN
    journal.log_record(_closed_record(
        "T-poisoned", pnl=1158.62, outcome=TradeOutcome.WIN,
        closed_at=NOW - timedelta(hours=2),
    ))
    outcome = session.run_cycle()
    # 176.59 / (2000 + 176.59) = 0.0811 — over the 5% daily envelope
    assert outcome.risk.daily_loss_pct == pytest.approx(0.08113, abs=1e-4)
    assert outcome.stat.entry_action != "SENT"
    assert "daily loss" in outcome.stat.entry_detail.lower()


def test_mt5_weekly_loss_tightens_and_blocks(tmp_path):
    fake = FakeMT5Trading()
    # NOW is Tuesday 2026-06-09 12:01 UTC; Monday 12:00 is in this ISO week
    fake.deals[52] = [_mt5_loss_deal(52, -250.0, NOW - timedelta(days=1))]
    session, _, _ = build_session(tmp_path, fake, [approved_smc("smc-1")])
    outcome = session.run_cycle()
    # 250 / (2000 + 250) = 0.111 — over the 10% weekly envelope
    assert outcome.risk.weekly_loss_pct == pytest.approx(0.1111, abs=1e-4)
    assert outcome.risk.daily_loss_pct == pytest.approx(0.0)
    assert outcome.stat.entry_action != "SENT"
    assert "weekly loss" in outcome.stat.entry_detail.lower()


def test_tighten_never_loosens_a_worse_journal_figure(tmp_path):
    fake = FakeMT5Trading()
    fake.deals[53] = [_mt5_loss_deal(53, -100.0, NOW - timedelta(hours=1))]
    session, journal, _ = build_session(tmp_path, fake, [no_trade()])
    # journal already records a worse real loss than MT5 reports
    journal.log_record(_closed_record(
        "T-real-loss", pnl=-300.0, outcome=TradeOutcome.LOSS,
        closed_at=NOW - timedelta(hours=1),
    ))
    outcome = session.run_cycle()
    # journal: 300/2000 = 0.15; MT5: 100/2100 = 0.0476 -> journal kept
    assert outcome.risk.daily_loss_pct == pytest.approx(0.15)


def test_profitable_mt5_day_changes_nothing_and_allows_entries(tmp_path):
    fake = FakeMT5Trading()
    fake.deals[54] = [_mt5_loss_deal(54, +50.0, NOW - timedelta(hours=1))]
    session, _, _ = build_session(tmp_path, fake, [approved_smc("smc-1")])
    outcome = session.run_cycle()
    assert outcome.risk.daily_loss_pct == pytest.approx(0.0)
    assert outcome.risk.weekly_loss_pct == pytest.approx(0.0)
    assert outcome.stat.entry_action == "SENT"


def test_unverified_accounting_leaves_risk_state_untouched(tmp_path):
    session, _, _ = build_session(
        tmp_path, _NoHistoryFake(), [approved_smc("smc-1")],
    )
    outcome = session.run_cycle()
    # the unverified gate blocks entries; the loss figures stay journal-based
    assert outcome.risk.daily_loss_pct == pytest.approx(0.0)
    assert outcome.risk.weekly_loss_pct == pytest.approx(0.0)
    assert "ACCOUNTING_UNVERIFIED_BLOCK_NEW_ENTRIES" in outcome.stat.entry_detail


class _WeeklyHistoryFails(FakeMT5Trading):
    """Daily history works; the week-start fetch raises."""

    def history_deals_get(self, *args, **kwargs):
        if args and isinstance(args[0], datetime):
            day_start = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
            if args[0] < day_start:
                raise RuntimeError("weekly history unavailable")
        return super().history_deals_get(*args, **kwargs)


def test_weekly_fetch_failure_still_tightens_daily(tmp_path):
    fake = _WeeklyHistoryFails()
    fake.deals[55] = [_mt5_loss_deal(55, -176.59, NOW - timedelta(hours=2))]
    session, _, _ = build_session(tmp_path, fake, [approved_smc("smc-1")])
    outcome = session.run_cycle()
    assert outcome.risk.daily_loss_pct == pytest.approx(0.08113, abs=1e-4)
    assert outcome.risk.weekly_loss_pct == pytest.approx(0.0)  # unknown stays journal-based
    assert outcome.stat.entry_action != "SENT"


# -- D1b: deposits must never dilute the loss percentages -----------------------------
#
# Live evidence 2026-06-11: the owner topped the account back to 2,000 with
# a +176.59 deposit after a -176.59 day. The deposit-free reconstruction
# (balance - realized) put the day start at 2,176.59 and read the daily
# loss as 8.11% instead of the true 8.83% (176.59/2,000) — a large enough
# deposit could dilute the figure below the 5% pause threshold.


def _balance_op(profit, when):
    return _Obj(
        profit=profit, commission=0.0, swap=0.0, type=2, entry=0,
        position_id=0, price=0.0, time=int(when.timestamp()),
        reason=0, symbol="",
    )


def test_deposit_does_not_dilute_the_daily_loss_pct(tmp_path):
    fake = FakeMT5Trading()
    fake.deals[61] = [_mt5_loss_deal(61, -176.59, NOW - timedelta(hours=2))]
    fake.deals[62] = [_balance_op(+176.59, NOW - timedelta(hours=1))]
    session, _, _ = build_session(tmp_path, fake, [approved_smc("smc-1")])
    outcome = session.run_cycle()
    # true day start: 2000 - (-176.59) - 176.59 = 2000 -> 0.0883, not the
    # diluted 176.59/2176.59 = 0.0811
    assert outcome.risk.daily_loss_pct == pytest.approx(0.08830, abs=1e-4)
    assert outcome.stat.entry_action != "SENT"


def test_withdrawal_enlarges_the_period_start_correctly(tmp_path):
    fake = FakeMT5Trading()
    fake.deals[63] = [_mt5_loss_deal(63, -100.0, NOW - timedelta(hours=2))]
    fake.deals[64] = [_balance_op(-400.0, NOW - timedelta(hours=1))]
    session, _, _ = build_session(tmp_path, fake, [no_trade()])
    outcome = session.run_cycle()
    # day start: 2000 + 100 + 400 = 2500 -> 100/2500 = 4% (below the pause)
    assert outcome.risk.daily_loss_pct == pytest.approx(0.04)


class _BalanceOpsUnavailable(FakeMT5Trading):
    """history works for everything except a balance-ops style call marker.

    fetch_balance_ops_since and fetch_realized_pnl_since share
    history_deals_get, so unavailability is simulated by counting date-range
    calls: the realized fetches (daily, weekly) succeed, later ones fail.
    """

    def __init__(self):
        super().__init__()
        self._range_calls = 0

    def history_deals_get(self, *args, **kwargs):
        if args and isinstance(args[0], datetime):
            self._range_calls += 1
            if self._range_calls > 2:  # daily + weekly realized succeed
                raise RuntimeError("balance ops history unavailable")
        return super().history_deals_get(*args, **kwargs)


def test_unknown_balance_ops_fall_back_to_deposit_free_tighten(tmp_path):
    fake = _BalanceOpsUnavailable()
    fake.deals[65] = [_mt5_loss_deal(65, -176.59, NOW - timedelta(hours=2))]
    session, _, _ = build_session(tmp_path, fake, [approved_smc("smc-1")])
    outcome = session.run_cycle()
    # ops unknown -> deposit-free reconstruction (still tightened, 0.0811)
    assert outcome.risk.daily_loss_pct == pytest.approx(0.08113, abs=1e-4)
    assert outcome.stat.entry_action != "SENT"


# -- decision 2026-06-11-06: trades-per-day counts THIS account's MT5 entries ---------


def _in_deal(position_id, when):
    return _Obj(
        profit=0.0, commission=0.0, swap=0.0, type=1, entry=0,
        position_id=position_id, price=2315.0, time=int(when.timestamp()),
        reason=0, symbol="XAUUSDm",
    )


def test_other_account_journal_trades_do_not_consume_the_daily_cap(tmp_path):
    fake = FakeMT5Trading()  # fresh account: zero entry deals today
    session, journal, _ = build_session(tmp_path, fake, [approved_smc("smc-1")])
    for i in range(10):  # journal carries a previous account's trades today
        journal.log_record(_closed_record(
            f"T-old-acct-{i}", pnl=5.0, outcome=TradeOutcome.WIN,
            closed_at=NOW - timedelta(hours=3),
        ))
    outcome = session.run_cycle()
    assert outcome.risk.trades_today == 0 or outcome.risk.trades_today == 1
    assert outcome.stat.entry_action == "SENT"


def test_mt5_entries_today_enforce_the_daily_cap(tmp_path):
    fake = FakeMT5Trading()
    # owner amendment 2026-06-12-06: the challenge cap is 25/day
    for i in range(25):  # this account already opened 25 trades today
        fake.deals[200 + i] = [_in_deal(200 + i, NOW - timedelta(hours=2))]
    session, _, _ = build_session(tmp_path, fake, [approved_smc("smc-1")])
    outcome = session.run_cycle()
    assert outcome.risk.trades_today == 25
    assert outcome.stat.entry_action != "SENT"
    assert "trades today" in outcome.stat.entry_detail.lower()
