"""Tests for P9-002 reflection engine (mistake categories assigned)."""

from datetime import datetime, timezone

from src.data.enums import Direction, TradeOutcome
from src.data.schemas import TradeRecord
from src.reflection import MistakeCategory, ReflectionEngine

UTC = timezone.utc
NOW = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)


def record(rid: str, **overrides) -> TradeRecord:
    kwargs = dict(
        record_id=rid, created_at_utc=NOW, symbol="XAUUSD", direction=Direction.LONG,
        outcome=TradeOutcome.WIN, entry_price=2300.0, exit_price=2310.0,
        stop_loss=2295.0, take_profit=2310.0, thesis="sweep reclaim",
        confidence=0.6, uncertainty=0.2, pnl=100.0,
    )
    kwargs.update(overrides)
    return TradeRecord(**kwargs)


def engine() -> ReflectionEngine:
    return ReflectionEngine(overconfidence_threshold=0.7, uncertainty_threshold=0.5, max_trades_per_day=3)


# ---------------------------------------------------------------------------
# Per-record mistake classification
# ---------------------------------------------------------------------------

def test_clean_winner_has_no_mistakes():
    assert engine().classify(record("R-1")) == ()


def test_overconfidence_on_loss():
    cats = engine().classify(record("R-2", outcome=TradeOutcome.LOSS, confidence=0.9, pnl=-50.0))
    assert MistakeCategory.OVERCONFIDENCE in cats


def test_ignored_uncertainty_on_loss():
    cats = engine().classify(record("R-3", outcome=TradeOutcome.LOSS, uncertainty=0.8, pnl=-50.0))
    assert MistakeCategory.IGNORED_UNCERTAINTY in cats


def test_no_stop_loss_flagged():
    cats = engine().classify(record("R-4", stop_loss=None))
    assert MistakeCategory.NO_STOP_LOSS in cats


def test_no_thesis_flagged():
    cats = engine().classify(record("R-5", thesis=None))
    assert MistakeCategory.NO_THESIS in cats


def test_no_execution_mistakes_for_no_trade():
    # A NO_TRADE record is a decision, not an executed trade -> no execution mistakes.
    cats = engine().classify(record("R-6", outcome=TradeOutcome.NO_TRADE, stop_loss=None, thesis=None))
    assert cats == ()


def test_multiple_categories_on_one_record():
    cats = engine().classify(
        record("R-7", outcome=TradeOutcome.LOSS, confidence=0.95, uncertainty=0.8,
               stop_loss=None, thesis=None, pnl=-80.0)
    )
    assert set(cats) == {
        MistakeCategory.NO_STOP_LOSS,
        MistakeCategory.NO_THESIS,
        MistakeCategory.OVERCONFIDENCE,
        MistakeCategory.IGNORED_UNCERTAINTY,
    }


# ---------------------------------------------------------------------------
# Daily review aggregation
# ---------------------------------------------------------------------------

def test_daily_review_counts_and_pnl():
    records = [
        record("R-1", outcome=TradeOutcome.WIN, pnl=100.0),
        record("R-2", outcome=TradeOutcome.LOSS, pnl=-50.0, confidence=0.9),
        record("R-3", outcome=TradeOutcome.NO_TRADE, pnl=None),
    ]
    review = engine().review(records)
    assert review.total_decisions == 3
    assert review.executed_trades == 2
    assert review.no_trades == 1
    assert review.wins == 1 and review.losses == 1
    assert review.total_pnl == 50.0
    assert review.win_rate == 0.5
    assert review.mistake_count(MistakeCategory.OVERCONFIDENCE) == 1


def test_overtrading_flagged():
    records = [record(f"R-{i}", outcome=TradeOutcome.WIN, pnl=10.0) for i in range(5)]
    review = engine().review(records)
    assert review.overtrading is True
    assert review.mistake_count(MistakeCategory.OVERTRADING) == 2  # 5 - max 3


def test_no_overtrading_within_limit():
    records = [record(f"R-{i}", outcome=TradeOutcome.WIN, pnl=10.0) for i in range(3)]
    review = engine().review(records)
    assert review.overtrading is False
    assert review.mistake_count(MistakeCategory.OVERTRADING) == 0


def test_review_summary_text():
    review = engine().review([record("R-1", outcome=TradeOutcome.WIN, pnl=100.0)])
    assert "trades=1" in review.summary
    assert "win_rate=100%" in review.summary


def test_empty_review():
    review = engine().review([])
    assert review.total_decisions == 0
    assert review.win_rate == 0.0
    assert review.mistakes == ()


# ---------------------------------------------------------------------------
# Offline only: never mutates policy
# ---------------------------------------------------------------------------

def test_engine_has_no_mutation_method():
    methods = dir(ReflectionEngine)
    for banned in ("apply", "update_policy", "mutate", "set_param", "adapt", "execute", "order"):
        assert not any(banned in m.lower() for m in methods)
