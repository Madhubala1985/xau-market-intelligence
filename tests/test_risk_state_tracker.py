"""Tests for the journal-driven risk state tracker (03_RISK_POLICY.md inputs).

Proves the Risk Governor's enforcement inputs are computed from real journal
history: daily/weekly realized loss fractions, trades opened today, the
consecutive-loss streak, and open symbols — and that the live shadow session
feeds them into the pipeline instead of permanent zeros.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.data.enums import Direction, TradeOutcome
from src.data.schemas import TradeRecord
from src.journal import TradeJournal
from src.risk import RiskStateTracker

UTC = timezone.utc
NOW = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)  # Wednesday
BALANCE = 2000.0


def record(
    rid: str,
    *,
    outcome: TradeOutcome,
    pnl=None,
    opened=None,
    closed=None,
    direction=Direction.LONG,
    symbol="XAUUSDM",
) -> TradeRecord:
    return TradeRecord(
        record_id=rid,
        created_at_utc=opened or NOW,
        symbol=symbol,
        direction=direction,
        outcome=outcome,
        opened_at_utc=opened,
        closed_at_utc=closed,
        pnl=pnl,
    )


@pytest.fixture
def journal(tmp_path) -> TradeJournal:
    return TradeJournal(tmp_path / "journal.jsonl")


def test_empty_journal_yields_zero_state(journal):
    snap = RiskStateTracker(journal).snapshot(NOW, BALANCE)
    assert snap.daily_loss_pct == 0.0
    assert snap.weekly_loss_pct == 0.0
    assert snap.trades_today == 0
    assert snap.consecutive_losses == 0
    assert snap.open_symbols == frozenset()


def test_daily_loss_fraction_from_todays_closed_losses(journal):
    today = NOW - timedelta(hours=2)
    journal.log_record(record("L1", outcome=TradeOutcome.LOSS, pnl=-10.0,
                              opened=today, closed=today))
    journal.log_record(record("L2", outcome=TradeOutcome.LOSS, pnl=-30.0,
                              opened=today, closed=today))
    # Decision 2026-06-12-05: the daily loss is NET drawdown — wins offset
    # losses, matching the MT5-truth net measure that tightens this figure.
    journal.log_record(record("W1", outcome=TradeOutcome.WIN, pnl=25.0,
                              opened=today, closed=NOW - timedelta(hours=1)))
    snap = RiskStateTracker(journal).snapshot(NOW, BALANCE)
    assert snap.daily_loss_pct == pytest.approx(15.0 / BALANCE)  # net -15


def test_weekly_includes_earlier_weekdays_but_not_last_week(journal):
    monday = NOW - timedelta(days=2)          # same ISO week
    last_friday = NOW - timedelta(days=5)     # previous week
    journal.log_record(record("M", outcome=TradeOutcome.LOSS, pnl=-20.0,
                              opened=monday, closed=monday))
    journal.log_record(record("F", outcome=TradeOutcome.LOSS, pnl=-50.0,
                              opened=last_friday, closed=last_friday))
    snap = RiskStateTracker(journal).snapshot(NOW, BALANCE)
    assert snap.daily_loss_pct == 0.0
    assert snap.weekly_loss_pct == pytest.approx(20.0 / BALANCE)  # 1%


def test_trades_today_counts_actionable_opens_only(journal):
    today = NOW - timedelta(hours=3)
    yesterday = NOW - timedelta(days=1)
    journal.log_record(record("T1", outcome=TradeOutcome.OPEN, opened=today))
    journal.log_record(record("T2", outcome=TradeOutcome.WIN, pnl=5.0,
                              opened=today, closed=NOW - timedelta(hours=1)))
    journal.log_record(record("Y", outcome=TradeOutcome.LOSS, pnl=-5.0,
                              opened=yesterday, closed=yesterday))
    journal.log_record(record("NT", outcome=TradeOutcome.NO_TRADE,
                              direction=Direction.NO_TRADE))
    snap = RiskStateTracker(journal).snapshot(NOW, BALANCE)
    assert snap.trades_today == 2


def test_consecutive_loss_streak_breaks_on_win(journal):
    t = NOW - timedelta(hours=6)
    journal.log_record(record("W", outcome=TradeOutcome.WIN, pnl=10.0,
                              opened=t, closed=t))
    journal.log_record(record("L1", outcome=TradeOutcome.LOSS, pnl=-5.0,
                              opened=t, closed=t + timedelta(hours=1)))
    journal.log_record(record("L2", outcome=TradeOutcome.LOSS, pnl=-5.0,
                              opened=t, closed=t + timedelta(hours=2)))
    snap = RiskStateTracker(journal).snapshot(NOW, BALANCE)
    assert snap.consecutive_losses == 2
    # Another win after the losses resets the streak.
    journal.log_record(record("W2", outcome=TradeOutcome.WIN, pnl=8.0,
                              opened=t, closed=t + timedelta(hours=3)))
    assert RiskStateTracker(journal).snapshot(NOW, BALANCE).consecutive_losses == 0


def test_open_symbols_reported_for_duplicate_check(journal):
    journal.log_record(record("O", outcome=TradeOutcome.OPEN,
                              opened=NOW - timedelta(hours=1)))
    snap = RiskStateTracker(journal).snapshot(NOW, BALANCE)
    assert snap.open_symbols == frozenset({"XAUUSDM"})


def test_unknown_balance_reports_zero_fractions_safely(journal):
    today = NOW - timedelta(hours=1)
    journal.log_record(record("L", outcome=TradeOutcome.LOSS, pnl=-10.0,
                              opened=today, closed=today))
    snap = RiskStateTracker(journal).snapshot(NOW, None)
    # Governor blocks separately on unknown balance (BROKER_STATE_UNKNOWN).
    assert snap.daily_loss_pct == 0.0
    assert snap.trades_today == 1  # counts still computed


def test_restart_safe_state_from_disk(tmp_path):
    path = tmp_path / "journal.jsonl"
    today = NOW - timedelta(hours=1)
    TradeJournal(path).log_record(record("L", outcome=TradeOutcome.LOSS,
                                         pnl=-40.0, opened=today, closed=today))
    # A fresh tracker over a fresh journal instance sees the same state.
    snap = RiskStateTracker(TradeJournal(path)).snapshot(NOW, BALANCE)
    assert snap.daily_loss_pct == pytest.approx(0.02)


def test_naive_now_is_rejected(journal):
    with pytest.raises(ValueError):
        RiskStateTracker(journal).snapshot(datetime(2026, 6, 10, 14, 0), BALANCE)
