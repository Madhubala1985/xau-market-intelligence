"""XAU/USD market-hours schedule (Task CONTINUOUS-001).

The continuous trading service must PAUSE (not crash, not spam the journal)
while the metals market is closed, and resume when it opens. This module
provides the schedule-based first check; the service combines it with tick
staleness (the broker feed is the ground truth — a frozen tick during
nominally-open hours is also treated as not tradeable).

Default schedule (UTC, approximate Exness XAUUSDm hours):
- daily trading break: 21:00 .. 22:05 UTC every trading day,
- weekend: Friday 21:00 UTC .. Sunday 22:05 UTC.

The exact boundaries vary slightly with broker DST handling; boundaries here
are deliberately a few minutes conservative on the open side, and the tick
staleness check in the service covers any drift honestly.

Pure time arithmetic: no MT5 calls, no credentials, no trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

_FRIDAY = 4
_SATURDAY = 5
_SUNDAY = 6


class MarketState:
    OPEN = "OPEN"
    CLOSED_DAILY_BREAK = "CLOSED_DAILY_BREAK"
    CLOSED_WEEKEND = "CLOSED_WEEKEND"


@dataclass(frozen=True)
class MarketSchedule:
    """Schedule-based market open/closed classification (UTC)."""

    daily_close: time = time(21, 0)
    daily_open: time = time(22, 5)

    def state(self, now: datetime) -> str:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware (UTC)")
        now = now.astimezone(timezone.utc)
        weekday = now.weekday()
        t = now.time()

        if weekday == _SATURDAY:
            return MarketState.CLOSED_WEEKEND
        if weekday == _FRIDAY and t >= self.daily_close:
            return MarketState.CLOSED_WEEKEND
        if weekday == _SUNDAY:
            if t < self.daily_open:
                return MarketState.CLOSED_WEEKEND
            return MarketState.OPEN
        # Mon-Thu (and Friday before close): the daily break applies.
        if self.daily_close <= t < self.daily_open:
            return MarketState.CLOSED_DAILY_BREAK
        return MarketState.OPEN

    def is_open(self, now: datetime) -> bool:
        return self.state(now) == MarketState.OPEN

    def next_open(self, now: datetime) -> datetime:
        """The next moment the schedule reports OPEN (== now when open)."""
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware (UTC)")
        now = now.astimezone(timezone.utc)
        state = self.state(now)
        if state == MarketState.OPEN:
            return now
        if state == MarketState.CLOSED_DAILY_BREAK:
            return now.replace(
                hour=self.daily_open.hour, minute=self.daily_open.minute,
                second=0, microsecond=0,
            )
        # Weekend: the upcoming Sunday at the daily open time.
        days_ahead = (_SUNDAY - now.weekday()) % 7
        sunday = (now + timedelta(days=days_ahead)).replace(
            hour=self.daily_open.hour, minute=self.daily_open.minute,
            second=0, microsecond=0,
        )
        if sunday <= now:  # Sunday pre-open handled above; safety for edges
            sunday += timedelta(days=7)
        return sunday
