"""Daily and 4H bias engine (Task P4-001).

Classifies higher-timeframe (HTF) directional bias as BULLISH, BEARISH, NEUTRAL,
or NO_TRADE, from Daily and 4H candle series. References 02_ARCHITECTURE.md
section 4 (Daily + 4H Bias Engine).

Method:
- Each timeframe's directional bias is the market-structure bias (P3-001
  final_bias, the trend after the latest BOS/CHOCH).
- Daily is the primary authority; 4H confirms it.
- Daily and 4H in conflict, or missing Daily data, yield NO_TRADE (the HTF
  context is unsafe/ambiguous). Daily neutral yields NEUTRAL.

No look-ahead: market-structure bias is prefix-stable (confirmed swings,
close-based breaks), so the classification depends only on the candles supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from src.data.schemas import Candle
from src.structure.market_structure import Bias, MarketStructureEngine


class HtfBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True)
class BiasResult:
    """HTF bias classification with its component biases and a reason."""

    bias: HtfBias
    daily_bias: Optional[Bias]  # None == insufficient daily data
    h4_bias: Optional[Bias]     # None == insufficient 4H data
    reason: str


class HtfBiasEngine:
    """Combines Daily and 4H structure bias into an overall HTF bias."""

    def __init__(self, swing_strength: int = 2) -> None:
        self._structure = MarketStructureEngine(strength=swing_strength)

    def classify(
        self,
        daily_candles: Sequence[Candle],
        h4_candles: Sequence[Candle],
    ) -> BiasResult:
        daily_bias = self._timeframe_bias(daily_candles)
        h4_bias = self._timeframe_bias(h4_candles)
        bias, reason = self._combine(daily_bias, h4_bias)
        return BiasResult(
            bias=bias,
            daily_bias=daily_bias,
            h4_bias=h4_bias,
            reason=reason,
        )

    # -- internals ---------------------------------------------------------
    def _timeframe_bias(self, candles: Sequence[Candle]) -> Optional[Bias]:
        """Structure bias for a timeframe; None when there is no data."""
        if not candles:
            return None
        return self._structure.analyze(candles).final_bias

    def _combine(
        self, daily: Optional[Bias], h4: Optional[Bias]
    ) -> tuple[HtfBias, str]:
        if daily is None:
            return HtfBias.NO_TRADE, "insufficient daily data"

        if daily is Bias.NEUTRAL:
            return HtfBias.NEUTRAL, "daily structure is neutral"

        if daily is Bias.BULLISH:
            if h4 is Bias.BEARISH:
                return HtfBias.NO_TRADE, "daily bullish but 4H bearish (conflict)"
            confirm = "confirmed by 4H" if h4 is Bias.BULLISH else "4H not opposing"
            return HtfBias.BULLISH, f"daily bullish, {confirm}"

        # daily is BEARISH
        if h4 is Bias.BULLISH:
            return HtfBias.NO_TRADE, "daily bearish but 4H bullish (conflict)"
        confirm = "confirmed by 4H" if h4 is Bias.BEARISH else "4H not opposing"
        return HtfBias.BEARISH, f"daily bearish, {confirm}"
