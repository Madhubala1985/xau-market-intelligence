"""Journal-driven risk state tracker (03_RISK_POLICY.md enforcement inputs).

The Risk Governor checks daily loss, weekly loss, trades-per-day, consecutive
losses, and duplicate exposure — but those are INPUTS: something must compute
them from actual trading history or the checks silently see zeros forever.
This tracker derives them from the TradeJournal's TradeRecords, so the live
loop (shadow now, supervised demo later) feeds the governor real values.

Conventions:
- Loss percentages are positive fractions of the provided balance
  (e.g. 0.02 == 2% lost), matching RiskContext / RiskLimits semantics.
- "Today" is the UTC calendar day of `now`; "this week" is the ISO week
  (Monday start) of `now`.
- consecutive_losses counts the LOSS streak in closed trades, most recent
  first; any WIN or BREAKEVEN breaks the streak.
- If balance is unknown (None/<= 0), loss fractions are reported as 0.0; this
  is safe because the governor independently blocks on an unknown balance
  (BROKER_STATE_UNKNOWN).

Read-only: this module never places orders and never mutates the journal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import FrozenSet, List, Optional

from src.data.enums import Direction, TradeOutcome
from src.data.schemas import TradeRecord
from src.journal.journal import TradeJournal

_ACTIONABLE = (Direction.LONG, Direction.SHORT)
_STREAK_BREAKERS = (TradeOutcome.WIN, TradeOutcome.BREAKEVEN)


def collapse_records(records: List[TradeRecord]) -> List[TradeRecord]:
    """Collapse an append-only record stream to the LATEST entry per record_id.

    The journal never rewrites lines; a trade's lifecycle is appended as
    successive TradeRecords sharing one record_id (OPEN, then a closing
    record). For risk math and reconciliation only the latest state counts —
    otherwise a long-closed trade's OPEN record would block trading forever.
    Journal order is preserved; the last occurrence wins.
    """
    latest: dict = {}
    for r in records:
        latest[r.record_id] = r
    return list(latest.values())


@dataclass(frozen=True)
class RiskStateSnapshot:
    """Risk enforcement inputs derived from the journal at one moment."""

    time_utc: datetime
    daily_loss_pct: float
    weekly_loss_pct: float
    trades_today: int
    consecutive_losses: int
    open_symbols: FrozenSet[str]


class RiskStateTracker:
    """Computes Risk Governor inputs from journaled TradeRecords."""

    def __init__(self, journal: TradeJournal) -> None:
        self._journal = journal

    def snapshot(self, now: datetime, balance: Optional[float]) -> RiskStateSnapshot:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware (UTC)")
        now = now.astimezone(timezone.utc)
        records = collapse_records(self._journal.records())

        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = day_start - timedelta(days=now.weekday())  # ISO Monday

        daily_loss = self._realized_loss(records, since=day_start, until=now)
        weekly_loss = self._realized_loss(records, since=week_start, until=now)
        safe_balance = balance if balance is not None and balance > 0 else None

        return RiskStateSnapshot(
            time_utc=now,
            daily_loss_pct=(daily_loss / safe_balance) if safe_balance else 0.0,
            weekly_loss_pct=(weekly_loss / safe_balance) if safe_balance else 0.0,
            trades_today=self._trades_opened(records, since=day_start, until=now),
            consecutive_losses=self._loss_streak(records),
            open_symbols=self._open_symbols(records),
        )

    # -- internals -----------------------------------------------------------
    @staticmethod
    def _realized_loss(
        records: List[TradeRecord], *, since: datetime, until: datetime
    ) -> float:
        """NET realized loss (positive number, floored at 0) in the window.

        Decision 2026-06-12-05: "daily/weekly loss" means net drawdown —
        wins offset losses, matching the MT5-truth net measure
        (fetch_realized_pnl_since) that tightens this figure. The old
        gross-losses-only sum paused a -1.2% net day as if it were -5.4%.
        """
        net = 0.0
        for r in records:
            if r.closed_at_utc is None or r.pnl is None:
                continue
            if since <= r.closed_at_utc <= until:
                net += r.pnl
        return max(0.0, -net)

    @staticmethod
    def _trades_opened(
        records: List[TradeRecord], *, since: datetime, until: datetime
    ) -> int:
        return sum(
            1
            for r in records
            if r.direction in _ACTIONABLE
            and r.opened_at_utc is not None
            and since <= r.opened_at_utc <= until
        )

    @staticmethod
    def _loss_streak(records: List[TradeRecord]) -> int:
        """LOSS streak over closed trades, most recent close first."""
        closed = sorted(
            (r for r in records if r.closed_at_utc is not None
             and r.outcome in (TradeOutcome.LOSS, *_STREAK_BREAKERS)),
            key=lambda r: r.closed_at_utc,
            reverse=True,
        )
        streak = 0
        for r in closed:
            if r.outcome is TradeOutcome.LOSS:
                streak += 1
            else:
                break
        return streak

    @staticmethod
    def _open_symbols(records: List[TradeRecord]) -> FrozenSet[str]:
        return frozenset(
            r.symbol for r in records if r.outcome is TradeOutcome.OPEN
        )
