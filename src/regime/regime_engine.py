"""Regime engine (Task P4-002).

Classifies the current XAU/USD market condition into one regime, from a candle
window. References 02_ARCHITECTURE.md section 10 and 10_TASK_QUEUE.md P4-002.

Regimes:
- TREND: clear directional structure (consistent BOS, no direction flips).
- CHOPPY: conflicting structure (alternating BOS/CHOCH, multiple flips).
- EXPANSION: volatility widening (recent ranges much larger than earlier).
- COMPRESSION: volatility contracting (recent ranges much smaller).
- RANGE: bounded, no structural breaks, stable volatility.
- NEWS_RISK: an external news-risk flag is set (safety override).
- NO_TRADE: insufficient data or otherwise unclear.

Inputs reuse the P3-001 structure engine (BOS/CHOCH events and direction flips)
and candle-range statistics. No look-ahead: structure is prefix-stable and
volatility uses only the supplied window.

Classification is priority-ordered so each window maps to exactly one regime:
data -> news -> choppy -> trend -> expansion -> compression -> range -> no-trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Sequence

from src.data.schemas import Candle
from src.structure.market_structure import (
    Bias,
    MarketStructureEngine,
    StructureEventType,
)


class Regime(str, Enum):
    TREND = "TREND"
    RANGE = "RANGE"
    COMPRESSION = "COMPRESSION"
    EXPANSION = "EXPANSION"
    CHOPPY = "CHOPPY"
    NEWS_RISK = "NEWS_RISK"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True)
class RegimeResult:
    """Regime classification with the features that produced it."""

    regime: Regime
    final_bias: Bias
    bos_count: int
    choch_count: int
    flips: int
    volatility_ratio: float
    reason: str


class RegimeEngine:
    """Classifies market regime from a candle window."""

    def __init__(
        self,
        *,
        swing_strength: int = 2,
        min_candles: int = 6,
        expansion_factor: float = 1.5,
        compression_factor: float = 0.67,
        choppy_flips: int = 2,
    ) -> None:
        self._structure = MarketStructureEngine(strength=swing_strength)
        self._min_candles = min_candles
        self._expansion_factor = expansion_factor
        self._compression_factor = compression_factor
        self._choppy_flips = choppy_flips

    def classify(
        self,
        candles: Sequence[Candle],
        *,
        news_risk: bool = False,
    ) -> RegimeResult:
        if len(candles) < self._min_candles:
            return self._result(
                Regime.NO_TRADE, Bias.NEUTRAL, 0, 0, 0, 1.0,
                "insufficient data for regime classification",
            )

        result = self._structure.analyze(candles)
        biases = [e.bias for e in result.events]
        bos_count = sum(
            1 for e in result.events if e.event_type is StructureEventType.BOS
        )
        choch_count = sum(
            1 for e in result.events if e.event_type is StructureEventType.CHOCH
        )
        flips = sum(1 for a, b in zip(biases, biases[1:]) if a is not b)
        ratio = self._volatility_ratio(candles)

        regime, reason = self._decide(
            news_risk=news_risk,
            events=len(result.events),
            final_bias=result.final_bias,
            bos_count=bos_count,
            flips=flips,
            ratio=ratio,
        )
        return self._result(
            regime, result.final_bias, bos_count, choch_count, flips, ratio, reason
        )

    # -- decision ----------------------------------------------------------
    def _decide(
        self,
        *,
        news_risk: bool,
        events: int,
        final_bias: Bias,
        bos_count: int,
        flips: int,
        ratio: float,
    ) -> tuple[Regime, str]:
        if news_risk:
            return Regime.NEWS_RISK, "external news-risk flag set"
        if flips >= self._choppy_flips:
            return Regime.CHOPPY, f"{flips} structure direction flips"
        if events and flips == 0 and bos_count >= 1 and final_bias is not Bias.NEUTRAL:
            return Regime.TREND, f"consistent {final_bias.value.lower()} structure"
        if ratio >= self._expansion_factor:
            return Regime.EXPANSION, f"volatility expanding (ratio {ratio:.2f})"
        if ratio <= self._compression_factor:
            return Regime.COMPRESSION, f"volatility contracting (ratio {ratio:.2f})"
        if events == 0:
            return Regime.RANGE, "no structural breaks, stable volatility"
        return Regime.NO_TRADE, "structure unclear"

    # -- features ----------------------------------------------------------
    def _volatility_ratio(self, candles: Sequence[Candle]) -> float:
        ranges: List[float] = [c.high - c.low for c in candles]
        mid = len(ranges) // 2
        first, second = ranges[:mid], ranges[mid:]
        avg_first = sum(first) / len(first) if first else 0.0
        avg_second = sum(second) / len(second) if second else 0.0
        if avg_first <= 0:
            return 1.0
        return avg_second / avg_first

    @staticmethod
    def _result(
        regime: Regime,
        final_bias: Bias,
        bos_count: int,
        choch_count: int,
        flips: int,
        ratio: float,
        reason: str,
    ) -> RegimeResult:
        return RegimeResult(
            regime=regime,
            final_bias=final_bias,
            bos_count=bos_count,
            choch_count=choch_count,
            flips=flips,
            volatility_ratio=ratio,
            reason=reason,
        )
