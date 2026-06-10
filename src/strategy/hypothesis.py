"""Trade hypothesis engine (Task P6-001).

Generates LONG / SHORT / WAIT / NO_TRADE hypotheses as TradeDecision objects from
the higher-level analysis context, per 13_XAUUSD_SMC_PLAYBOOK.md ("Valid Trade
Hypothesis").

Hard rules (P6-001 / playbook): no thesis = no trade; no invalidation = no trade.
An actionable LONG/SHORT is only produced when there is HTF directional bias, a
tradeable regime, a non-empty thesis (liquidity/structure evidence), and an
invalidation level on the correct side of entry. Otherwise the engine returns a
WAIT or NO_TRADE hypothesis -- it never fabricates an actionable trade.

Hypotheses are proposals only (status PROPOSED); the Risk Governor (P7) decides
permission. No look-ahead: the engine only composes already-computed context.

The actionable invariants are also enforced structurally by the TradeDecision
schema (src/data/schemas.py): it rejects a LONG/SHORT without thesis +
invalidation, and a stop on the wrong side of entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.data.enums import DecisionStatus, Direction
from src.data.schemas import TradeDecision
from src.regime.htf_bias import HtfBias
from src.regime.regime_engine import Regime

# Regimes that ALWAYS block a new trade hypothesis: data/news safety gates.
_ALWAYS_BLOCKING_REGIMES = frozenset({Regime.NO_TRADE, Regime.NEWS_RISK})


@dataclass(frozen=True)
class HypothesisInput:
    """Composed analysis context for one hypothesis decision."""

    symbol: str
    time_utc: datetime
    current_price: float
    htf_bias: HtfBias
    regime: Regime
    # Evidence and levels (populated from the analysis stack):
    thesis_reason: Optional[str] = None       # liquidity/structure evidence text
    invalidation_price: Optional[float] = None
    entry_price: Optional[float] = None        # defaults to current_price
    target_price: Optional[float] = None       # explicit liquidity target
    setup_type: Optional[str] = None
    confidence: float = 0.5
    uncertainty: float = 0.3
    # Graded regime gate (INTELLIGENCE-001): CHOPPY is no longer a blind hard
    # block. The pipeline decomposes chop into subtypes and may set this True
    # ONLY when the subtype is tradeable AND confluence is strong. None keeps
    # the conservative default (CHOPPY blocks). NO_TRADE / NEWS_RISK regimes
    # block regardless of this flag — it cannot weaken the safety gates.
    regime_allows: Optional[bool] = None
    regime_detail: str = ""


class TradeHypothesisEngine:
    """Builds a TradeDecision hypothesis from analysis context."""

    def __init__(self, *, default_rr: float = 2.0) -> None:
        if default_rr <= 0:
            raise ValueError("default_rr must be > 0")
        self._default_rr = default_rr

    def generate(self, inp: HypothesisInput) -> TradeDecision:
        # 1) Gates that block any directional hypothesis.
        if inp.htf_bias is HtfBias.NO_TRADE:
            return self._terminal(inp, Direction.NO_TRADE, "HTF bias is NO_TRADE")
        if inp.regime in _ALWAYS_BLOCKING_REGIMES:
            # Safety gates: never overridable, regardless of confluence.
            return self._terminal(
                inp, Direction.NO_TRADE, f"regime {inp.regime.value} blocks new trades"
            )
        if inp.regime is Regime.CHOPPY and inp.regime_allows is not True:
            detail = f" ({inp.regime_detail})" if inp.regime_detail else ""
            return self._terminal(
                inp, Direction.NO_TRADE,
                f"regime CHOPPY blocks new trades{detail}",
            )
        if inp.htf_bias is HtfBias.NEUTRAL:
            return self._terminal(inp, Direction.WAIT, "HTF bias neutral; wait")

        direction = (
            Direction.LONG if inp.htf_bias is HtfBias.BULLISH else Direction.SHORT
        )

        # 2) No thesis = no trade.
        if not (inp.thesis_reason and inp.thesis_reason.strip()):
            return self._terminal(
                inp, Direction.NO_TRADE, "no liquidity/structure evidence; no thesis"
            )

        # 3) No invalidation = no trade.
        if inp.invalidation_price is None:
            return self._terminal(
                inp, Direction.NO_TRADE, "no invalidation level; no trade"
            )

        entry = inp.entry_price if inp.entry_price is not None else inp.current_price
        invalidation = inp.invalidation_price

        # 4) Invalidation must sit on the correct side of entry.
        if not self._invalidation_valid(direction, entry, invalidation):
            return self._terminal(
                inp, Direction.NO_TRADE, "invalidation on wrong side of entry; no trade"
            )

        thesis = (
            f"{inp.htf_bias.value} bias in {inp.regime.value} regime: "
            f"{inp.thesis_reason.strip()}"
        )
        take_profits = self._targets(direction, entry, invalidation, inp.target_price)

        return TradeDecision(
            decision_id=self._decision_id(inp),
            time_utc=inp.time_utc,
            symbol=inp.symbol,
            direction=direction,
            status=DecisionStatus.PROPOSED,
            setup_type=inp.setup_type,
            thesis=thesis,
            invalidation_price=invalidation,
            entry_price=entry,
            stop_loss=invalidation,  # stop at the invalidation level (correct side)
            take_profits=take_profits,
            confidence=inp.confidence,
            uncertainty=inp.uncertainty,
            reason=inp.thesis_reason.strip(),
        )

    # -- internals ---------------------------------------------------------
    @staticmethod
    def _invalidation_valid(
        direction: Direction, entry: float, invalidation: float
    ) -> bool:
        if direction is Direction.LONG:
            return invalidation < entry
        return invalidation > entry

    def _targets(
        self,
        direction: Direction,
        entry: float,
        invalidation: float,
        target_price: Optional[float],
    ) -> tuple[float, ...]:
        # Prefer an explicit liquidity target when it sits in the trade direction.
        if target_price is not None:
            if direction is Direction.LONG and target_price > entry:
                return (target_price,)
            if direction is Direction.SHORT and target_price < entry:
                return (target_price,)
        # Otherwise derive a default risk-reward target.
        risk = abs(entry - invalidation)
        if risk <= 0:
            return ()
        if direction is Direction.LONG:
            return (entry + self._default_rr * risk,)
        return (entry - self._default_rr * risk,)

    @staticmethod
    def _decision_id(inp: HypothesisInput) -> str:
        return f"{inp.symbol}-{int(inp.time_utc.timestamp())}"

    def _terminal(
        self, inp: HypothesisInput, direction: Direction, reason: str
    ) -> TradeDecision:
        """A WAIT or NO_TRADE hypothesis (no thesis/invalidation required)."""
        status = (
            DecisionStatus.NO_TRADE
            if direction is Direction.NO_TRADE
            else DecisionStatus.PROPOSED
        )
        return TradeDecision(
            decision_id=self._decision_id(inp),
            time_utc=inp.time_utc,
            symbol=inp.symbol,
            direction=direction,
            status=status,
            reason=reason,
        )
