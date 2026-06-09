"""Trailing stop engine (Task P8-002).

Implements structure-based, volatility-based, and liquidity-target trailing, plus
break-even and partial-profit / runner logic. References
17_STOP_AND_TRAILING_POLICY.md.

Hard invariants:
- A trailing stop may only move in the trade's favor (LONG: up, SHORT: down). It
  must NEVER widen (move away from price / loosen). If a proposed trail would
  widen or not improve, the current stop is kept unchanged.
- No premature trailing: trailing is inactive until profit reaches the
  confirmation threshold (default 1R). Break-even only after confirmation.
- A candidate stop on the wrong side of price is ignored.

No order placement; no look-ahead (only the supplied price/levels are used).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from src.data.enums import Direction


class TrailMethod(str, Enum):
    STRUCTURE = "STRUCTURE"
    VOLATILITY = "VOLATILITY"
    LIQUIDITY = "LIQUIDITY"
    BREAK_EVEN = "BREAK_EVEN"


@dataclass(frozen=True)
class PositionState:
    """State of an open position for trailing decisions."""

    direction: Direction
    entry_price: float
    initial_stop: float   # original stop (defines 1R)
    current_stop: float
    current_price: float
    atr: float = 0.0

    @property
    def initial_risk(self) -> float:
        return abs(self.entry_price - self.initial_stop)

    @property
    def profit(self) -> float:
        if self.direction is Direction.LONG:
            return self.current_price - self.entry_price
        return self.entry_price - self.current_price

    @property
    def profit_r(self) -> float:
        risk = self.initial_risk
        return self.profit / risk if risk > 0 else 0.0


@dataclass(frozen=True)
class TrailResult:
    """Outcome of a trailing update."""

    new_stop: float
    moved: bool
    method: Optional[TrailMethod]
    reason: str


@dataclass(frozen=True)
class RunnerConditions:
    structure_valid: bool = True
    opposite_displacement: bool = False
    spread_safe: bool = True


@dataclass(frozen=True)
class PartialPlan:
    """Partial-profit take levels and runner permission."""

    take_levels: Tuple[float, ...]
    runner_allowed: bool
    reason: str


class TrailingStopEngine:
    """Computes trailing-stop updates and partial/runner plans."""

    def __init__(
        self,
        *,
        atr_multiple: float = 1.0,
        buffer: float = 1.0,
        be_trigger_r: float = 1.0,
    ) -> None:
        if atr_multiple < 0 or buffer < 0 or be_trigger_r <= 0:
            raise ValueError("invalid trailing config")
        self._atr_multiple = atr_multiple
        self._buffer = buffer
        self._be_trigger_r = be_trigger_r

    # -- trailing ----------------------------------------------------------
    def update_stop(
        self,
        state: PositionState,
        method: TrailMethod,
        *,
        last_swing: Optional[float] = None,
        protect_level: Optional[float] = None,
    ) -> TrailResult:
        """Return an updated stop, or the unchanged stop if it must not move."""
        if state.direction not in (Direction.LONG, Direction.SHORT):
            raise ValueError("direction must be LONG or SHORT")

        # No premature trailing: require confirmation (profit >= trigger R).
        if state.initial_risk <= 0:
            return self._hold(state, method, "invalid initial risk; no trail")
        if state.profit_r < self._be_trigger_r:
            return self._hold(
                state, method,
                f"premature: profit {state.profit_r:.2f}R < trigger {self._be_trigger_r}R",
            )

        candidate = self._candidate(state, method, last_swing, protect_level)
        if candidate is None:
            return self._hold(state, method, "no candidate for method/inputs")

        # Candidate must be on the correct side of price.
        if state.direction is Direction.LONG and candidate >= state.current_price:
            return self._hold(state, method, "candidate not below price")
        if state.direction is Direction.SHORT and candidate <= state.current_price:
            return self._hold(state, method, "candidate not above price")

        # Never widen: only accept an improvement toward price.
        if state.direction is Direction.LONG and candidate <= state.current_stop:
            return self._hold(state, method, "would widen/not improve long stop")
        if state.direction is Direction.SHORT and candidate >= state.current_stop:
            return self._hold(state, method, "would widen/not improve short stop")

        return TrailResult(
            new_stop=round(candidate, 8),
            moved=True,
            method=method,
            reason=f"{method.value} trail to {round(candidate, 8)}",
        )

    def _candidate(
        self,
        state: PositionState,
        method: TrailMethod,
        last_swing: Optional[float],
        protect_level: Optional[float],
    ) -> Optional[float]:
        is_long = state.direction is Direction.LONG
        if method is TrailMethod.VOLATILITY:
            if state.atr <= 0:
                return None
            delta = state.atr * self._atr_multiple
            return state.current_price - delta if is_long else state.current_price + delta
        if method is TrailMethod.STRUCTURE:
            if last_swing is None:
                return None
            return last_swing - self._buffer if is_long else last_swing + self._buffer
        if method is TrailMethod.LIQUIDITY:
            if protect_level is None:
                return None
            return protect_level - self._buffer if is_long else protect_level + self._buffer
        # BREAK_EVEN
        return state.entry_price

    # -- partials / runner -------------------------------------------------
    def partial_plan(
        self,
        state: PositionState,
        *,
        next_liquidity: Optional[float] = None,
        conditions: Optional[RunnerConditions] = None,
    ) -> PartialPlan:
        """Partial-take levels (1R, next liquidity beyond it) and runner permission."""
        conditions = conditions or RunnerConditions()
        risk = state.initial_risk
        is_long = state.direction is Direction.LONG

        levels = []
        if risk > 0:
            one_r = state.entry_price + risk if is_long else state.entry_price - risk
            levels.append(round(one_r, 8))
            if next_liquidity is not None:
                beyond = next_liquidity > one_r if is_long else next_liquidity < one_r
                if beyond:
                    levels.append(round(next_liquidity, 8))

        runner_allowed = (
            conditions.structure_valid
            and not conditions.opposite_displacement
            and conditions.spread_safe
        )
        reason = (
            "runner allowed: structure valid, no opposite displacement, spread safe"
            if runner_allowed
            else "runner blocked: a runner condition failed"
        )
        return PartialPlan(
            take_levels=tuple(levels),
            runner_allowed=runner_allowed,
            reason=reason,
        )

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _hold(state: PositionState, method: TrailMethod, reason: str) -> TrailResult:
        return TrailResult(
            new_stop=state.current_stop, moved=False, method=method, reason=reason
        )
