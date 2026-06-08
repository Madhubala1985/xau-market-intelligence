"""Premium / discount engine (Task P3-005).

Marks premium and discount areas within a selected swing range, with optional
Gann-box-style band segmentation. References 13_XAUUSD_SMC_PLAYBOOK.md
(premium/discount location).

Model:
- A DealingRange is defined by a swing high and swing low. Its equilibrium is the
  50% midpoint.
- Discount = below equilibrium (look for longs); premium = above equilibrium
  (look for shorts); a configurable band around 50% is EQUILIBRIUM.
- Gann-box segmentation subdivides the range at configurable fractions
  (default quartiles 0/25/50/75/100%) into labeled bands, each classified as
  premium / discount / equilibrium.

No look-ahead: the auto range selector uses confirmed swings only (P3-001), so
the chosen range depends only on the candles supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from src.data.schemas import Candle
from src.structure.market_structure import MarketStructureEngine, SwingType


class PriceZone(str, Enum):
    PREMIUM = "PREMIUM"
    DISCOUNT = "DISCOUNT"
    EQUILIBRIUM = "EQUILIBRIUM"


# Default Gann-box-style segmentation (quartiles).
DEFAULT_SEGMENTS: Tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)


@dataclass(frozen=True)
class DealingRange:
    """A swing range used to derive premium/discount location."""

    high: float
    low: float
    high_index: Optional[int] = None
    low_index: Optional[int] = None
    high_time: Optional[datetime] = None
    low_time: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.high <= self.low:
            raise ValueError("DealingRange high must be > low")

    @property
    def size(self) -> float:
        return self.high - self.low

    @property
    def equilibrium(self) -> float:
        return (self.high + self.low) / 2

    def fraction_of(self, price: float) -> float:
        """Position of a price within the range (0 = low, 1 = high)."""
        return (price - self.low) / self.size

    def price_at(self, fraction: float) -> float:
        """Price at a given fraction of the range."""
        return self.low + fraction * self.size


@dataclass(frozen=True)
class PremiumDiscountBand:
    """One Gann-box-style band within the range."""

    zone: PriceZone
    bottom: float
    top: float
    lower_fraction: float
    upper_fraction: float
    label: str


class PremiumDiscountEngine:
    """Classifies prices as premium/discount/equilibrium within a range."""

    def __init__(
        self,
        *,
        swing_strength: int = 2,
        equilibrium_band: float = 0.0,
        segments: Sequence[float] = DEFAULT_SEGMENTS,
    ) -> None:
        if not 0.0 <= equilibrium_band < 1.0:
            raise ValueError("equilibrium_band must be in [0, 1)")
        seg = tuple(segments)
        if len(seg) < 2 or any(seg[i] >= seg[i + 1] for i in range(len(seg) - 1)):
            raise ValueError("segments must be strictly increasing with >= 2 points")
        if seg[0] < 0.0 or seg[-1] > 1.0:
            raise ValueError("segments must lie within [0, 1]")
        self._structure = MarketStructureEngine(strength=swing_strength)
        self._equilibrium_band = equilibrium_band
        self._segments = seg

    # -- range selection ---------------------------------------------------
    def range_from_candles(self, candles: Sequence[Candle]) -> Optional[DealingRange]:
        """Build a dealing range from the most recent confirmed swings.

        Returns None if there is no confirmed swing high and low, or the range is
        degenerate (swing high not above swing low).
        """
        swings = self._structure.find_swings(candles)
        highs = [s for s in swings if s.swing_type is SwingType.HIGH]
        lows = [s for s in swings if s.swing_type is SwingType.LOW]
        if not highs or not lows:
            return None
        high_pt, low_pt = highs[-1], lows[-1]  # most recent of each (sorted)
        if high_pt.price <= low_pt.price:
            return None
        return DealingRange(
            high=high_pt.price,
            low=low_pt.price,
            high_index=high_pt.index,
            low_index=low_pt.index,
            high_time=high_pt.time_utc,
            low_time=low_pt.time_utc,
        )

    # -- classification ----------------------------------------------------
    def classify(self, dealing_range: DealingRange, price: float) -> PriceZone:
        """Classify a price as premium / discount / equilibrium."""
        return self._zone_for_fraction(dealing_range.fraction_of(price))

    def _zone_for_fraction(self, fraction: float) -> PriceZone:
        half_band = self._equilibrium_band / 2
        if abs(fraction - 0.5) <= half_band:
            return PriceZone.EQUILIBRIUM
        return PriceZone.PREMIUM if fraction > 0.5 else PriceZone.DISCOUNT

    # -- segmentation ------------------------------------------------------
    def segments(self, dealing_range: DealingRange) -> List[PremiumDiscountBand]:
        """Return Gann-box-style bands spanning the range, low to high."""
        bands: List[PremiumDiscountBand] = []
        for lower, upper in zip(self._segments, self._segments[1:]):
            mid = (lower + upper) / 2
            bands.append(
                PremiumDiscountBand(
                    zone=self._zone_for_fraction(mid),
                    bottom=dealing_range.price_at(lower),
                    top=dealing_range.price_at(upper),
                    lower_fraction=lower,
                    upper_fraction=upper,
                    label=f"{lower * 100:.0f}-{upper * 100:.0f}%",
                )
            )
        return bands
