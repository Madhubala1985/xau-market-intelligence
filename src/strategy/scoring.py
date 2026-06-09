"""Confidence and uncertainty engine (Task P6-002).

Aggregates component scores into an overall confidence and uncertainty, and
recommends ALLOW / REDUCE / BLOCK sizing. References 02_ARCHITECTURE.md
section 12 and 10_TASK_QUEUE.md P6-002.

Hard rules (P6-002 / architecture):
- High uncertainty must block or reduce a trade.
- Confidence alone can NEVER bypass risk: this engine produces an eligibility
  recommendation only. The result always carries authorizes_trade = False and
  risk_governor_required = True; the Risk Governor (P7) has final authority.

Components scored in [0, 1]: structure, liquidity, regime, volatility, session,
execution quality. Order-flow proxy (P5-001) and futures confirmation (P5-002)
contribute via their bounded confidence/uncertainty adjustments. No look-ahead:
the engine only aggregates already-computed scores.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import Optional

from src.orderflow.futures_confirmation import FuturesConfirmation
from src.orderflow.proxy import OrderFlowProxy


class ScoreRecommendation(str, Enum):
    """Eligibility recommendation. NOT a trade authorization."""

    ALLOW = "ALLOW"
    REDUCE = "REDUCE"
    BLOCK = "BLOCK"


def _check_unit(value: float, name: str) -> float:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value}")
    return value


@dataclass(frozen=True)
class ComponentScores:
    """Per-component support scores in [0, 1] (1 = strong/clean support)."""

    structure: float
    liquidity: float
    regime: float
    volatility: float
    session: float
    execution_quality: float

    def __post_init__(self) -> None:
        for f in fields(self):
            _check_unit(getattr(self, f.name), f.name)

    def values(self) -> list[float]:
        return [getattr(self, f.name) for f in fields(self)]


@dataclass(frozen=True)
class ConfidenceResult:
    """Confidence/uncertainty assessment and an eligibility recommendation."""

    confidence: float
    uncertainty: float
    recommendation: ScoreRecommendation
    size_factor: float
    reason: str
    # Scoring can never authorize a trade or bypass risk (P6-002 / risk policy).
    authorizes_trade: bool = False
    risk_governor_required: bool = True


class ConfidenceEngine:
    """Scores confidence/uncertainty and recommends ALLOW/REDUCE/BLOCK sizing."""

    def __init__(
        self,
        *,
        block_uncertainty: float = 0.7,
        reduce_uncertainty: float = 0.4,
        min_confidence: float = 0.3,
        reduce_factor: float = 0.5,
    ) -> None:
        self._block_uncertainty = block_uncertainty
        self._reduce_uncertainty = reduce_uncertainty
        self._min_confidence = min_confidence
        self._reduce_factor = reduce_factor

    def score(
        self,
        components: ComponentScores,
        proxy: Optional[OrderFlowProxy] = None,
        futures: Optional[FuturesConfirmation] = None,
    ) -> ConfidenceResult:
        values = components.values()
        mean = sum(values) / len(values)
        spread = max(values) - min(values)  # disagreement among components

        conf_adj = (proxy.confidence_adjustment if proxy else 0.0) + (
            futures.confidence_adjustment if futures else 0.0
        )
        unc_adj = (proxy.uncertainty_adjustment if proxy else 0.0) + (
            futures.uncertainty_adjustment if futures else 0.0
        )

        confidence = self._clamp(mean + conf_adj)
        # Uncertainty rises with low support and with component disagreement.
        base_uncertainty = (1.0 - mean) * 0.5 + spread * 0.5
        uncertainty = self._clamp(base_uncertainty + unc_adj)

        recommendation, size_factor, reason = self._recommend(confidence, uncertainty)
        return ConfidenceResult(
            confidence=confidence,
            uncertainty=uncertainty,
            recommendation=recommendation,
            size_factor=size_factor,
            reason=reason,
        )

    # -- internals ---------------------------------------------------------
    def _recommend(
        self, confidence: float, uncertainty: float
    ) -> tuple[ScoreRecommendation, float, str]:
        # High uncertainty blocks; confidence cannot override this.
        if uncertainty >= self._block_uncertainty:
            return ScoreRecommendation.BLOCK, 0.0, "uncertainty too high; block"
        if confidence < self._min_confidence:
            return ScoreRecommendation.BLOCK, 0.0, "confidence too low; block"
        if uncertainty >= self._reduce_uncertainty:
            return (
                ScoreRecommendation.REDUCE,
                self._reduce_factor,
                "elevated uncertainty; reduce size",
            )
        return ScoreRecommendation.ALLOW, 1.0, "eligible pending risk governor"

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))
