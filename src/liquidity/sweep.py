"""Liquidity sweep engine (Task P3-003).

Detects liquidity sweeps against the resting-liquidity map (P3-002), per
15_LIQUIDITY_ENGINEERING.md. A valid sweep requires, mechanically:

1. a known liquidity level is taken (a wick pushes beyond it),
2. price fails to continue and closes back across the level (rejection),
3. displacement appears in the rejection direction,
4. market structure confirms in the rejection direction.

"A wick alone is not enough": steps 1-2 only form a CANDIDATE. Confirmation
(steps 3-4) upgrades it to a TRUE sweep; if the confirmation window elapses
without both, it is a FALSE sweep. A level that is taken but where price closes
through and continues is NOT a sweep (no candidate).

A sweep is not a trade by itself (15_LIQUIDITY_ENGINEERING.md final rule); this
engine only classifies.

No look-ahead:
- Only levels established strictly before the sweep candle are considered.
- A candidate is known at its sweep candle; it is only CONFIRMED at the later
  candle where displacement and structure both complete (confirmed_index).
- Until the confirmation window fully elapses, an unconfirmed candidate is
  PENDING rather than FALSE.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional, Sequence, Union

from src.data.schemas import Candle
from src.liquidity.liquidity_map import (
    LiquidityLevel,
    LiquidityMap,
    LiquiditySide,
)
from src.structure.market_structure import Bias, MarketStructureEngine


class SweepStatus(str, Enum):
    TRUE_SWEEP = "TRUE_SWEEP"
    FALSE_SWEEP = "FALSE_SWEEP"
    PENDING = "PENDING"


@dataclass(frozen=True)
class SweepEvent:
    """A detected liquidity-sweep candidate and its confirmation status."""

    level: LiquidityLevel
    swept_side: LiquiditySide
    rejection_bias: Bias
    sweep_index: int
    sweep_time: datetime
    status: SweepStatus
    displacement_index: Optional[int] = None
    structure_index: Optional[int] = None
    confirmed_index: Optional[int] = None


class SweepEngine:
    """Classifies liquidity sweeps against known levels."""

    def __init__(
        self,
        *,
        swing_strength: int = 2,
        rejection_ratio: float = 0.5,
        min_penetration: float = 0.0,
        displacement_factor: float = 1.5,
        displacement_lookback: int = 10,
        confirm_window: int = 3,
        require_displacement: bool = True,
        require_structure: bool = True,
    ) -> None:
        self._structure = MarketStructureEngine(strength=swing_strength)
        self._rejection_ratio = rejection_ratio
        self._min_penetration = min_penetration
        self._displacement_factor = displacement_factor
        self._displacement_lookback = displacement_lookback
        self._confirm_window = confirm_window
        self._require_displacement = require_displacement
        self._require_structure = require_structure

    def detect(
        self,
        candles: Sequence[Candle],
        levels: Union[LiquidityMap, Sequence[LiquidityLevel]],
    ) -> List[SweepEvent]:
        """Return sweep events (TRUE/FALSE/PENDING) for the given levels."""
        level_list = (
            list(levels.levels) if isinstance(levels, LiquidityMap) else list(levels)
        )
        if not candles or not level_list:
            return []

        structure_events = self._structure.analyze(candles).events
        n = len(candles)
        events: List[SweepEvent] = []
        consumed: set = set()

        for i, candle in enumerate(candles):
            for level in level_list:
                key = (level.kind, level.price, level.time_utc)
                if key in consumed:
                    continue
                # Only levels established before this candle (no look-ahead /
                # no self-reference).
                if level.time_utc >= candle.time_utc:
                    continue

                candidate = self._candidate(candle, level)
                if candidate is None:
                    continue

                consumed.add(key)
                rejection_bias = candidate
                event = self._confirm(
                    candles, i, level, rejection_bias, structure_events, n
                )
                events.append(event)
        return events

    # -- candidate detection ----------------------------------------------
    def _candidate(self, candle: Candle, level: LiquidityLevel) -> Optional[Bias]:
        """Return the rejection bias if (take-out + close-back) holds, else None."""
        rng = candle.high - candle.low
        if rng <= 0:
            return None

        if level.side is LiquiditySide.BUY_SIDE:
            took = candle.high > level.price + self._min_penetration
            closed_back = candle.close < level.price
            rejection = (candle.high - candle.close) / rng
            if took and closed_back and rejection >= self._rejection_ratio:
                return Bias.BEARISH  # swept highs -> bearish rejection
        else:  # SELL_SIDE
            took = candle.low < level.price - self._min_penetration
            closed_back = candle.close > level.price
            rejection = (candle.close - candle.low) / rng
            if took and closed_back and rejection >= self._rejection_ratio:
                return Bias.BULLISH  # swept lows -> bullish rejection
        return None

    # -- confirmation ------------------------------------------------------
    def _confirm(
        self,
        candles: Sequence[Candle],
        i: int,
        level: LiquidityLevel,
        rejection_bias: Bias,
        structure_events,
        n: int,
    ) -> SweepEvent:
        window_end = i + self._confirm_window
        baseline = self._baseline_range(candles, i)

        displacement_index: Optional[int] = None
        for j in range(i, min(window_end, n - 1) + 1):
            if self._is_displacement(candles[j], rejection_bias, baseline):
                displacement_index = j
                break

        structure_index: Optional[int] = None
        for ev in structure_events:
            if ev.bias is rejection_bias and i <= ev.index <= window_end:
                structure_index = ev.index
                break

        disp_ok = (not self._require_displacement) or displacement_index is not None
        struct_ok = (not self._require_structure) or structure_index is not None
        window_elapsed = window_end <= (n - 1)

        if disp_ok and struct_ok:
            status = SweepStatus.TRUE_SWEEP
            confirmed_index = max(
                idx for idx in (displacement_index, structure_index, i) if idx is not None
            )
        elif window_elapsed:
            status = SweepStatus.FALSE_SWEEP
            confirmed_index = None
        else:
            status = SweepStatus.PENDING
            confirmed_index = None

        return SweepEvent(
            level=level,
            swept_side=level.side,
            rejection_bias=rejection_bias,
            sweep_index=i,
            sweep_time=candles[i].time_utc,
            status=status,
            displacement_index=displacement_index,
            structure_index=structure_index,
            confirmed_index=confirmed_index,
        )

    def _baseline_range(self, candles: Sequence[Candle], i: int) -> float:
        start = max(0, i - self._displacement_lookback)
        prior = candles[start:i]
        if not prior:
            return candles[i].high - candles[i].low
        return sum(c.high - c.low for c in prior) / len(prior)

    def _is_displacement(self, candle: Candle, bias: Bias, baseline: float) -> bool:
        rng = candle.high - candle.low
        if rng <= 0:
            return False
        directional = (
            candle.close < candle.open
            if bias is Bias.BEARISH
            else candle.close > candle.open
        )
        return directional and rng >= self._displacement_factor * baseline
