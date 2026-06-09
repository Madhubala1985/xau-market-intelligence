"""Gold futures confirmation layer (Task P5-002).

Adds optional gold-futures confirmation context for XAU/USD decisions. References
19_GOLD_FUTURES_CONFIRMATION_POLICY.md and decision INIT-006.

Rules enforced here:
- Spot XAU/USD is the execution instrument; futures is CONTEXT only.
- Futures may only adjust confidence / uncertainty (and downstream risk). It can
  NEVER trigger a trade by itself: FuturesConfirmation.is_trade_signal is always
  False, and there is no direction/signal/order field or decision method.
- Missing or insufficient futures data must NOT break the core system: the layer
  returns an UNAVAILABLE assessment with zero adjustment and a note.
- No look-ahead: futures bias is derived from the supplied futures candles using
  the prefix-stable structure engine (P3-001).

Confirmation logic: futures increases confidence only when its directional bias
ALIGNS with the spot thesis bias; an opposing futures bias reduces confidence and
increases uncertainty (policy Conflict Logic).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from src.data.schemas import Candle
from src.structure.market_structure import Bias, MarketStructureEngine


class FuturesAlignment(str, Enum):
    ALIGNED = "ALIGNED"
    CONFLICT = "CONFLICT"
    NEUTRAL = "NEUTRAL"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class FuturesConfirmation:
    """Gold-futures confirmation assessment. Confidence context only."""

    alignment: FuturesAlignment
    spot_bias: Bias
    futures_bias: Optional[Bias]  # None when unavailable/insufficient
    confidence_adjustment: float
    uncertainty_adjustment: float
    note: str
    # Futures can never trigger a trade (INIT-006 / policy Core Rule).
    is_trade_signal: bool = False


class FuturesConfirmationEngine:
    """Compares gold-futures bias to the spot thesis bias for confirmation."""

    def __init__(
        self,
        *,
        swing_strength: int = 2,
        min_candles: int = 6,
        step: float = 0.1,
        max_adjustment: float = 0.2,
    ) -> None:
        self._structure = MarketStructureEngine(strength=swing_strength)
        self._min_candles = min_candles
        self._step = step
        self._max = max_adjustment

    def confirm(
        self,
        spot_bias: Bias,
        futures_candles: Optional[Sequence[Candle]] = None,
    ) -> FuturesConfirmation:
        """Assess futures confirmation for a spot thesis bias.

        futures_candles may be None or too short; the layer degrades gracefully.
        """
        futures_bias = self._futures_bias(futures_candles)
        if futures_bias is None:
            return self._build(
                FuturesAlignment.UNAVAILABLE, spot_bias, None, 0.0, 0.0,
                "futures data unavailable; continuing with core XAU/USD logic",
            )

        # Futures only adds value when both sides have a direction.
        if spot_bias is Bias.NEUTRAL or futures_bias is Bias.NEUTRAL:
            return self._build(
                FuturesAlignment.NEUTRAL, spot_bias, futures_bias, 0.0, 0.0,
                "futures inconclusive; no confidence change",
            )

        if futures_bias is spot_bias:
            return self._build(
                FuturesAlignment.ALIGNED, spot_bias, futures_bias,
                self._clamp(self._step), 0.0,
                f"futures confirms {spot_bias.value.lower()} thesis (confidence up)",
            )

        # Opposing directions -> conflict.
        return self._build(
            FuturesAlignment.CONFLICT, spot_bias, futures_bias,
            self._clamp(-self._step), min(self._step, self._max),
            "futures conflicts with spot thesis (confidence down, uncertainty up)",
        )

    # -- internals ---------------------------------------------------------
    def _futures_bias(self, futures_candles: Optional[Sequence[Candle]]) -> Optional[Bias]:
        if not futures_candles or len(futures_candles) < self._min_candles:
            return None
        return self._structure.analyze(futures_candles).final_bias

    def _clamp(self, value: float) -> float:
        return max(-self._max, min(self._max, value))

    @staticmethod
    def _build(
        alignment: FuturesAlignment,
        spot_bias: Bias,
        futures_bias: Optional[Bias],
        confidence_adjustment: float,
        uncertainty_adjustment: float,
        note: str,
    ) -> FuturesConfirmation:
        return FuturesConfirmation(
            alignment=alignment,
            spot_bias=spot_bias,
            futures_bias=futures_bias,
            confidence_adjustment=confidence_adjustment,
            uncertainty_adjustment=uncertainty_adjustment,
            note=note,
        )
