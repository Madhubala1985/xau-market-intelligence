"""FVG / order block / supply-demand zone engine (Task P3-004).

Detects imbalance and origin zones from a Candle series, with mitigation status.
References 02_ARCHITECTURE.md section 7 and 13_XAUUSD_SMC_PLAYBOOK.md.

Zone categories:
- FAIR_VALUE_GAP: a 3-candle imbalance. Bullish FVG when candle[i+1].low is above
  candle[i-1].high (gap left by an up displacement); bearish when
  candle[i+1].high is below candle[i-1].low.
- ORDER_BLOCK: the last opposing candle before a displacement that BREAKS
  structure (reuses the P3-001 structure engine). Bullish OB = last down candle
  before an up break; bearish OB = last up candle before a down break.
- SUPPLY_DEMAND: the base candle immediately before a displacement candle
  (no structure break required). Demand (bullish) precedes an up displacement,
  supply (bearish) precedes a down displacement.

Bias: BULLISH zones are demand/support (rest below price); BEARISH zones are
supply/resistance (rest above price).

Mitigation: a zone is mitigated once a later candle trades back into its range
(overlap). Mitigation is evaluated only from candles after the zone's creation
index, so there is no look-ahead and results are prefix-stable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from src.data.schemas import Candle
from src.structure.market_structure import Bias, MarketStructureEngine


class ZoneKind(str, Enum):
    FAIR_VALUE_GAP = "FAIR_VALUE_GAP"
    ORDER_BLOCK = "ORDER_BLOCK"
    SUPPLY_DEMAND = "SUPPLY_DEMAND"


@dataclass(frozen=True)
class Zone:
    """A detected FVG / order block / supply-demand zone."""

    kind: ZoneKind
    bias: Bias  # BULLISH = demand/support, BEARISH = supply/resistance
    top: float
    bottom: float
    origin_index: int   # candle that forms the zone
    created_index: int  # candle at which the zone becomes known
    created_time: datetime
    mitigated: bool = False
    mitigation_index: Optional[int] = None

    @property
    def size(self) -> float:
        return self.top - self.bottom


class ZoneEngine:
    """Detects FVG, order-block, and supply/demand zones with mitigation."""

    def __init__(
        self,
        *,
        swing_strength: int = 2,
        min_gap: float = 0.0,
        displacement_factor: float = 1.5,
        displacement_lookback: int = 10,
        ob_lookback: int = 10,
    ) -> None:
        if min_gap < 0:
            raise ValueError("min_gap must be >= 0")
        self._structure = MarketStructureEngine(strength=swing_strength)
        self._min_gap = min_gap
        self._displacement_factor = displacement_factor
        self._displacement_lookback = displacement_lookback
        self._ob_lookback = ob_lookback

    def build(self, candles: Sequence[Candle]) -> List[Zone]:
        """Return all detected zones, sorted by creation index."""
        zones = (
            self.find_fvgs(candles)
            + self.find_order_blocks(candles)
            + self.find_supply_demand(candles)
        )
        zones.sort(key=lambda z: (z.created_index, z.kind.value, z.bottom))
        return zones

    # -- fair value gaps ---------------------------------------------------
    def find_fvgs(self, candles: Sequence[Candle]) -> List[Zone]:
        zones: List[Zone] = []
        for i in range(1, len(candles) - 1):
            prev, nxt = candles[i - 1], candles[i + 1]
            created = i + 1
            if nxt.low - prev.high > self._min_gap:  # bullish gap
                zones.append(
                    self._make_zone(
                        candles, ZoneKind.FAIR_VALUE_GAP, Bias.BULLISH,
                        top=nxt.low, bottom=prev.high,
                        origin_index=i, created_index=created,
                    )
                )
            elif prev.low - nxt.high > self._min_gap:  # bearish gap
                zones.append(
                    self._make_zone(
                        candles, ZoneKind.FAIR_VALUE_GAP, Bias.BEARISH,
                        top=prev.low, bottom=nxt.high,
                        origin_index=i, created_index=created,
                    )
                )
        return zones

    # -- order blocks ------------------------------------------------------
    def find_order_blocks(self, candles: Sequence[Candle]) -> List[Zone]:
        zones: List[Zone] = []
        consumed: set = set()
        for ev in self._structure.analyze(candles).events:
            k = ev.index
            want_bearish_candle = ev.bias is Bias.BULLISH  # OB is the opposing candle
            origin = self._last_opposing_candle(candles, k, want_bearish_candle)
            if origin is None or origin in consumed:
                continue
            consumed.add(origin)
            c = candles[origin]
            zones.append(
                self._make_zone(
                    candles, ZoneKind.ORDER_BLOCK, ev.bias,
                    top=c.high, bottom=c.low,
                    origin_index=origin, created_index=k,
                )
            )
        return zones

    def _last_opposing_candle(
        self, candles: Sequence[Candle], k: int, want_bearish: bool
    ) -> Optional[int]:
        start = max(0, k - self._ob_lookback)
        for j in range(k, start - 1, -1):
            c = candles[j]
            is_bearish = c.close < c.open
            is_bullish = c.close > c.open
            if (want_bearish and is_bearish) or (not want_bearish and is_bullish):
                return j
        return None

    # -- supply / demand ---------------------------------------------------
    def find_supply_demand(self, candles: Sequence[Candle]) -> List[Zone]:
        zones: List[Zone] = []
        for d in range(1, len(candles)):
            baseline = self._baseline_range(candles, d)
            disp = candles[d]
            rng = disp.high - disp.low
            if rng < self._displacement_factor * baseline or rng <= 0:
                continue
            base = candles[d - 1]
            if disp.close > disp.open:  # up displacement -> demand below
                bias = Bias.BULLISH
            elif disp.close < disp.open:  # down displacement -> supply above
                bias = Bias.BEARISH
            else:
                continue
            zones.append(
                self._make_zone(
                    candles, ZoneKind.SUPPLY_DEMAND, bias,
                    top=base.high, bottom=base.low,
                    origin_index=d - 1, created_index=d,
                )
            )
        return zones

    # -- helpers -----------------------------------------------------------
    def _make_zone(
        self,
        candles: Sequence[Candle],
        kind: ZoneKind,
        bias: Bias,
        *,
        top: float,
        bottom: float,
        origin_index: int,
        created_index: int,
    ) -> Zone:
        mitigated, mit_index = self._mitigation(candles, created_index, top, bottom)
        return Zone(
            kind=kind,
            bias=bias,
            top=top,
            bottom=bottom,
            origin_index=origin_index,
            created_index=created_index,
            created_time=candles[created_index].time_utc,
            mitigated=mitigated,
            mitigation_index=mit_index,
        )

    @staticmethod
    def _mitigation(
        candles: Sequence[Candle], created_index: int, top: float, bottom: float
    ) -> Tuple[bool, Optional[int]]:
        for j in range(created_index + 1, len(candles)):
            c = candles[j]
            if c.low <= top and c.high >= bottom:  # candle overlaps the zone
                return True, j
        return False, None

    def _baseline_range(self, candles: Sequence[Candle], i: int) -> float:
        start = max(0, i - self._displacement_lookback)
        prior = candles[start:i]
        if not prior:
            return candles[i].high - candles[i].low
        return sum(c.high - c.low for c in prior) / len(prior)
