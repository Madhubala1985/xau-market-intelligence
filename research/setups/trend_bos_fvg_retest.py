"""Setup 4 (v1): trend-day continuation after H1 BOS -> M5 FVG retest.

Higher-timeframe context sets direction: the most recent H1 structure break
(BOS/CHOCH) that is already CLOSED defines the trend. On M5, within the active
session, the first displacement in the trend direction that leaves an FVG is
traded on its retest (continuation), stopping beyond the displacement leg.

EXACT MECHANICAL RULES (v1 — frozen):
  HTF context:    MarketStructureEngine on H1. Trend = bias of the most recent H1
                  BOS/CHOCH whose break candle has CLOSED at/before the M5 arm bar
                  (strict causality across timeframes — the H1 bar must be done).
  Active window:  M5 bars in [active_start_h, active_end_h) UTC.
  Displacement:   first M5 candle in the trend direction with range >=
                  displacement_factor x baseline, leaving an FVG in that direction.
  Entry:          pending limit at the FVG near edge (continuation retest).
  Stop:           beyond the displacement leg low/high by sl_buffer_usd.
  Invalidation:   price trading beyond the leg extreme before fill voids the intent.
  Expiry:         cancel if unfilled mitigation_within bars after the FVG.
  Target:         fixed rr.
  One trade/day (first valid in the trend direction).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from research.setups._common import (
    baseline_range,
    bear_fvg,
    bull_fvg,
    day_midnight,
    group_by_day,
    is_bear_displacement,
    is_bull_displacement,
    utc_day,
    window_indices,
)
from research.setups.base import EntryIntent, MarketData
from src.data.enums import Direction, Timeframe
from src.structure.market_structure import Bias, MarketStructureEngine


class TrendBosFvgRetest:
    name = "trend_bos_fvg_retest"
    version = "v1"
    description = (
        "H1 BOS sets trend -> first M5 displacement+FVG in trend direction -> "
        "continuation entry on FVG retest; stop beyond the displacement leg."
    )

    def __init__(
        self,
        *,
        active_start_h: int = 7,
        active_end_h: int = 16,
        baseline_lookback: int = 20,
        displacement_factor: float = 1.5,
        swing_strength: int = 2,
        mitigation_within: int = 12,
        sl_buffer_usd: float = 0.10,
        rr: float = 2.0,
    ) -> None:
        self.active_start_h = active_start_h
        self.active_end_h = active_end_h
        self.baseline_lookback = baseline_lookback
        self.displacement_factor = displacement_factor
        self.swing_strength = swing_strength
        self.mitigation_within = mitigation_within
        self.sl_buffer_usd = sl_buffer_usd
        self.rr = rr
        self._structure = MarketStructureEngine(strength=swing_strength)

    def rules(self) -> Dict[str, object]:
        return {
            "name": self.name, "version": self.version, "description": self.description,
            "active_window_utc": f"[{self.active_start_h:02d}:00,{self.active_end_h:02d}:00)",
            "htf": "H1 BOS/CHOCH",
            "displacement_factor": self.displacement_factor,
            "swing_strength": self.swing_strength,
            "mitigation_within_bars": self.mitigation_within,
            "sl_buffer_usd": self.sl_buffer_usd, "rr": self.rr, "session": "TREND_DAY",
        }

    def scan(self, data: MarketData) -> List[EntryIntent]:
        candles = data.exec_candles
        h1 = data.tf(Timeframe.H1)
        if not candles or not h1:
            return []
        # Precompute H1 structure events (causal: each event carries its H1 time).
        h1_events = self._structure.analyze(h1).events
        # Sorted by the time the break is known; we pick the latest <= arm time.
        events_by_time = [(h1[e.index].time_utc, e.bias) for e in h1_events]
        events_by_time.sort()

        intents: List[EntryIntent] = []
        for _, idxs in group_by_day(candles).items():
            intent = self._scan_day(candles, idxs, events_by_time)
            if intent is not None:
                intents.append(intent)
        return intents

    def _trend_at(self, events_by_time, when) -> Bias:
        """Bias of the most recent H1 break whose candle closed at/before `when`."""
        trend = Bias.NEUTRAL
        for t, bias in events_by_time:
            if t <= when:
                trend = bias
            else:
                break
        return trend

    def _scan_day(self, candles, idxs, events_by_time) -> Optional[EntryIntent]:
        active = window_indices(candles, idxs, self.active_start_h, self.active_end_h)
        if len(active) < self.baseline_lookback // 2 + 2:
            return None

        for pos, i in enumerate(active):
            trend = self._trend_at(events_by_time, candles[i].time_utc)
            if trend is Bias.NEUTRAL:
                continue
            baseline = baseline_range(candles, i, self.baseline_lookback)
            if baseline is None:
                continue
            c = candles[i]
            is_long = trend is Bias.BULLISH
            if is_long and is_bull_displacement(c, baseline, self.displacement_factor):
                gap = bull_fvg(candles, i)
            elif (not is_long) and is_bear_displacement(c, baseline, self.displacement_factor):
                gap = bear_fvg(candles, i)
            else:
                continue
            if gap is None:
                continue

            arm_i = i + 1
            if arm_i >= len(candles):
                return None
            leg_lo = min(candles[i - 1].low, c.low, candles[i + 1].low)
            leg_hi = max(candles[i - 1].high, c.high, candles[i + 1].high)
            gap_bottom, gap_top = gap
            if is_long:
                entry_price = gap_top
                stop = leg_lo - self.sl_buffer_usd
                risk = entry_price - stop
                target = entry_price + self.rr * risk if risk > 0 else 0.0
                invalidation = leg_lo
            else:
                entry_price = gap_bottom
                stop = leg_hi + self.sl_buffer_usd
                risk = stop - entry_price
                target = entry_price - self.rr * risk if risk > 0 else 0.0
                invalidation = leg_hi
            if risk <= 0:
                return None

            return EntryIntent(
                setup=self.name, version=self.version,
                day=day_midnight(utc_day(candles[arm_i])),
                direction=Direction.LONG if is_long else Direction.SHORT,
                session="TREND_DAY",
                arm_index=arm_i, arm_time=candles[arm_i].time_utc,
                entry_price=entry_price, stop=stop, target=target,
                invalidation_price=invalidation,
                expiry_index=arm_i + self.mitigation_within,
                note=(f"H1 trend {trend.value}; M5 displacement+FVG "
                      f"[{gap_bottom:.2f},{gap_top:.2f}] continuation retest"),
                context={"trend": 1.0 if is_long else -1.0,
                         "fvg_bottom": gap_bottom, "fvg_top": gap_top,
                         "risk_usd": risk},
            )
        return None
