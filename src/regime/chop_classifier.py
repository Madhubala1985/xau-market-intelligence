"""CHOPPY regime decomposition (Task INTELLIGENCE-001).

Live evidence (170+ continuous cycles, 2026-06-10) showed CHOPPY acting as a
near-permanent hard block: the regime engine counts structure flips over the
WHOLE supplied window, and any flip-rich window blocked every entry even while
price trended directionally through London/NY. A single "CHOPPY" label is not
enough intelligence for XAU/USD: chop that precedes expansion, chop that
engineers liquidity, and genuinely dangerous chop are different conditions.

This classifier decomposes a CHOPPY window into subtypes:

- DANGEROUS_CHOP            hard block (erratic wicks / abnormal spread)
- LOW_QUALITY_CHOP          block (no usable evidence)
- LIQUIDITY_CHOP_WITH_SWEEP tradeable with HIGH confluence (sweep present)
- TRAP_REVERSAL_FROM_CHOP   tradeable with HIGH confluence (confirmed sweep
                            rejection = stop-hunt/trap completed)
- BREAKOUT_EXPANSION_FROM_CHOP tradeable with HIGH confluence (displacement
                            close beyond the prior consolidation range)
- CONTINUATION_AFTER_CHOP   tradeable with HIGH confluence (directional drift
                            resumed out of the chop)

"Tradeable" NEVER means "trade": it means the hypothesis gate may pass the
candidate to the confluence/scoring/risk stack instead of refusing outright.
Stop-loss, structural invalidation, the confidence engine, and the Risk
Governor all still apply. DANGEROUS_CHOP and LOW_QUALITY_CHOP keep blocking.

Heuristics are deliberately simple, honest, and testable — no indicator
pretence, just price-path geometry over a RECENT window.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from src.data.schemas import Candle
from src.liquidity.sweep import SweepEvent, SweepStatus


class ChopSubtype(str, Enum):
    DANGEROUS_CHOP = "DANGEROUS_CHOP"
    LOW_QUALITY_CHOP = "LOW_QUALITY_CHOP"
    LIQUIDITY_CHOP_WITH_SWEEP = "LIQUIDITY_CHOP_WITH_SWEEP"
    TRAP_REVERSAL_FROM_CHOP = "TRAP_REVERSAL_FROM_CHOP"
    BREAKOUT_EXPANSION_FROM_CHOP = "BREAKOUT_EXPANSION_FROM_CHOP"
    CONTINUATION_AFTER_CHOP = "CONTINUATION_AFTER_CHOP"


_HARD_BLOCK = {ChopSubtype.DANGEROUS_CHOP, ChopSubtype.LOW_QUALITY_CHOP}


@dataclass(frozen=True)
class ChopAssessment:
    """Subtype + the measured features that produced it (credential-free)."""

    subtype: ChopSubtype
    tradeable: bool          # may proceed to confluence gating (never auto-trade)
    reason: str
    drift_ratio: float       # |net move| / path length over the recent window
    displacement_ratio: float  # strongest recent body vs median range
    wick_ratio: float        # mean wick share of range (erratic-ness)

    def to_dict(self) -> dict:
        return {
            "subtype": self.subtype.value,
            "tradeable": self.tradeable,
            "reason": self.reason,
            "drift_ratio": round(self.drift_ratio, 4),
            "displacement_ratio": round(self.displacement_ratio, 4),
            "wick_ratio": round(self.wick_ratio, 4),
        }


class ChopClassifier:
    """Decomposes a CHOPPY window into graded subtypes."""

    def __init__(
        self,
        *,
        window: int = 36,                # ~3h of M5
        dangerous_wick_ratio: float = 0.70,
        dangerous_spread_ratio: float = 0.80,
        displacement_factor: float = 1.8,
        drift_continuation: float = 0.35,
        breakout_lookback: int = 24,
    ) -> None:
        self._window = window
        self._dangerous_wick = dangerous_wick_ratio
        self._dangerous_spread = dangerous_spread_ratio
        self._displacement_factor = displacement_factor
        self._drift_continuation = drift_continuation
        self._breakout_lookback = breakout_lookback

    def classify(
        self,
        candles: Sequence[Candle],
        sweeps: Sequence[SweepEvent] = (),
        *,
        spread_ratio: float = 0.0,   # current spread / allowed max, in [0, ~]
    ) -> ChopAssessment:
        recent = list(candles[-self._window:])
        if len(recent) < 6:
            return self._make(
                ChopSubtype.LOW_QUALITY_CHOP,
                "insufficient recent data", 0.0, 0.0, 0.0,
            )

        drift = self._drift_ratio(recent)
        displacement = self._displacement_ratio(recent)
        wick = self._wick_ratio(recent)

        # 1) Dangerous conditions: abnormal spread or erratic wick-dominated
        #    candles — always a hard block (03_RISK_POLICY dangerous volatility).
        if spread_ratio >= self._dangerous_spread:
            return self._make(
                ChopSubtype.DANGEROUS_CHOP,
                f"spread at {spread_ratio:.0%} of the allowed max",
                drift, displacement, wick,
            )
        if wick >= self._dangerous_wick:
            return self._make(
                ChopSubtype.DANGEROUS_CHOP,
                f"erratic candles: mean wick share {wick:.2f}",
                drift, displacement, wick,
            )

        recent_sweep = self._recent_sweep(sweeps, len(candles))

        # 2) Completed trap: a CONFIRMED sweep rejection inside/after the chop.
        if recent_sweep is not None and recent_sweep.status is SweepStatus.TRUE_SWEEP:
            return self._make(
                ChopSubtype.TRAP_REVERSAL_FROM_CHOP,
                f"confirmed {recent_sweep.swept_side.value} sweep rejection "
                "(stop-hunt completed)",
                drift, displacement, wick,
            )

        # 3) Breakout expansion: displacement close beyond the consolidation.
        if displacement >= self._displacement_factor and self._broke_range(recent):
            return self._make(
                ChopSubtype.BREAKOUT_EXPANSION_FROM_CHOP,
                f"displacement {displacement:.1f}x closed beyond the recent range",
                drift, displacement, wick,
            )

        # 4) Liquidity chop: a sweep candidate exists but is unconfirmed.
        if recent_sweep is not None:
            return self._make(
                ChopSubtype.LIQUIDITY_CHOP_WITH_SWEEP,
                f"{recent_sweep.swept_side.value} sweep pending confirmation",
                drift, displacement, wick,
            )

        # 5) Directional drift out of chop (continuation).
        if drift >= self._drift_continuation:
            return self._make(
                ChopSubtype.CONTINUATION_AFTER_CHOP,
                f"directional drift resumed (drift ratio {drift:.2f})",
                drift, displacement, wick,
            )

        return self._make(
            ChopSubtype.LOW_QUALITY_CHOP,
            f"no sweep, no breakout, weak drift ({drift:.2f})",
            drift, displacement, wick,
        )

    # -- features ----------------------------------------------------------------
    @staticmethod
    def _drift_ratio(recent: Sequence[Candle]) -> float:
        net = abs(recent[-1].close - recent[0].close)
        path = sum(abs(c.close - c.open) for c in recent)
        return net / path if path > 0 else 0.0

    @staticmethod
    def _displacement_ratio(recent: Sequence[Candle]) -> float:
        ranges = sorted(c.high - c.low for c in recent)
        median = ranges[len(ranges) // 2] if ranges else 0.0
        if median <= 0:
            return 0.0
        strongest = max(abs(c.close - c.open) for c in recent)
        return strongest / median

    @staticmethod
    def _wick_ratio(recent: Sequence[Candle]) -> float:
        shares = []
        for c in recent:
            full = c.high - c.low
            if full <= 0:
                continue
            shares.append(1.0 - abs(c.close - c.open) / full)
        return sum(shares) / len(shares) if shares else 0.0

    def _broke_range(self, recent: Sequence[Candle]) -> bool:
        if len(recent) <= self._breakout_lookback // 2:
            return False
        prior = recent[:-self._breakout_lookback // 4 or -1]
        last_close = recent[-1].close
        prior_high = max(c.high for c in prior)
        prior_low = min(c.low for c in prior)
        return last_close > prior_high or last_close < prior_low

    @staticmethod
    def _recent_sweep(
        sweeps: Sequence[SweepEvent], total: int, lookback: int = 30
    ) -> Optional[SweepEvent]:
        recent = [
            s for s in sweeps
            if s.status in (SweepStatus.TRUE_SWEEP, SweepStatus.PENDING)
            and s.sweep_index >= total - lookback
        ]
        if not recent:
            return None
        # Prefer confirmed sweeps, then the most recent.
        recent.sort(
            key=lambda s: (s.status is SweepStatus.TRUE_SWEEP, s.sweep_index)
        )
        return recent[-1]

    def _make(
        self, subtype: ChopSubtype, reason: str,
        drift: float, displacement: float, wick: float,
    ) -> ChopAssessment:
        return ChopAssessment(
            subtype=subtype,
            tradeable=subtype not in _HARD_BLOCK,
            reason=reason,
            drift_ratio=drift,
            displacement_ratio=displacement,
            wick_ratio=wick,
        )
