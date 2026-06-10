"""Tests for the XAU market-hours schedule (CONTINUOUS-001)."""

from datetime import datetime, timezone

import pytest

from src.execution.market_hours import MarketSchedule, MarketState

UTC = timezone.utc
SCHEDULE = MarketSchedule()


def dt(day, hour, minute=0):
    # 2026-06-08 is a Monday.
    return datetime(2026, 6, day, hour, minute, tzinfo=UTC)


def test_weekday_trading_hours_are_open():
    assert SCHEDULE.is_open(dt(9, 12))       # Tuesday noon
    assert SCHEDULE.is_open(dt(8, 0, 30))    # Monday just after midnight
    assert SCHEDULE.is_open(dt(12, 20, 59))  # Friday before the close


def test_daily_break_is_closed_and_reopens():
    assert SCHEDULE.state(dt(9, 21, 30)) == MarketState.CLOSED_DAILY_BREAK
    assert SCHEDULE.state(dt(9, 22, 4)) == MarketState.CLOSED_DAILY_BREAK
    assert SCHEDULE.is_open(dt(9, 22, 5))
    assert SCHEDULE.next_open(dt(9, 21, 30)) == dt(9, 22, 5)


def test_weekend_is_closed_from_friday_close_to_sunday_open():
    assert SCHEDULE.state(dt(12, 21, 0)) == MarketState.CLOSED_WEEKEND   # Fri
    assert SCHEDULE.state(dt(13, 12)) == MarketState.CLOSED_WEEKEND      # Sat
    assert SCHEDULE.state(dt(14, 22, 0)) == MarketState.CLOSED_WEEKEND   # Sun pre
    assert SCHEDULE.is_open(dt(14, 22, 5))                                # Sun open


def test_next_open_over_the_weekend_is_sunday_open():
    expected = dt(14, 22, 5)  # Sunday
    assert SCHEDULE.next_open(dt(12, 21, 30)) == expected  # Friday evening
    assert SCHEDULE.next_open(dt(13, 3)) == expected       # Saturday
    assert SCHEDULE.next_open(dt(14, 10)) == expected      # Sunday morning


def test_next_open_when_open_is_now():
    now = dt(9, 12)
    assert SCHEDULE.next_open(now) == now


def test_naive_datetime_is_rejected():
    with pytest.raises(ValueError):
        SCHEDULE.is_open(datetime(2026, 6, 9, 12, 0))
    with pytest.raises(ValueError):
        SCHEDULE.next_open(datetime(2026, 6, 9, 12, 0))
