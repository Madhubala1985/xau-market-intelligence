"""Reflection engine (Task P9-002).

Classifies trading mistakes mechanically from journaled TradeRecords and generates
a daily review. References 02_ARCHITECTURE.md section 18 and 04_ADAPTATION_POLICY.md.

Offline only: this engine produces a report. It must NEVER change live policy or
parameters (live self-mutation is forbidden, INIT-004 / 04_ADAPTATION_POLICY.md).
It has no apply/update/mutate methods. Never writes credentials.

Mistake categories are derived deterministically from a record's fields and the
day's trade count; no look-ahead beyond the supplied records.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, List, Sequence, Tuple

from src.data.enums import TradeOutcome
from src.data.schemas import TradeRecord

# Outcomes that represent an actually executed trade.
_EXECUTED = {
    TradeOutcome.WIN,
    TradeOutcome.LOSS,
    TradeOutcome.BREAKEVEN,
    TradeOutcome.OPEN,
}


class MistakeCategory(str, Enum):
    OVERCONFIDENCE = "OVERCONFIDENCE"          # high confidence + loss
    IGNORED_UNCERTAINTY = "IGNORED_UNCERTAINTY"  # high uncertainty + loss
    NO_STOP_LOSS = "NO_STOP_LOSS"              # executed trade without a stop
    NO_THESIS = "NO_THESIS"                    # executed trade without a thesis
    OVERTRADING = "OVERTRADING"                # too many trades in the day


@dataclass(frozen=True)
class RecordMistakes:
    record_id: str
    categories: Tuple[MistakeCategory, ...]


@dataclass(frozen=True)
class DailyReview:
    total_decisions: int
    executed_trades: int
    no_trades: int
    wins: int
    losses: int
    breakeven: int
    open_trades: int
    total_pnl: float
    win_rate: float
    overtrading: bool
    mistakes: Tuple[Tuple[MistakeCategory, int], ...]
    per_record: Tuple[RecordMistakes, ...]

    def mistake_count(self, category: MistakeCategory) -> int:
        for cat, count in self.mistakes:
            if cat is category:
                return count
        return 0

    @property
    def summary(self) -> str:
        mistakes = ", ".join(f"{c.value}={n}" for c, n in self.mistakes) or "none"
        return (
            f"trades={self.executed_trades} (W{self.wins}/L{self.losses}) "
            f"win_rate={self.win_rate:.0%} pnl={self.total_pnl:.2f} "
            f"no_trades={self.no_trades} mistakes: {mistakes}"
        )


class ReflectionEngine:
    """Classifies mistakes and builds a daily review (offline; never mutates policy)."""

    def __init__(
        self,
        *,
        overconfidence_threshold: float = 0.7,
        uncertainty_threshold: float = 0.5,
        max_trades_per_day: int = 3,
    ) -> None:
        self._overconfidence_threshold = overconfidence_threshold
        self._uncertainty_threshold = uncertainty_threshold
        self._max_trades_per_day = max_trades_per_day

    # -- per-record classification ----------------------------------------
    def classify(self, record: TradeRecord) -> Tuple[MistakeCategory, ...]:
        """Return the mistake categories for a single record (empty if clean)."""
        if record.outcome not in _EXECUTED:
            return ()  # a no-trade / cancelled decision has no execution mistakes

        cats: List[MistakeCategory] = []
        if record.stop_loss is None:
            cats.append(MistakeCategory.NO_STOP_LOSS)
        if not (record.thesis and record.thesis.strip()):
            cats.append(MistakeCategory.NO_THESIS)
        if record.outcome is TradeOutcome.LOSS:
            if (
                record.confidence is not None
                and record.confidence >= self._overconfidence_threshold
            ):
                cats.append(MistakeCategory.OVERCONFIDENCE)
            if (
                record.uncertainty is not None
                and record.uncertainty >= self._uncertainty_threshold
            ):
                cats.append(MistakeCategory.IGNORED_UNCERTAINTY)
        return tuple(cats)

    # -- daily review ------------------------------------------------------
    def review(self, records: Sequence[TradeRecord]) -> DailyReview:
        """Aggregate a set of records into a daily review with mistake counts."""
        executed = [r for r in records if r.outcome in _EXECUTED]
        no_trades = [r for r in records if r.outcome not in _EXECUTED]

        wins = sum(1 for r in executed if r.outcome is TradeOutcome.WIN)
        losses = sum(1 for r in executed if r.outcome is TradeOutcome.LOSS)
        breakeven = sum(1 for r in executed if r.outcome is TradeOutcome.BREAKEVEN)
        open_trades = sum(1 for r in executed if r.outcome is TradeOutcome.OPEN)
        total_pnl = sum(r.pnl for r in executed if r.pnl is not None)
        decided = wins + losses
        win_rate = wins / decided if decided else 0.0

        counter: Counter = Counter()
        per_record: List[RecordMistakes] = []
        for r in records:
            cats = self.classify(r)
            if cats:
                per_record.append(RecordMistakes(r.record_id, cats))
                counter.update(cats)

        overtrading = len(executed) > self._max_trades_per_day
        if overtrading:
            counter[MistakeCategory.OVERTRADING] = len(executed) - self._max_trades_per_day

        return DailyReview(
            total_decisions=len(records),
            executed_trades=len(executed),
            no_trades=len(no_trades),
            wins=wins,
            losses=losses,
            breakeven=breakeven,
            open_trades=open_trades,
            total_pnl=total_pnl,
            win_rate=win_rate,
            overtrading=overtrading,
            mistakes=tuple(sorted(counter.items(), key=lambda kv: kv[0].value)),
            per_record=tuple(per_record),
        )

    def review_journal(self, records: Iterable[TradeRecord]) -> DailyReview:
        """Convenience: review records pulled from the trade journal."""
        return self.review(list(records))
