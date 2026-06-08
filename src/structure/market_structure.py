"""Swing & market-structure engine (Task P3-001).

Mechanically detects swing highs/lows, BOS (break of structure) and CHOCH
(change of character) from a Candle series. References 13_XAUUSD_SMC_PLAYBOOK.md
(structure must be detected mechanically, never assumed).

No look-ahead:
- A swing pivot at index i is a fractal extreme versus `strength` candles on each
  side, so it is only CONFIRMED at index i + strength. The engine never uses a
  swing before its confirmation index.
- BOS/CHOCH are decided from the close of the current candle breaking the most
  recent already-confirmed swing level. No future candle is consulted, so the
  result for any prefix of the series is stable.

Definitions (close-based breaks):
- Bullish break = close above the active (most recent confirmed) swing high.
- Bearish break = close below the active swing low.
- A break that continues the prevailing bias is a BOS; the first break against
  the prevailing bias is a CHOCH (and flips the bias). The very first break
  establishes the bias and is reported as BOS.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Sequence

from src.data.schemas import Candle


class SwingType(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class StructureEventType(str, Enum):
    BOS = "BOS"
    CHOCH = "CHOCH"


class Bias(str, Enum):
    NEUTRAL = "NEUTRAL"
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


@dataclass(frozen=True)
class SwingPoint:
    """A confirmed fractal swing high or low."""

    swing_type: SwingType
    index: int
    time_utc: datetime
    price: float
    confirmed_index: int  # candle index at which this swing becomes known


@dataclass(frozen=True)
class StructureEvent:
    """A detected BOS or CHOCH."""

    event_type: StructureEventType
    bias: Bias  # direction of the break (BULLISH or BEARISH)
    index: int  # candle index whose close produced the break
    time_utc: datetime
    price: float  # the broken swing level
    broken_swing: SwingPoint


@dataclass(frozen=True)
class StructureResult:
    """Full structure analysis of a candle series."""

    swings: tuple[SwingPoint, ...]
    events: tuple[StructureEvent, ...]
    final_bias: Bias


class MarketStructureEngine:
    """Detects swings and structure events with no look-ahead."""

    def __init__(self, strength: int = 2) -> None:
        if strength < 1:
            raise ValueError("strength must be >= 1")
        self._strength = strength

    # -- swing detection ---------------------------------------------------
    def find_swings(self, candles: Sequence[Candle]) -> List[SwingPoint]:
        """Return confirmed fractal swing points in confirmation order.

        A swing high at i has a strictly greater high than every candle within
        `strength` bars on both sides; a swing low mirrors with lows. Strict
        comparison means flat plateaus (equal highs/lows) produce no swing.
        """
        s = self._strength
        n = len(candles)
        swings: List[SwingPoint] = []
        for i in range(s, n - s):
            window = range(i - s, i + s + 1)
            hi = candles[i].high
            lo = candles[i].low
            if all(candles[j].high < hi for j in window if j != i):
                swings.append(
                    SwingPoint(SwingType.HIGH, i, candles[i].time_utc, hi, i + s)
                )
            if all(candles[j].low > lo for j in window if j != i):
                swings.append(
                    SwingPoint(SwingType.LOW, i, candles[i].time_utc, lo, i + s)
                )
        swings.sort(key=lambda sp: (sp.confirmed_index, sp.index))
        return swings

    # -- structure analysis ------------------------------------------------
    def analyze(self, candles: Sequence[Candle]) -> StructureResult:
        """Detect swings and the resulting BOS/CHOCH sequence."""
        swings = self.find_swings(candles)

        confirm_map: Dict[int, List[SwingPoint]] = {}
        for sp in swings:
            confirm_map.setdefault(sp.confirmed_index, []).append(sp)

        trend = Bias.NEUTRAL
        active_high: Optional[SwingPoint] = None
        active_low: Optional[SwingPoint] = None
        events: List[StructureEvent] = []

        for k in range(len(candles)):
            # 1) Confirm any swings whose right-side window completes at k.
            for sp in confirm_map.get(k, []):
                if sp.swing_type is SwingType.HIGH:
                    active_high = sp
                else:
                    active_low = sp

            # 2) Evaluate a close-based break of an active level.
            close = candles[k].close
            bullish_break = active_high is not None and close > active_high.price
            bearish_break = active_low is not None and close < active_low.price
            if bullish_break and bearish_break:
                # Degenerate opposite breaks: prefer continuation of the trend.
                if trend is Bias.BEARISH:
                    bullish_break = False
                else:
                    bearish_break = False

            if bullish_break:
                event_type = (
                    StructureEventType.CHOCH
                    if trend is Bias.BEARISH
                    else StructureEventType.BOS
                )
                events.append(
                    StructureEvent(
                        event_type,
                        Bias.BULLISH,
                        k,
                        candles[k].time_utc,
                        active_high.price,
                        active_high,
                    )
                )
                trend = Bias.BULLISH
                active_high = None  # consume the broken level
            elif bearish_break:
                event_type = (
                    StructureEventType.CHOCH
                    if trend is Bias.BULLISH
                    else StructureEventType.BOS
                )
                events.append(
                    StructureEvent(
                        event_type,
                        Bias.BEARISH,
                        k,
                        candles[k].time_utc,
                        active_low.price,
                        active_low,
                    )
                )
                trend = Bias.BEARISH
                active_low = None  # consume the broken level

        return StructureResult(
            swings=tuple(swings),
            events=tuple(events),
            final_bias=trend,
        )
