"""Open-position protection manager (Audit F-4; 17_STOP_AND_TRAILING_POLICY.md).

Computes stop-protection PROPOSALS for open positions using the existing
TrailingStopEngine: break-even protection once the trade has earned it, then
structure/volatility trailing. This module performs NO MT5 calls — it returns
proposals; applying them is the (separately gated) supervised demo session's
job, through the ExecutionGateway pathway only.

Hard properties (inherited from TrailingStopEngine and asserted by tests):
- a stop is NEVER widened,
- no premature trailing (profit must reach the trigger R first),
- proposals require a known current stop; a position without a stop-loss is
  reported as a protection violation (stop-loss is mandatory).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from src.broker.mt5_data_adapter import BrokerPosition
from src.data.enums import Direction
from src.trade_management.trailing import (
    PositionState,
    TrailMethod,
    TrailingStopEngine,
)


@dataclass(frozen=True)
class StopProposal:
    """A proposed stop update for one open position (no order is sent here)."""

    ticket: int
    symbol: str
    current_stop: Optional[float]
    proposed_stop: Optional[float]
    should_update: bool
    method: Optional[str]
    reason: str
    violation: bool = False  # True == position breaks a hard rule (e.g. no SL)


class PositionProtectionManager:
    """Derives break-even / trailing proposals for open broker positions."""

    def __init__(self, engine: Optional[TrailingStopEngine] = None) -> None:
        self._engine = engine or TrailingStopEngine()

    def propose(
        self,
        position: BrokerPosition,
        *,
        atr: float = 0.0,
        last_swing: Optional[float] = None,
        initial_stop: Optional[float] = None,
    ) -> StopProposal:
        """Propose a protection update for one position.

        `initial_stop` is the ORIGINAL stop from the journaled trade record
        (linked via reconciliation); it defines 1R for trail triggers. Without
        it the current broker stop is used, which is conservative — and once
        the stop reaches break-even, further trailing requires the journal's
        original stop to compute R.
        """
        # Stop-loss mandatory: an open position without one is a violation
        # that the supervised session must surface immediately.
        if position.stop_loss is None:
            return StopProposal(
                ticket=position.ticket,
                symbol=position.symbol,
                current_stop=None,
                proposed_stop=None,
                should_update=False,
                method=None,
                reason="VIOLATION: open position has no stop-loss",
                violation=True,
            )
        if position.current_price is None:
            return StopProposal(
                ticket=position.ticket,
                symbol=position.symbol,
                current_stop=position.stop_loss,
                proposed_stop=None,
                should_update=False,
                method=None,
                reason="no current price available; holding stop",
            )

        state = PositionState(
            direction=Direction(position.direction),
            entry_price=position.entry_price,
            # Prefer the journaled ORIGINAL stop (defines 1R); fall back to
            # the current broker stop, which is conservative (never premature).
            initial_stop=initial_stop if initial_stop is not None else position.stop_loss,
            current_stop=position.stop_loss,
            current_price=position.current_price,
            atr=atr,
        )

        # Preference order: break-even protection first, then structure,
        # then volatility trailing. First proposal that moves the stop wins.
        attempts = [
            (TrailMethod.BREAK_EVEN, dict(protect_level=position.entry_price)),
            (TrailMethod.STRUCTURE, dict(last_swing=last_swing)),
            (TrailMethod.VOLATILITY, {}),
        ]
        for method, kwargs in attempts:
            result = self._engine.update_stop(state, method, **kwargs)
            if result.moved:
                return StopProposal(
                    ticket=position.ticket,
                    symbol=position.symbol,
                    current_stop=position.stop_loss,
                    proposed_stop=result.new_stop,
                    should_update=True,
                    method=method.value,
                    reason=result.reason,
                )

        return StopProposal(
            ticket=position.ticket,
            symbol=position.symbol,
            current_stop=position.stop_loss,
            proposed_stop=None,
            should_update=False,
            method=None,
            reason="no protection update earned yet; holding stop",
        )

    def propose_all(
        self,
        positions: Sequence[BrokerPosition],
        *,
        atr: float = 0.0,
        last_swing: Optional[float] = None,
        initial_stops: Optional[dict] = None,  # ticket -> original stop
    ) -> Tuple[StopProposal, ...]:
        stops = initial_stops or {}
        return tuple(
            self.propose(p, atr=atr, last_swing=last_swing,
                         initial_stop=stops.get(p.ticket))
            for p in positions
        )
