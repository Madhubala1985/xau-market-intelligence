"""Adaptive Risk Budget Engine (Task INTELLIGENCE-001).

Replaces the static "always 0.5%" behavior with an evidence-driven risk
budget. The budget EXPANDS only when evidence is strong (confluence, MTF
alignment, confidence, clean conditions) and CONTRACTS multiplicatively on
losses, drawdown, uncertainty, bad spread, news risk, or existing exposure.

Hard guarantees (03_RISK_POLICY.md is the authority):
- the budget NEVER exceeds the policy cap (0.50% per trade in demo) — the cap
  is a ceiling the engine can only stay under, not a default it always uses;
- contraction factors are multiplicative and <= 1, so consecutive losses can
  only shrink risk: no martingale, no grid, no recovery sizing, structurally;
- raising the policy cap itself requires validated evidence and a manual
  policy change — this engine cannot do it.

Capital phases (growth objective $2k -> $10k -> $15k -> $25k+) set the BASE
budget: earlier phases run a relatively larger base (small-account growth),
later phases de-risk — but every phase remains inside the policy cap and
every phase contracts identically on bad conditions. Growth is treated as a
probabilistic objective (expectancy x opportunity quality), never a promise.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

POLICY_RISK_CAP = 0.005   # 03_RISK_POLICY demo: max risk per trade
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
    CapitalPhase.PHASE_1: 0.0030,
    CapitalPhase.PHASE_2: 0.0030,
    CapitalPhase.PHASE_3: 0.0025,
    CapitalPhase.PHASE_4: 0.0020,
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
            risk *= 1.65
            reasons.append("expansion x1.65: elite evidence")
        elif (
            inputs.confluence_score >= 0.70
            and inputs.mtf_score >= 0.60
            and inputs.confidence >= 0.65
            and inputs.uncertainty <= 0.30
        ):
            risk *= 1.30
            reasons.append("expansion x1.30: strong evidence")
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

        # -- clamp to [floor, policy cap]; the cap is NEVER exceeded -----------
        if risk > self._cap:
            reasons.append(f"clamped to policy cap {self._cap:.4f}")
            risk = self._cap
        if risk < self._floor:
            reasons.append(f"raised to floor {self._floor:.4f} (probe size)")
            risk = self._floor

        return AdaptiveRiskDecision(
            risk_pct=risk,
            tier=self._tier(risk, _PHASE_BASE[phase]),
            phase=phase,
            reasons=tuple(reasons),
        )

    # -- helpers ---------------------------------------------------------------
    def _blocked(self, phase: CapitalPhase, why: str) -> AdaptiveRiskDecision:
        return AdaptiveRiskDecision(
            risk_pct=0.0, tier=RiskTier.BLOCKED, phase=phase,
            reasons=(f"no risk budget: {why}",),
        )

    def _tier(self, risk: float, base: float) -> RiskTier:
        if risk >= self._cap * 0.99:
            return RiskTier.MAX_EVIDENCE
        if risk >= base * 1.2:
            return RiskTier.ELEVATED
        if risk >= base * 0.8:
            return RiskTier.STANDARD
        if risk >= base * 0.45:
            return RiskTier.DEFENSIVE
        return RiskTier.MINIMAL
