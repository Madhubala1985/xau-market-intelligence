"""Shared mechanical primitives for setups.

These mirror the definitions used by the existing engines (ZoneEngine.find_fvgs,
the displacement notion in SweepEngine/ZoneEngine) but operate on explicit
candle indices so each setup keeps tight, auditable control over causality.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from src.data.schemas import Candle


def utc_day(c: Candle) -> date:
    return c.time_utc.astimezone(timezone.utc).date()


def utc_hour(c: Candle) -> int:
    return c.time_utc.astimezone(timezone.utc).hour


def day_midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def group_by_day(candles: Sequence[Candle]) -> Dict[date, List[int]]:
    """Map each UTC day to the global indices of its candles (in order)."""
    out: Dict[date, List[int]] = {}
    for i, c in enumerate(candles):
        out.setdefault(utc_day(c), []).append(i)
    return out


def window_indices(candles: Sequence[Candle], idxs: Sequence[int],
                   start_h: int, end_h: int) -> List[int]:
    """Indices (from idxs) whose UTC hour is in [start_h, end_h)."""
    return [i for i in idxs if start_h <= utc_hour(candles[i]) < end_h]


def range_of(candles: Sequence[Candle], idxs: Sequence[int]) -> Tuple[float, float]:
    """(low, high) over the given indices."""
    return (min(candles[i].low for i in idxs), max(candles[i].high for i in idxs))


def baseline_range(candles: Sequence[Candle], idx: int, lookback: int) -> Optional[float]:
    """Average true-ish range of the `lookback` bars before idx (None if too few)."""
    lo = max(0, idx - lookback)
    window = candles[lo:idx]
    if len(window) < max(3, lookback // 2):
        return None
    return sum(c.high - c.low for c in window) / len(window)


def is_bull_displacement(c: Candle, baseline: float, factor: float) -> bool:
    return c.close > c.open and (c.high - c.low) >= factor * baseline


def is_bear_displacement(c: Candle, baseline: float, factor: float) -> bool:
    return c.close < c.open and (c.high - c.low) >= factor * baseline


def bull_fvg(candles: Sequence[Candle], i: int, min_gap: float = 0.0) -> Optional[Tuple[float, float]]:
    """Bullish 3-candle FVG centred on i -> (bottom, top); None if no gap.

    Gap = candles[i+1].low - candles[i-1].high > min_gap.
    """
    if i - 1 < 0 or i + 1 >= len(candles):
        return None
    prev, nxt = candles[i - 1], candles[i + 1]
    if nxt.low - prev.high > min_gap:
        return (prev.high, nxt.low)
    return None


def bear_fvg(candles: Sequence[Candle], i: int, min_gap: float = 0.0) -> Optional[Tuple[float, float]]:
    """Bearish 3-candle FVG centred on i -> (bottom, top); None if no gap.

    Gap = candles[i-1].low - candles[i+1].high > min_gap. Returned bottom<top.
    """
    if i - 1 < 0 or i + 1 >= len(candles):
        return None
    prev, nxt = candles[i - 1], candles[i + 1]
    if prev.low - nxt.high > min_gap:
        return (nxt.high, prev.low)
    return None
