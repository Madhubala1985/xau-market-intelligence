"""Stop placement intelligence (Task P8-001).

Places a stop-loss BEYOND the thesis invalidation using a volatility (ATR) and
liquidity buffer, and evaluates whether a proposed stop is logical or "obvious"
(parked on the level/pool where retail stops cluster). References
17_STOP_AND_TRAILING_POLICY.md.

Scope: stop PLACEMENT only. Trailing is P8-002. This module never places orders
and never widens a stop after entry; it only computes/validates a stop level.

Principles enforced:
- The stop must sit beyond the invalidation by at least a clearance =
  max(atr * atr_multiple, min_buffer); a stop on/too near the invalidation or a
  liquidity pool is rejected as OBVIOUS.
- A stop closer to entry than the broker minimum / min buffer is rejected as
  TOO_TIGHT (no fear-based tight stops).
- A stop on the wrong side of entry, or not beyond the invalidation, is rejected.
No look-ahead: only the supplied levels are used.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Tuple

from src.data.enums import Direction
from src.data.schemas import TradeDecision


class StopVerdict(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED_OBVIOUS = "REJECTED_OBVIOUS"
    REJECTED_TOO_TIGHT = "REJECTED_TOO_TIGHT"
    REJECTED_WRONG_SIDE = "REJECTED_WRONG_SIDE"
    REJECTED_NOT_BEYOND_INVALIDATION = "REJECTED_NOT_BEYOND_INVALIDATION"


@dataclass(frozen=True)
class StopPlacement:
    """A computed stop level."""

    stop_price: float
    distance: float   # |entry - stop|
    buffer: float     # clearance beyond the invalidation (+spread)
    reason: str


@dataclass(frozen=True)
class StopEvaluation:
    """Verdict for a proposed stop."""

    verdict: StopVerdict
    reason: str

    @property
    def accepted(self) -> bool:
        return self.verdict is StopVerdict.ACCEPTED


class StopPlacementEngine:
    """Computes and validates logical stop-loss levels."""

    def __init__(
        self,
        *,
        atr_multiple: float = 0.5,
        min_buffer: float = 1.0,
        broker_min_stop: float = 0.0,
    ) -> None:
        if atr_multiple < 0 or min_buffer < 0 or broker_min_stop < 0:
            raise ValueError("atr_multiple, min_buffer, broker_min_stop must be >= 0")
        self._atr_multiple = atr_multiple
        self._min_buffer = min_buffer
        self._broker_min_stop = broker_min_stop

    def clearance(self, atr: float) -> float:
        """Required distance beyond the invalidation level."""
        return max(atr * self._atr_multiple, self._min_buffer)

    # -- placement ---------------------------------------------------------
    def place(
        self,
        direction: Direction,
        entry_price: float,
        invalidation_price: float,
        *,
        atr: float = 0.0,
        spread: float = 0.0,
        liquidity_levels: Sequence[float] = (),
    ) -> StopPlacement:
        """Compute a stop beyond the invalidation with volatility/liquidity buffer."""
        if direction not in (Direction.LONG, Direction.SHORT):
            raise ValueError("direction must be LONG or SHORT")
        if spread < 0:
            raise ValueError("spread must be >= 0")
        self._require_valid_invalidation(direction, entry_price, invalidation_price)

        clearance = self.clearance(atr)
        buffer = clearance + spread

        if direction is Direction.LONG:
            stop = min(invalidation_price - buffer, entry_price - self._broker_min_stop)
            for level in sorted(liquidity_levels, reverse=True):
                if abs(stop - level) < clearance:
                    stop = min(stop, level - clearance)
        else:  # SHORT
            stop = max(invalidation_price + buffer, entry_price + self._broker_min_stop)
            for level in sorted(liquidity_levels):
                if abs(stop - level) < clearance:
                    stop = max(stop, level + clearance)

        return StopPlacement(
            stop_price=round(stop, 8),
            distance=round(abs(entry_price - stop), 8),
            buffer=round(buffer, 8),
            reason=(
                f"stop beyond invalidation by clearance {clearance} (+spread {spread}), "
                "clear of liquidity pools"
            ),
        )

    # -- evaluation --------------------------------------------------------
    def evaluate(
        self,
        direction: Direction,
        entry_price: float,
        invalidation_price: float,
        proposed_stop: float,
        *,
        atr: float = 0.0,
        liquidity_levels: Sequence[float] = (),
    ) -> StopEvaluation:
        """Classify a proposed stop as logical (ACCEPTED) or rejected."""
        if direction not in (Direction.LONG, Direction.SHORT):
            raise ValueError("direction must be LONG or SHORT")

        clearance = self.clearance(atr)
        min_distance = max(self._broker_min_stop, self._min_buffer)
        distance = abs(entry_price - proposed_stop)

        if direction is Direction.LONG:
            if proposed_stop >= entry_price:
                return self._reject(StopVerdict.REJECTED_WRONG_SIDE, "long stop must be below entry")
            if proposed_stop > invalidation_price:
                return self._reject(
                    StopVerdict.REJECTED_NOT_BEYOND_INVALIDATION,
                    "long stop must be below the invalidation level",
                )
            if invalidation_price - proposed_stop < clearance:
                return self._reject(
                    StopVerdict.REJECTED_OBVIOUS,
                    "stop sits on/too near the invalidation level (no buffer)",
                )
        else:  # SHORT
            if proposed_stop <= entry_price:
                return self._reject(StopVerdict.REJECTED_WRONG_SIDE, "short stop must be above entry")
            if proposed_stop < invalidation_price:
                return self._reject(
                    StopVerdict.REJECTED_NOT_BEYOND_INVALIDATION,
                    "short stop must be above the invalidation level",
                )
            if proposed_stop - invalidation_price < clearance:
                return self._reject(
                    StopVerdict.REJECTED_OBVIOUS,
                    "stop sits on/too near the invalidation level (no buffer)",
                )

        if any(abs(proposed_stop - level) < clearance for level in liquidity_levels):
            return self._reject(
                StopVerdict.REJECTED_OBVIOUS,
                "stop sits on an obvious liquidity pool",
            )
        if distance < min_distance:
            return self._reject(
                StopVerdict.REJECTED_TOO_TIGHT,
                f"stop distance {distance} below minimum {min_distance}",
            )
        return StopEvaluation(StopVerdict.ACCEPTED, "stop is beyond invalidation with buffer")

    # -- TradeDecision convenience ----------------------------------------
    def place_for_decision(
        self,
        decision: TradeDecision,
        *,
        atr: float = 0.0,
        spread: float = 0.0,
        liquidity_levels: Sequence[float] = (),
    ) -> StopPlacement:
        entry, invalidation = self._decision_levels(decision)
        return self.place(
            decision.direction, entry, invalidation,
            atr=atr, spread=spread, liquidity_levels=liquidity_levels,
        )

    def evaluate_decision(
        self,
        decision: TradeDecision,
        *,
        atr: float = 0.0,
        liquidity_levels: Sequence[float] = (),
    ) -> StopEvaluation:
        entry, invalidation = self._decision_levels(decision)
        if decision.stop_loss is None:
            raise ValueError("decision has no stop_loss to evaluate")
        return self.evaluate(
            decision.direction, entry, invalidation, decision.stop_loss,
            atr=atr, liquidity_levels=liquidity_levels,
        )

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _decision_levels(decision: TradeDecision) -> Tuple[float, float]:
        if decision.entry_price is None or decision.invalidation_price is None:
            raise ValueError("decision must have entry_price and invalidation_price")
        return decision.entry_price, decision.invalidation_price

    @staticmethod
    def _require_valid_invalidation(
        direction: Direction, entry: float, invalidation: float
    ) -> None:
        if direction is Direction.LONG and invalidation >= entry:
            raise ValueError("LONG invalidation must be below entry")
        if direction is Direction.SHORT and invalidation <= entry:
            raise ValueError("SHORT invalidation must be above entry")

    @staticmethod
    def _reject(verdict: StopVerdict, reason: str) -> StopEvaluation:
        return StopEvaluation(verdict, reason)
