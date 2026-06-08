"""Timeframe aggregation engine (Task P2-001).

Aggregates a lower-timeframe Candle series (e.g. 1M) into a higher timeframe
(5M / 15M / 1H / 4H / Daily). Aggregation rules:

- bars are grouped into aligned UTC windows [bucket_start, bucket_start + step),
- open  = open of the first (earliest) source bar in the window,
- high  = max high, low = min low,
- close = close of the last (latest) source bar in the window,
- tick_volume = sum; real_volume = sum if every source bar has it, else None,
- spread is not carried (an aggregated bar has no single spread): None.

No future leakage (06_DATA_POLICY.md):
- Each aggregated bar is computed only from source bars whose time falls inside
  its own window, so no value comes from a later period.
- A bar is only "known" once its window has fully elapsed. With drop_incomplete
  (the default), the still-forming bar is withheld: when `now` is given, any
  bucket whose end is after `now` is dropped; when `now` is None, the most
  recent bucket is dropped as potentially incomplete. Pass drop_incomplete=False
  to receive the forming bar explicitly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Sequence

from src.data.enums import Timeframe
from src.data.schemas import Candle

UTC = timezone.utc

# Aggregatable timeframes and their interval in seconds (TICK is excluded).
_INTERVAL_SECONDS = {
    Timeframe.M1: 60,
    Timeframe.M5: 5 * 60,
    Timeframe.M15: 15 * 60,
    Timeframe.H1: 60 * 60,
    Timeframe.H4: 4 * 60 * 60,
    Timeframe.D1: 24 * 60 * 60,
}


class AggregationError(Exception):
    """Raised when aggregation inputs are invalid."""


def _interval_seconds(timeframe: Timeframe) -> int:
    seconds = _INTERVAL_SECONDS.get(timeframe)
    if seconds is None:
        raise AggregationError(f"timeframe {timeframe} cannot be aggregated")
    return seconds


def _bucket_start(time_utc: datetime, step_seconds: int) -> datetime:
    """Return the aligned UTC window start for a timestamp.

    Intraday steps align to the UTC epoch grid; the daily step aligns to UTC
    midnight (both follow from flooring the epoch to a multiple of the step).
    """
    epoch = int(time_utc.timestamp())
    start_epoch = epoch - (epoch % step_seconds)
    return datetime.fromtimestamp(start_epoch, tz=UTC)


class TimeframeAggregator:
    """Stateless aggregator from a lower timeframe to a higher one."""

    def aggregate(
        self,
        candles: Sequence[Candle],
        target: Timeframe,
        *,
        now: Optional[datetime] = None,
        drop_incomplete: bool = True,
    ) -> List[Candle]:
        """Aggregate `candles` into `target` timeframe bars (oldest-first).

        Args:
            candles: source bars in strictly increasing time order, all sharing
                one symbol and one (lower) timeframe.
            target: the higher timeframe to build.
            now: reference UTC time used to decide which trailing bar is still
                forming (no future leakage). If None, the last bucket is treated
                as potentially incomplete.
            drop_incomplete: when True (default) the forming bar is withheld.

        Raises:
            AggregationError: on inconsistent input or an invalid target.
        """
        if not candles:
            return []

        source_tf = self._validate_source(candles)
        step = _interval_seconds(target)
        source_step = _interval_seconds(source_tf)
        if step <= source_step:
            raise AggregationError(
                f"target {target.value} must be larger than source {source_tf.value}"
            )
        if step % source_step != 0:
            raise AggregationError(
                f"target {target.value} is not a whole multiple of source "
                f"{source_tf.value}"
            )

        buckets = self._group(candles, step)
        bars = [self._build_bar(start, group, target) for start, group in buckets]

        if drop_incomplete:
            bars = self._drop_incomplete(bars, step, now)
        return bars

    # -- internals ---------------------------------------------------------
    def _validate_source(self, candles: Sequence[Candle]) -> Timeframe:
        symbols = {c.symbol for c in candles}
        if len(symbols) > 1:
            raise AggregationError(f"candles mix multiple symbols: {sorted(symbols)}")
        timeframes = {c.timeframe for c in candles}
        if len(timeframes) > 1:
            raise AggregationError(
                f"candles mix multiple timeframes: {sorted(timeframes)}"
            )
        try:
            source_tf = Timeframe(next(iter(timeframes)))
        except ValueError as exc:
            raise AggregationError(
                f"unknown source timeframe: {next(iter(timeframes))!r}"
            ) from exc

        for i in range(1, len(candles)):
            if candles[i].time_utc <= candles[i - 1].time_utc:
                raise AggregationError(
                    "source candles must be in strictly increasing time order "
                    "with no duplicates"
                )
        return source_tf

    def _group(
        self, candles: Sequence[Candle], step: int
    ) -> List[tuple[datetime, List[Candle]]]:
        groups: List[tuple[datetime, List[Candle]]] = []
        current_start: Optional[datetime] = None
        current: List[Candle] = []
        for candle in candles:
            start = _bucket_start(candle.time_utc, step)
            if current_start is None or start != current_start:
                if current:
                    groups.append((current_start, current))
                current_start = start
                current = [candle]
            else:
                current.append(candle)
        if current:
            groups.append((current_start, current))
        return groups

    def _build_bar(
        self, start: datetime, group: List[Candle], target: Timeframe
    ) -> Candle:
        # group is already in chronological order (source was validated).
        first, last = group[0], group[-1]

        real_volumes = [c.real_volume for c in group]
        real_volume = (
            sum(real_volumes) if all(v is not None for v in real_volumes) else None
        )

        # Preserve the broker's UTC offset by re-expressing the aligned window
        # start in the source bars' timezone.
        source_tz = first.broker_time.tzinfo or UTC
        broker_time = start.astimezone(source_tz)

        return Candle(
            symbol=first.symbol,
            timeframe=target.value,
            broker_time=broker_time,
            time_utc=start,
            open=first.open,
            high=max(c.high for c in group),
            low=min(c.low for c in group),
            close=last.close,
            tick_volume=sum(c.tick_volume for c in group),
            real_volume=real_volume,
            spread=None,
        )

    def _drop_incomplete(
        self, bars: List[Candle], step: int, now: Optional[datetime]
    ) -> List[Candle]:
        if not bars:
            return bars
        if now is not None:
            # Keep only windows that have fully elapsed by `now`.
            return [
                b
                for b in bars
                if b.time_utc.timestamp() + step <= now.timestamp()
            ]
        # Without a reference time, the most recent window may still be forming.
        return bars[:-1]


def aggregate(
    candles: Sequence[Candle],
    target: Timeframe,
    *,
    now: Optional[datetime] = None,
    drop_incomplete: bool = True,
) -> List[Candle]:
    """Module-level convenience wrapper around TimeframeAggregator.aggregate."""
    return TimeframeAggregator().aggregate(
        candles, target, now=now, drop_incomplete=drop_incomplete
    )
