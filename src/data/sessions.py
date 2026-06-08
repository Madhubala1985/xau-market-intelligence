"""Session / kill-zone engine (Task P2-002).

Classifies normalized UTC timestamps into trading sessions and tracks session
highs/lows. References 14_SESSION_KILLZONE_POLICY.md and 06_DATA_POLICY.md
(session classification must use normalized time).

Model: the UTC day is tiled into ordered, non-overlapping segments that cover
[00:00, 24:00). The London-New-York overlap is represented as its own segment
sitting between the London-only and New-York-only segments, so every timestamp
maps to exactly one session with exact [start, end) bounds and no gaps.

Default tiling (UTC):
    00:00-08:00  ASIAN
    08:00-13:00  LONDON
    13:00-16:00  LONDON_NY_OVERLAP
    16:00-21:00  NEW_YORK
    21:00-22:00  ROLLOVER
    22:00-24:00  LOW_LIQUIDITY

Weekend/closed: the market is treated as closed from Friday close (default
21:00 UTC) through Sunday open (default 22:00 UTC), and all day Saturday.

Kill-zone / tradeability are flags only. Per policy, a kill zone increases
attention but never triggers a trade on its own; the risk governor decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence

from src.data.enums import SessionType
from src.data.schemas import Candle, SessionState

UTC = timezone.utc
_DAY_MINUTES = 24 * 60


@dataclass(frozen=True)
class SessionSegment:
    """A labeled time-of-day window, in minutes from UTC midnight."""

    session: SessionType
    start_min: int  # inclusive
    end_min: int    # exclusive


# Default day tiling (must cover [0, 1440) with no gaps or overlaps).
DEFAULT_SEGMENTS: tuple[SessionSegment, ...] = (
    SessionSegment(SessionType.ASIAN, 0, 8 * 60),
    SessionSegment(SessionType.LONDON, 8 * 60, 13 * 60),
    SessionSegment(SessionType.LONDON_NY_OVERLAP, 13 * 60, 16 * 60),
    SessionSegment(SessionType.NEW_YORK, 16 * 60, 21 * 60),
    SessionSegment(SessionType.ROLLOVER, 21 * 60, 22 * 60),
    SessionSegment(SessionType.LOW_LIQUIDITY, 22 * 60, 24 * 60),
)

_DEFAULT_KILL_ZONES = frozenset(
    {SessionType.LONDON, SessionType.NEW_YORK, SessionType.LONDON_NY_OVERLAP}
)
_DEFAULT_NON_TRADEABLE = frozenset(
    {SessionType.ROLLOVER, SessionType.LOW_LIQUIDITY, SessionType.CLOSED}
)


@dataclass(frozen=True)
class SessionConfig:
    """Configuration for the session engine.

    Times are minutes from UTC midnight. The market is closed from
    weekend_close_min on Friday through weekend_open_min on Sunday.
    """

    segments: tuple[SessionSegment, ...] = DEFAULT_SEGMENTS
    kill_zone_sessions: frozenset = _DEFAULT_KILL_ZONES
    non_tradeable_sessions: frozenset = _DEFAULT_NON_TRADEABLE
    weekend_close_min: int = 21 * 60  # Friday 21:00 UTC
    weekend_open_min: int = 22 * 60   # Sunday 22:00 UTC

    def __post_init__(self) -> None:
        segs = self.segments
        if not segs:
            raise ValueError("segments must not be empty")
        if segs[0].start_min != 0 or segs[-1].end_min != _DAY_MINUTES:
            raise ValueError("segments must cover the full day [0, 1440)")
        prev_end = 0
        for seg in segs:
            if seg.start_min != prev_end:
                raise ValueError(
                    f"segments must tile without gaps/overlaps near minute {prev_end}"
                )
            if seg.end_min <= seg.start_min:
                raise ValueError("each segment must have end_min > start_min")
            prev_end = seg.end_min


@dataclass(frozen=True)
class SessionLevels:
    """High/low for one contiguous occurrence of a session."""

    session: SessionType
    start_utc: datetime
    end_utc: datetime
    high: float
    low: float
    candle_count: int


def _ensure_utc(time_utc: datetime, field_name: str = "time_utc") -> datetime:
    if time_utc.tzinfo is None or time_utc.tzinfo.utcoffset(time_utc) is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return time_utc.astimezone(UTC)


class SessionEngine:
    """Maps UTC timestamps to sessions and tracks session highs/lows."""

    def __init__(self, config: Optional[SessionConfig] = None) -> None:
        self._config = config or SessionConfig()

    # -- market open / classification -------------------------------------
    def is_market_open(self, time_utc: datetime) -> bool:
        """Return True if the market is open at the given UTC time."""
        t = _ensure_utc(time_utc)
        weekday = t.weekday()  # Mon=0 .. Sun=6
        minutes = t.hour * 60 + t.minute
        if weekday == 5:  # Saturday
            return False
        if weekday == 4 and minutes >= self._config.weekend_close_min:  # Fri close
            return False
        if weekday == 6 and minutes < self._config.weekend_open_min:  # Sun pre-open
            return False
        return True

    def classify(self, time_utc: datetime) -> SessionType:
        """Classify a UTC timestamp into a SessionType."""
        t = _ensure_utc(time_utc)
        if not self.is_market_open(t):
            return SessionType.CLOSED
        return self._segment_for(t).session

    def segment_bounds(self, time_utc: datetime) -> tuple[datetime, datetime]:
        """Return [start, end) UTC bounds of the session containing the time.

        For a closed-market time the bounds span the whole UTC day.
        """
        t = _ensure_utc(time_utc)
        midnight = t.replace(hour=0, minute=0, second=0, microsecond=0)
        if not self.is_market_open(t):
            return midnight, midnight + timedelta(days=1)
        seg = self._segment_for(t)
        return (
            midnight + timedelta(minutes=seg.start_min),
            midnight + timedelta(minutes=seg.end_min),
        )

    def session_state(
        self,
        time_utc: datetime,
        *,
        high: Optional[float] = None,
        low: Optional[float] = None,
    ) -> SessionState:
        """Build a SessionState snapshot for a UTC timestamp."""
        t = _ensure_utc(time_utc)
        session = self.classify(t)
        start, end = self.segment_bounds(t)
        return SessionState(
            session=session,
            time_utc=t,
            session_start_utc=start,
            session_end_utc=end,
            is_kill_zone=session in self._config.kill_zone_sessions,
            is_tradeable=session not in self._config.non_tradeable_sessions,
            session_high=high,
            session_low=low,
        )

    # -- level tracking ----------------------------------------------------
    def annotate(self, candles: Sequence[Candle]) -> List[SessionState]:
        """Return a SessionState per candle with running session high/low.

        The high/low reflect only candles seen so far within the current session
        occurrence (including the current candle), so there is no look-ahead.
        """
        states: List[SessionState] = []
        current_key = None
        run_high: Optional[float] = None
        run_low: Optional[float] = None

        for candle in candles:
            key = self._instance_key(candle.time_utc)
            if key != current_key:
                current_key = key
                run_high = candle.high
                run_low = candle.low
            else:
                run_high = max(run_high, candle.high)
                run_low = min(run_low, candle.low)
            states.append(
                self.session_state(candle.time_utc, high=run_high, low=run_low)
            )
        return states

    def track_session_levels(self, candles: Sequence[Candle]) -> List[SessionLevels]:
        """Aggregate high/low for each contiguous session occurrence."""
        levels: List[SessionLevels] = []
        current_key = None
        seg_session: Optional[SessionType] = None
        seg_start: Optional[datetime] = None
        seg_end: Optional[datetime] = None
        high = low = 0.0
        count = 0

        def flush() -> None:
            if current_key is not None and count > 0:
                levels.append(
                    SessionLevels(
                        session=seg_session,
                        start_utc=seg_start,
                        end_utc=seg_end,
                        high=high,
                        low=low,
                        candle_count=count,
                    )
                )

        for candle in candles:
            key = self._instance_key(candle.time_utc)
            if key != current_key:
                flush()
                current_key = key
                seg_session = self.classify(candle.time_utc)
                seg_start, seg_end = self.segment_bounds(candle.time_utc)
                high = candle.high
                low = candle.low
                count = 1
            else:
                high = max(high, candle.high)
                low = min(low, candle.low)
                count += 1
        flush()
        return levels

    # -- internals ---------------------------------------------------------
    def _segment_for(self, t: datetime) -> SessionSegment:
        minutes = t.hour * 60 + t.minute
        for seg in self._config.segments:
            if seg.start_min <= minutes < seg.end_min:
                return seg
        # Should be unreachable because segments tile the full day.
        raise ValueError(f"no session segment for minute {minutes}")

    def _instance_key(self, time_utc: datetime) -> tuple:
        """Identify one session occurrence: (session, its start instant)."""
        t = _ensure_utc(time_utc)
        session = self.classify(t)
        start, _ = self.segment_bounds(t)
        return (session, start)
