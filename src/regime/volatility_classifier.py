"""Gold-specific volatility safety classifier (Task INTELLIGENCE-002).

03_RISK_POLICY.md distinguishes TRADABLE volatility (opportunity) from
DANGEROUS volatility (must block). Before this module the distinction lived
implicitly in regime scores and spread gates; this makes it an explicit,
testable layer:

- NORMAL             ordinary conditions
- EXPANSION          volatility widening; tradeable WITH confluence
- DANGEROUS_SPIKE    one candle far outside the recent distribution
- NEWS_LIKE_SHOCK    a burst of huge alternating candles (news behavior)
- SPREAD_MISMATCH    spread blown out while price volatility is ordinary
                     (feed/liquidity problem, not opportunity)
- UNSTABLE_STOPS     short-term ATR exploding with wick-dominated candles:
                     no stop distance is rational

The dangerous states (SPIKE / SHOCK / MISMATCH / UNSTABLE_STOPS) hard-block
new entries in the pipeline. EXPANSION never blocks by itself — XAU/USD
opportunity often lives there (03_RISK_POLICY volatility rule).

Pure price-path geometry; no indicators pretended, no credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from src.data.schemas import Candle


class VolatilityState(str, Enum):
    NORMAL = "NORMAL"
    EXPANSION = "EXPANSION"
    DANGEROUS_SPIKE = "DANGEROUS_SPIKE"
    NEWS_LIKE_SHOCK = "NEWS_LIKE_SHOCK"
    SPREAD_MISMATCH = "SPREAD_MISMATCH"
    UNSTABLE_STOPS = "UNSTABLE_STOPS"


_DANGEROUS = {
    VolatilityState.DANGEROUS_SPIKE,
    VolatilityState.NEWS_LIKE_SHOCK,
    VolatilityState.SPREAD_MISMATCH,
    VolatilityState.UNSTABLE_STOPS,
}


@dataclass(frozen=True)
class VolatilityAssessment:
    state: VolatilityState
    dangerous: bool
    reason: str
    spike_ratio: float    # last range / median range
    atr_ratio: float      # short ATR / long ATR
    wick_ratio: float     # mean wick share over the short window

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "dangerous": self.dangerous,
            "reason": self.reason,
            "spike_ratio": round(self.spike_ratio, 3),
            "atr_ratio": round(self.atr_ratio, 3),
            "wick_ratio": round(self.wick_ratio, 3),
        }


class VolatilityClassifier:
    """Classifies the volatility state of the recent exec window."""

    def __init__(
        self,
        *,
        window: int = 30,
        short_window: int = 5,
        spike_factor: float = 4.0,
        shock_factor: float = 2.5,
        shock_count: int = 3,
        mismatch_spread_ratio: float = 0.70,
        unstable_atr_ratio: float = 2.0,
        unstable_wick_ratio: float = 0.60,
        expansion_atr_ratio: float = 1.4,
    ) -> None:
        self._window = window
        self._short = short_window
        self._spike = spike_factor
        self._shock = shock_factor
        self._shock_count = shock_count
        self._mismatch_spread = mismatch_spread_ratio
        self._unstable_atr = unstable_atr_ratio
        self._unstable_wick = unstable_wick_ratio
        self._expansion_atr = expansion_atr_ratio

    def classify(
        self, candles: Sequence[Candle], *, spread_ratio: float = 0.0
    ) -> VolatilityAssessment:
        recent = list(candles[-self._window:])
        if len(recent) < self._short + 3:
            return self._make(VolatilityState.NORMAL,
                              "insufficient data; treated as normal",
                              0.0, 1.0, 0.0)

        ranges = [c.high - c.low for c in recent]
        median = sorted(ranges)[len(ranges) // 2]
        median = median if median > 0 else 1e-9
        short = recent[-self._short:]
        spike_ratio = ranges[-1] / median
        atr_short = sum(c.high - c.low for c in short) / len(short)
        atr_long = sum(ranges) / len(ranges)
        atr_ratio = atr_short / atr_long if atr_long > 0 else 1.0
        wick_ratio = self._wick_share(short)

        # 1) One candle far outside the distribution.
        if spike_ratio >= self._spike:
            return self._make(
                VolatilityState.DANGEROUS_SPIKE,
                f"last candle {spike_ratio:.1f}x the median range",
                spike_ratio, atr_ratio, wick_ratio,
            )
        # 2) A burst of huge alternating candles (news-like behavior).
        big = [c for c in short if (c.high - c.low) >= self._shock * median]
        if len(big) >= self._shock_count and self._alternating(short):
            return self._make(
                VolatilityState.NEWS_LIKE_SHOCK,
                f"{len(big)} candles >= {self._shock}x median with "
                "alternating direction",
                spike_ratio, atr_ratio, wick_ratio,
            )
        # 3) Spread blown out without matching price volatility.
        if spread_ratio >= self._mismatch_spread and atr_ratio < self._expansion_atr:
            return self._make(
                VolatilityState.SPREAD_MISMATCH,
                f"spread at {spread_ratio:.0%} of max while volatility is "
                "ordinary (liquidity problem, not opportunity)",
                spike_ratio, atr_ratio, wick_ratio,
            )
        # 4) Stop distances unstable: ATR exploding + wick-dominated candles.
        if atr_ratio >= self._unstable_atr and wick_ratio >= self._unstable_wick:
            return self._make(
                VolatilityState.UNSTABLE_STOPS,
                f"short ATR {atr_ratio:.1f}x baseline with wick share "
                f"{wick_ratio:.2f}; no rational stop distance",
                spike_ratio, atr_ratio, wick_ratio,
            )
        # 5) Honest expansion: tradeable with confluence, never auto-blocked.
        if atr_ratio >= self._expansion_atr:
            return self._make(
                VolatilityState.EXPANSION,
                f"volatility expanding ({atr_ratio:.1f}x baseline)",
                spike_ratio, atr_ratio, wick_ratio,
            )
        return self._make(VolatilityState.NORMAL, "ordinary volatility",
                          spike_ratio, atr_ratio, wick_ratio)

    # -- helpers ---------------------------------------------------------------
    @staticmethod
    def _wick_share(candles: Sequence[Candle]) -> float:
        shares = []
        for c in candles:
            full = c.high - c.low
            if full <= 0:
                continue
            shares.append(1.0 - abs(c.close - c.open) / full)
        return sum(shares) / len(shares) if shares else 0.0

    @staticmethod
    def _alternating(candles: Sequence[Candle]) -> bool:
        directions = [1 if c.close >= c.open else -1 for c in candles]
        flips = sum(1 for a, b in zip(directions, directions[1:]) if a != b)
        return flips >= len(directions) // 2

    @staticmethod
    def _make(state, reason, spike, atr, wick) -> VolatilityAssessment:
        return VolatilityAssessment(
            state=state, dangerous=state in _DANGEROUS, reason=reason,
            spike_ratio=spike, atr_ratio=atr, wick_ratio=wick,
        )
