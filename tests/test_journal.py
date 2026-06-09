"""Tests for P9-001 trade journal.

Required:
- decisions persisted,
- restart-safe.
"""

from datetime import datetime, timedelta, timezone

from src.data.enums import DecisionStatus, Direction, TradeOutcome
from src.data.schemas import TradeDecision, TradeRecord
from src.journal import EntryKind, TradeJournal

UTC = timezone.utc
NOW = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)


def long_decision() -> TradeDecision:
    return TradeDecision(
        decision_id="D-1", time_utc=NOW, symbol="XAUUSD", direction=Direction.LONG,
        status=DecisionStatus.PROPOSED, thesis="sweep reclaim with displacement",
        invalidation_price=2295.0, entry_price=2300.0, stop_loss=2295.0,
        take_profits=(2310.0, 2320.0), confidence=0.7, uncertainty=0.2,
    )


def no_trade_decision() -> TradeDecision:
    return TradeDecision(
        decision_id="D-2", time_utc=NOW, symbol="XAUUSD",
        direction=Direction.NO_TRADE, status=DecisionStatus.NO_TRADE,
        reason="regime CHOPPY blocks new trades",
    )


def trade_record() -> TradeRecord:
    return TradeRecord(
        record_id="R-1", created_at_utc=NOW, symbol="XAUUSD",
        direction=Direction.LONG, outcome=TradeOutcome.WIN,
        opened_at_utc=NOW, closed_at_utc=NOW + timedelta(hours=2),
        entry_price=2300.0, exit_price=2310.0, pnl=100.0,
    )


def journal(tmp_path) -> TradeJournal:
    return TradeJournal(tmp_path / "journal.jsonl")


# ---------------------------------------------------------------------------
# Decisions persisted (trade AND no-trade)
# ---------------------------------------------------------------------------

def test_decisions_persisted(tmp_path):
    j = journal(tmp_path)
    j.log_decision(long_decision())
    j.log_decision(no_trade_decision())
    entries = j.entries()
    assert len(entries) == 2
    assert all(e.kind is EntryKind.DECISION for e in entries)
    ids = [d.decision_id for d in j.decisions()]
    assert ids == ["D-1", "D-2"]


def test_no_trade_decision_logged(tmp_path):
    j = journal(tmp_path)
    j.log_decision(no_trade_decision())
    d = j.decisions()[0]
    assert d.direction is Direction.NO_TRADE
    assert d.reason == "regime CHOPPY blocks new trades"


def test_trade_record_logged(tmp_path):
    j = journal(tmp_path)
    j.log_record(trade_record())
    records = j.records()
    assert len(records) == 1
    assert records[0].outcome is TradeOutcome.WIN
    assert records[0].pnl == 100.0


def test_decision_round_trip_equal(tmp_path):
    j = journal(tmp_path)
    original = long_decision()
    j.log_decision(original)
    reloaded = j.decisions()[0]
    assert reloaded == original  # frozen pydantic models compare by value


# ---------------------------------------------------------------------------
# Restart-safe
# ---------------------------------------------------------------------------

def test_restart_safe_reload(tmp_path):
    path = tmp_path / "journal.jsonl"
    writer = TradeJournal(path)
    writer.log_decision(long_decision())
    writer.log_decision(no_trade_decision())
    writer.log_record(trade_record())

    # A fresh journal instance on the same path reloads everything.
    reader = TradeJournal(path)
    entries = reader.entries()
    assert len(entries) == 3
    assert len(reader.decisions()) == 2
    assert len(reader.records()) == 1
    assert reader.decisions()[0].decision_id == "D-1"


def test_appends_across_instances(tmp_path):
    path = tmp_path / "journal.jsonl"
    TradeJournal(path).log_decision(long_decision())
    TradeJournal(path).log_decision(no_trade_decision())  # new instance appends
    assert len(TradeJournal(path).entries()) == 2


def test_empty_journal_when_absent(tmp_path):
    assert TradeJournal(tmp_path / "missing.jsonl").entries() == []


# ---------------------------------------------------------------------------
# No credentials ever written
# ---------------------------------------------------------------------------

def test_no_credentials_in_journal_file(tmp_path):
    path = tmp_path / "journal.jsonl"
    j = TradeJournal(path)
    j.log_decision(long_decision())
    j.log_record(trade_record())
    blob = path.read_text(encoding="utf-8").lower()
    for token in ("password", "login", "server", "secret", "token"):
        assert token not in blob
