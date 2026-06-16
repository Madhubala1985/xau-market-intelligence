"""Setup 3 (v1): NY sweep of London high/low -> failed continuation -> reversal.

During the New York session price often runs the London-session high or low,
fails to continue (closes back inside the London range), then displaces in the
OPPOSITE direction. We trade the reversal on the FVG that displacement leaves.

EXACT MECHANICAL RULES (v1 — frozen):
  London range:   M5 high/low in [london_start_h, london_end_h) UTC.
  NY window:       everything below occurs in [ny_start_h, ny_end_h) UTC.
  No-trade:        skip if < min_london_candles or London range < min_range_usd.
  Sweep:           first NY M5 bar whose HIGH > London high (short side) or whose
                   LOW < London low (long side); take whichever happens first.
  Failed continuation: within reclaim_within bars, a candle CLOSES back inside the
                   London range (below London high for the high-sweep; above London
                   low for the low-sweep).
  Reversal displacement: after the failure, a displacement candle in the reversal
                   direction (range >= displacement_factor x baseline) leaving an FVG.
  Entry:           pending limit at the FVG near edge (mitigation).
  Invalidation:    a new extreme beyond the swept level before fill voids the intent.
  Expiry:          cancel if unfilled mitigation_within bars after the FVG.
  Stop:            beyond the swept extreme by sl_buffer_usd.
  Target:          fixed rr.
  One trade/day (first valid; high-sweep short is checked before low-sweep long).
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
    range_of,
    utc_day,
    window_indices,
)
from research.setups.base import EntryIntent, MarketData
from src.data.enums import Direction


class NyLondonSweepReversal:
    name = "ny_london_sweep_reversal"
    version = "v1"
    description = (
        "NY sweep of London high/low -> failed continuation -> reversal "
        "displacement -> FVG mitigation; stop beyond the swept extreme."
    )

    def __init__(
        self,
        *,
        london_start_h: int = 7,
        london_end_h: int = 12,
        ny_start_h: int = 12,
        ny_end_h: int = 16,
        min_london_candles: int = 24,
        min_range_usd: float = 2.0,
        reclaim_within: int = 6,
        baseline_lookback: int = 20,
        displacement_factor: float = 1.5,
        mitigation_within: int = 12,
        sl_buffer_usd: float = 0.10,
        rr: float = 2.0,
    ) -> None:
        self.london_start_h = london_start_h
        self.london_end_h = london_end_h
        self.ny_start_h = ny_start_h
        self.ny_end_h = ny_end_h
        self.min_london_candles = min_london_candles
        self.min_range_usd = min_range_usd
        self.reclaim_within = reclaim_within
        self.baseline_lookback = baseline_lookback
        self.displacement_factor = displacement_factor
        self.mitigation_within = mitigation_within
        self.sl_buffer_usd = sl_buffer_usd
        self.rr = rr

    def rules(self) -> Dict[str, object]:
        return {
            "name": self.name, "version": self.version, "description": self.description,
            "london_window_utc": f"[{self.london_start_h:02d}:00,{self.london_end_h:02d}:00)",
            "ny_window_utc": f"[{self.ny_start_h:02d}:00,{self.ny_end_h:02d}:00)",
            "min_london_candles": self.min_london_candles,
            "min_range_usd": self.min_range_usd,
            "reclaim_within_bars": self.reclaim_within,
            "displacement_factor": self.displacement_factor,
            "mitigation_within_bars": self.mitigation_within,
            "sl_buffer_usd": self.sl_buffer_usd, "rr": self.rr, "session": "NEW_YORK",
        }

    def scan(self, data: MarketData) -> List[EntryIntent]:
        candles = data.exec_candles
        if not candles:
            return []
        intents: List[EntryIntent] = []
        for _, idxs in group_by_day(candles).items():
            intent = self._scan_day(candles, idxs)
            if intent is not None:
                intents.append(intent)
        return intents

    def _scan_day(self, candles, idxs) -> Optional[EntryIntent]:
        london = window_indices(candles, idxs, self.london_start_h, self.london_end_h)
        if len(london) < self.min_london_candles:
            return None
        london_low, london_high = range_of(candles, london)
        if (london_high - london_low) < self.min_range_usd:
            return None
        ny = window_indices(candles, idxs, self.ny_start_h, self.ny_end_h)
        if not ny:
            return None

        # Find the first sweep (either side) and its direction.
        for pos, i in enumerate(ny):
            if candles[i].high > london_high:
                return self._reversal(candles, ny, pos, Direction.SHORT,
                                      level=london_high, london_low=london_low,
                                      london_high=london_high)
            if candles[i].low < london_low:
                return self._reversal(candles, ny, pos, Direction.LONG,
                                      level=london_low, london_low=london_low,
                                      london_high=london_high)
        return None

    def _reversal(self, candles, ny, sweep_pos, direction, *, level,
                  london_low, london_high) -> Optional[EntryIntent]:
        is_long = direction == Direction.LONG
        extreme = candles[ny[sweep_pos]].low if is_long else candles[ny[sweep_pos]].high

        # failed continuation: close back inside the London range
        fail_pos = None
        for p in range(sweep_pos + 1, min(sweep_pos + 1 + self.reclaim_within, len(ny))):
            i = ny[p]
            if is_long:
                extreme = min(extreme, candles[i].low)
                if candles[i].close > london_low:
                    fail_pos = p
                    break
            else:
                extreme = max(extreme, candles[i].high)
                if candles[i].close < london_high:
                    fail_pos = p
                    break
        if fail_pos is None:
            return None

        # reversal displacement leaving an FVG
        fvg_pos = None
        gap = None
        for p in range(fail_pos, len(ny)):
            i = ny[p]
            baseline = baseline_range(candles, i, self.baseline_lookback)
            if baseline is None:
                continue
            c = candles[i]
            if is_long and is_bull_displacement(c, baseline, self.displacement_factor):
                g = bull_fvg(candles, i)
                if g:
                    fvg_pos, gap = p, g
                    break
            if (not is_long) and is_bear_displacement(c, baseline, self.displacement_factor):
                g = bear_fvg(candles, i)
                if g:
                    fvg_pos, gap = p, g
                    break
        if gap is None:
            return None

        disp_i = ny[fvg_pos]
        arm_i = disp_i + 1
        if arm_i >= len(candles):
            return None
        gap_bottom, gap_top = gap
        if is_long:
            entry_price = gap_top                       # price falls into gap
            stop = extreme - self.sl_buffer_usd
            risk = entry_price - stop
            target = entry_price + self.rr * risk if risk > 0 else 0.0
            invalidation = extreme
        else:
            entry_price = gap_bottom                     # price rises into gap
            stop = extreme + self.sl_buffer_usd
            risk = stop - entry_price
            target = entry_price - self.rr * risk if risk > 0 else 0.0
            invalidation = extreme
        if risk <= 0:
            return None

        return EntryIntent(
            setup=self.name, version=self.version,
            day=day_midnight(utc_day(candles[arm_i])),
            direction=direction, session="NEW_YORK",
            arm_index=arm_i, arm_time=candles[arm_i].time_utc,
            entry_price=entry_price, stop=stop, target=target,
            invalidation_price=invalidation,
            expiry_index=arm_i + self.mitigation_within,
            note=(f"NY swept London {'low' if is_long else 'high'} {level:.2f} to "
                  f"{extreme:.2f}; failed continuation; reversal FVG "
                  f"[{gap_bottom:.2f},{gap_top:.2f}]"),
            context={"london_high": london_high, "london_low": london_low,
                     "swept_extreme": extreme, "fvg_bottom": gap_bottom,
                     "fvg_top": gap_top, "risk_usd": risk},
        )
