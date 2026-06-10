"""Milestone-aware adaptive lot sizing (Task SIZING-001).

Root cause this module fixes (Proven Defect, live evidence 2026-06-10): a
fully-qualified SHORT candidate (confluence 0.70, MTF 0.90, TRUE_SWEEP, FVG,
OB, displacement 1.8x) died with "invalid lot size 0.0" because the adaptive
budget (DEFENSIVE 0.20% of $2,000 = $4) was smaller than the loss of the
broker MINIMUM lot (0.01 x 100 oz x stop distance). The sizers blocked, the
lot fell to 0.0, and the governor reported a vague invalid-lot error.

The fix: ONE explicit lot resolver that converts the adaptive risk budget
into a broker-valid volume with a documented verdict — never a silent 0.0:

    raw_lot     = (equity x risk_pct) / (stop_distance x contract_size)
    rounded_lot = floor(raw_lot / lot_step) x lot_step

- rounded_lot >= min_lot                       -> SIZED (capped at max_lot)
- rounded_lot < min_lot:
    min_lot_risk = min_lot x contract_size x stop_distance
    * min_lot_risk <= equity x ceiling_pct     -> MIN_LOT_PROMOTED_TO_0_01
      (the phase CEILING — not the contracted budget — bounds viability;
      a defensive budget means "risk less when possible", not "the broker
      minimum is forbidden")
    * min_lot_risk >  equity x ceiling_pct     -> MIN_LOT_RISK_TOO_HIGH
    * min_lot_risk >  equity x absolute cap    -> STOP_TOO_WIDE_FOR_ACCOUNT

Lot size is NEVER fixed: it scales continuously with equity, the adaptive
budget (setup quality, drawdown, news/macro state...), and the stop distance.
Milestone context ($2k -> $10k -> $15k -> $25k) is carried for diagnostics:
growth comes from expectancy x compounding inside the phase ceilings, never
from martingale/grid/averaging (the adaptive engine is contraction-only on
adverse signals and this resolver cannot exceed its ceilings).

Every decision carries full diagnostics for the terminal and the journal.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.risk.adaptive_risk import POLICY_RISK_CAP, CapitalPhase

_EPS = 1e-9

_MILESTONE = {
    CapitalPhase.PHASE_1: "$10,000 (milestone 1)",
    CapitalPhase.PHASE_2: "$15,000 (milestone 2)",
    CapitalPhase.PHASE_3: "$25,000 (milestone 3)",
    CapitalPhase.PHASE_4: "beyond $25,000 (compounding)",
}


class LotVerdict:
    SIZED = "SIZED"
    MIN_LOT_PROMOTED = "MIN_LOT_PROMOTED_TO_0.01"
    MIN_LOT_RISK_TOO_HIGH = "MIN_LOT_RISK_TOO_HIGH"
    STOP_TOO_WIDE = "STOP_TOO_WIDE_FOR_ACCOUNT"
    NO_STOP = "NO_STOP_DISTANCE"
    NO_BUDGET = "NO_RISK_BUDGET"


_BLOCKING = {LotVerdict.MIN_LOT_RISK_TOO_HIGH, LotVerdict.STOP_TOO_WIDE,
             LotVerdict.NO_STOP, LotVerdict.NO_BUDGET}


@dataclass(frozen=True)
class LotDecision:
    """A fully-explained lot sizing outcome (credential-free)."""

    lot: float                 # final broker-valid lot (0.0 ONLY when blocked)
    verdict: str
    reason: str
    risk_pct: float            # adaptive budget used
    risk_usd: float
    ceiling_pct: float         # phase ceiling bounding min-lot viability
    ceiling_usd: float
    stop_distance: float       # effective distance incl. spread buffer
    min_lot_risk_usd: float    # loss at the broker minimum lot
    raw_lot: float
    rounded_lot: float
    realized_risk_usd: float   # loss-at-stop of the FINAL lot
    realized_risk_pct: float
    phase: str
    milestone: str

    @property
    def approved(self) -> bool:
        return self.verdict not in _BLOCKING and self.lot > 0

    def to_dict(self) -> dict:
        return {
            "lot": self.lot,
            "verdict": self.verdict,
            "reason": self.reason,
            "risk_pct": round(self.risk_pct, 6),
            "risk_usd": round(self.risk_usd, 2),
            "ceiling_pct": round(self.ceiling_pct, 6),
            "ceiling_usd": round(self.ceiling_usd, 2),
            "stop_distance": round(self.stop_distance, 4),
            "min_lot_risk_usd": round(self.min_lot_risk_usd, 2),
            "raw_lot": round(self.raw_lot, 5),
            "rounded_lot": round(self.rounded_lot, 4),
            "realized_risk_usd": round(self.realized_risk_usd, 2),
            "realized_risk_pct": round(self.realized_risk_pct, 6),
            "phase": self.phase,
            "milestone": self.milestone,
        }


def resolve_lot(
    *,
    equity: float,
    risk_pct: float,
    ceiling_pct: float,
    stop_distance: float,
    contract_size: float = 100.0,   # XAUUSDm: 100 oz/lot (WINMT5-LIVE-001)
    min_lot: float = 0.01,
    lot_step: float = 0.01,
    max_lot: float = 100.0,
    absolute_cap_pct: float = POLICY_RISK_CAP,
) -> LotDecision:
    """Convert the adaptive risk budget into a broker-valid lot. Never vague."""
    phase = CapitalPhase.of(equity)
    milestone = _MILESTONE[phase]
    ceiling_pct = min(ceiling_pct, absolute_cap_pct)
    risk_usd = max(0.0, equity * risk_pct)
    ceiling_usd = max(0.0, equity * ceiling_pct)
    min_lot_risk = min_lot * contract_size * max(stop_distance, 0.0)

    def make(lot, verdict, reason, raw=0.0, rounded=0.0) -> LotDecision:
        realized = lot * contract_size * max(stop_distance, 0.0)
        return LotDecision(
            lot=lot, verdict=verdict, reason=reason,
            risk_pct=risk_pct, risk_usd=risk_usd,
            ceiling_pct=ceiling_pct, ceiling_usd=ceiling_usd,
            stop_distance=stop_distance, min_lot_risk_usd=min_lot_risk,
            raw_lot=raw, rounded_lot=rounded,
            realized_risk_usd=realized,
            realized_risk_pct=(realized / equity) if equity > 0 else 0.0,
            phase=phase.value, milestone=milestone,
        )

    if stop_distance <= 0:
        return make(0.0, LotVerdict.NO_STOP,
                    "no usable stop distance (stop-loss is mandatory)")
    if risk_usd <= 0 or equity <= 0:
        return make(0.0, LotVerdict.NO_BUDGET,
                    "adaptive risk budget is zero (blocked conditions)")

    raw = risk_usd / (stop_distance * contract_size)
    rounded = math.floor(raw / lot_step + _EPS) * lot_step
    rounded = round(rounded, 8)

    if rounded >= min_lot - _EPS:
        lot = min(rounded, max_lot)
        return make(
            lot, LotVerdict.SIZED,
            f"budget ${risk_usd:.2f} over {stop_distance:.2f} stop -> "
            f"{lot} lot (raw {raw:.4f})",
            raw=raw, rounded=rounded,
        )

    # Below the broker minimum: explicit min-lot viability decision.
    if min_lot_risk <= equity * absolute_cap_pct + _EPS:
        if min_lot_risk <= ceiling_usd + _EPS:
            return make(
                min_lot, LotVerdict.MIN_LOT_PROMOTED,
                f"budget ${risk_usd:.2f} sizes below the broker minimum; "
                f"min-lot risk ${min_lot_risk:.2f} "
                f"({min_lot_risk / equity:.2%}) fits inside the "
                f"{phase.value} ceiling ${ceiling_usd:.2f} -> promoted to "
                f"{min_lot}",
                raw=raw, rounded=rounded,
            )
        return make(
            0.0, LotVerdict.MIN_LOT_RISK_TOO_HIGH,
            f"min-lot risk ${min_lot_risk:.2f} "
            f"({min_lot_risk / equity:.2%}) exceeds the {phase.value} "
            f"ceiling ${ceiling_usd:.2f}; skip (stop {stop_distance:.2f}, "
            f"min lot {min_lot})",
            raw=raw, rounded=rounded,
        )
    return make(
        0.0, LotVerdict.STOP_TOO_WIDE,
        f"min-lot risk ${min_lot_risk:.2f} ({min_lot_risk / equity:.2%}) "
        f"exceeds even the absolute demo cap "
        f"({absolute_cap_pct:.2%}) on this equity; the logical stop "
        f"({stop_distance:.2f}) is too wide for the account",
        raw=raw, rounded=rounded,
    )
