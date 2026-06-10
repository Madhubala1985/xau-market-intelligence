"""Adaptive Risk Budget Engine (Task INTELLIGENCE-001).

Replaces the static "always 0.5%" behavior with an evidence-driven risk
budget. The budget EXPANDS only when evidence is strong (confluence, MTF
alignment, confidence, clean conditions) and CONTRACTS multiplicatively on
losses, drawdown, uncertainty, bad spread, news risk, or existing exposure.

Hard guarantees (03_RISK_POLICY.md is the authority; its Adaptive Demo Risk
Policy section, decision 2026-06-10-08, defines the bounds used here):
- the budget NEVER exceeds the phase ceiling, and no phase ceiling exceeds
  the absolute demo cap (1.0%); daily 2% / weekly 5% loss limits are
  untouched survival anchors enforced by the governor and the service;
- contraction factors are multiplicative and <= 1, so consecutive losses can
  only shrink risk: no martingale, no grid, no recovery sizing, structurally;
- real-money risk policy is NOT this policy and remains unchanged (0.25%);
- changing these bounds again requires evidence and a manual policy edit —
  this engine cannot do it.

Capital phases (growth objective $2k -> $10k -> $15k -> $25k+):

    phase     equity        base    ceiling   rationale
    PHASE_1   < $10k        0.40%   1.00%     growth phase: elite evidence may
                                              run 2 losses-to-daily-stop risk
    PHASE_2   $10k-$15k     0.35%   0.80%     protect the first milestone
    PHASE_3   $15k-$25k     0.30%   0.60%     de-risk into the next milestone
    PHASE_4   >= $25k       0.20%   0.50%     capital preservation

The ceiling is reached ONLY via evidence expansion (max x2.0 of base on
elite evidence) and only when nothing is contracting. Expected-growth math
(recorded in 03_RISK_POLICY): with expectancy E = r(pR - (1-p)) at p=0.45,
R=2, a flat 0.5% risks E≈0.18%/trade => ~900 trades to 5x; evidence-tiered
risk concentrating 0.8-1.0% on the highest-quality subset roughly halves the
trades needed for the same drawdown bound, because the daily/weekly stops —
not the per-trade cap — bound the tail.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

# 03_RISK_POLICY "Adaptive Demo Risk Policy": absolute demo per-trade ceiling.
# Phase ceilings below can only tighten it. Real-money policy is separate
# and unchanged.
POLICY_RISK_CAP = 0.010
RISK_FLOOR = 0.001        # below this a trade is not worth its costs


class CapitalPhase(str, Enum):
    PHASE_1 = "PHASE_1"   # < $10k   (growth: $2k -> $10k)
    PHASE_2 = "PHASE_2"   # < $15k
    PHASE_3 = "PHASE_3"   # < $25k
    PHASE_4 = "PHASE_4"   # >= $25k

    @classmethod
    def of(cls, equity: float) -> "CapitalPhase":
        if equity < 10_000:
            return cls.PHASE_1
        if equity < 15_000:
            return cls.PHASE_2
        if equity < 25_000:
            return cls.PHASE_3
        return cls.PHASE_4


_PHASE_BASE = {
    CapitalPhase.PHASE_1: 0.0040,
    CapitalPhase.PHASE_2: 0.0035,
    CapitalPhase.PHASE_3: 0.0030,
    CapitalPhase.PHASE_4: 0.0020,
}

# Evidence-gated ceilings per phase (Adaptive Demo Risk Policy). Reached only
# through expansion on elite evidence with nothing contracting.
_PHASE_CEILING = {
    CapitalPhase.PHASE_1: 0.0100,
    CapitalPhase.PHASE_2: 0.0080,
    CapitalPhase.PHASE_3: 0.0060,
    CapitalPhase.PHASE_4: 0.0050,
}


class RiskTier(str, Enum):
    BLOCKED = "BLOCKED"        # conditions make any risk unjustifiable
    MINIMAL = "MINIMAL"        # heavy contraction: probe size only
    DEFENSIVE = "DEFENSIVE"    # contracted below base
    STANDARD = "STANDARD"      # around the phase base
    ELEVATED = "ELEVATED"      # expanded on strong evidence
    MAX_EVIDENCE = "MAX_EVIDENCE"  # at/near the policy cap; rare


@dataclass(frozen=True)
class AdaptiveRiskInputs:
    """Everything the budget decision is based on (credential-free)."""

    equity: float
    confluence_score: float        # [0,1] graded evidence
    mtf_score: float               # [0,1] multi-timeframe agreement
    confidence: float              # [0,1]
    uncertainty: float             # [0,1]
    regime_tradeable: bool         # graded regime gate outcome
    spread_ratio: float            # current spread / allowed max
    news_clear: bool               # known AND not risky
    consecutive_losses: int
    daily_loss_pct: float
    weekly_loss_pct: float
    open_positions: int


@dataclass(frozen=True)
class AdaptiveRiskDecision:
    """The budget for ONE prospective trade."""

    risk_pct: float
    tier: RiskTier
    phase: CapitalPhase
    reasons: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "risk_pct": round(self.risk_pct, 6),
            "tier": self.tier.value,
            "phase": self.phase.value,
            "reasons": list(self.reasons),
        }


class AdaptiveRiskEngine:
    """Computes the evidence-driven risk budget for one prospective trade."""

    def __init__(
        self,
        *,
        policy_cap: float = POLICY_RISK_CAP,
        floor: float = RISK_FLOOR,
    ) -> None:
        if not (0 < floor <= policy_cap):
            raise ValueError("floor must be in (0, policy_cap]")
        self._cap = policy_cap
        self._floor = floor

    def decide(self, inputs: AdaptiveRiskInputs) -> AdaptiveRiskDecision:
        phase = CapitalPhase.of(inputs.equity)
        reasons: List[str] = [f"phase {phase.value} base"]

        # Unjustifiable conditions: no budget at all (fail closed).
        if not inputs.news_clear:
            return self._blocked(phase, "news risk not clear")
        if not inputs.regime_tradeable:
            return self._blocked(phase, "regime gate does not permit trading")
        if inputs.spread_ratio >= 1.0:
            return self._blocked(phase, "spread at/above the allowed max")

        risk = _PHASE_BASE[phase]

        # -- expansion: ONLY on strong combined evidence -----------------------
        evidence = min(inputs.confluence_score, inputs.mtf_score)
        if (
            inputs.confluence_score >= 0.85
            and inputs.mtf_score >= 0.75
            and inputs.confidence >= 0.75
            and inputs.uncertainty <= 0.20
        ):
            risk *= 2.00
            reasons.append("expansion x2.00: elite evidence")
        elif (
            inputs.confluence_score >= 0.70
            and inputs.mtf_score >= 0.60
            and inputs.confidence >= 0.65
            and inputs.uncertainty <= 0.30
        ):
            risk *= 1.40
            reasons.append("expansion x1.40: strong evidence")
        elif inputs.confluence_score < 0.50 or evidence < 0.35:
            risk *= 0.60
            reasons.append("contraction x0.60: weak evidence")

        # -- contraction: multiplicative, never expansive ----------------------
        if inputs.consecutive_losses > 0:
            factor = max(0.40, 0.75 ** inputs.consecutive_losses)
            risk *= factor
            reasons.append(
                f"contraction x{factor:.2f}: {inputs.consecutive_losses} "
                "consecutive loss(es)"
            )
        if inputs.daily_loss_pct >= 0.01:
            risk *= 0.50
            reasons.append("contraction x0.50: daily drawdown >= 1%")
        if inputs.weekly_loss_pct >= 0.03:
            risk *= 0.50
            reasons.append("contraction x0.50: weekly drawdown >= 3%")
        if inputs.uncertainty >= 0.50:
            risk *= 0.50
            reasons.append("contraction x0.50: high uncertainty")
        if inputs.spread_ratio >= 0.60:
            risk *= 0.75
            reasons.append("contraction x0.75: spread degraded")
        if inputs.open_positions > 0:
            risk *= 0.50
            reasons.append("contraction x0.50: existing open exposure")

        # -- clamp to [floor, phase ceiling]; ceilings are NEVER exceeded ------
        ceiling = min(_PHASE_CEILING[phase], self._cap)
        if risk > ceiling:
            reasons.append(f"clamped to {phase.value} ceiling {ceiling:.4f}")
            risk = ceiling
        if risk < self._floor:
            reasons.append(f"raised to floor {self._floor:.4f} (probe size)")
            risk = self._floor

        return AdaptiveRiskDecision(
            risk_pct=risk,
            tier=self._tier(risk, _PHASE_BASE[phase], ceiling),
            phase=phase,
            reasons=tuple(reasons),
        )

    # -- helpers ---------------------------------------------------------------
    def _blocked(self, phase: CapitalPhase, why: str) -> AdaptiveRiskDecision:
        return AdaptiveRiskDecision(
            risk_pct=0.0, tier=RiskTier.BLOCKED, phase=phase,
            reasons=(f"no risk budget: {why}",),
        )

    def _tier(self, risk: float, base: float, ceiling: float) -> RiskTier:
        if risk >= ceiling * 0.99:
            return RiskTier.MAX_EVIDENCE
        if risk >= base * 1.2:
            return RiskTier.ELEVATED
        if risk >= base * 0.8:
            return RiskTier.STANDARD
        if risk >= base * 0.45:
            return RiskTier.DEFENSIVE
        return RiskTier.MINIMAL
