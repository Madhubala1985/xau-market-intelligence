"""Setup 1 (v1): London sweep of Asian low -> reclaim -> displacement -> FVG -> long.

Plain-English thesis: during the London killzone, price often runs the liquidity
resting below the Asian-session low, then reclaims it and displaces up. The
displacement leaves a bullish fair-value gap; price retraces into that gap
(mitigation) before continuing up. We buy the mitigation, stop below the swept
low, target a fixed R multiple.

EXACT MECHANICAL RULES (v1 — frozen; any change is a NEW version):

  Timezone:           all times UTC (06_DATA_POLICY.md single internal tz).
  Exec timeframe:     M5.
  Asian range:        highs/lows of M5 candles in [asian_start_h, asian_end_h).
  No-trade filters:   skip the day if fewer than `min_asian_candles` Asian bars,
                      or Asian range < `min_asian_range_usd` (chop/illiquid).
  Window:             sweep, reclaim, displacement and entry must all occur in
                      [london_start_h, london_end_h).
  Sweep condition:    an M5 candle's LOW prints below the Asian low
                      (penetration > 0). `sweep_low` = that candle's low.
  Reclaim condition:  within `reclaim_within` bars after the sweep, an M5 candle
                      CLOSES back above the Asian low.
  Displacement:       after reclaim, a bullish M5 candle (close > open) whose
                      range >= `displacement_factor` x the average range of the
                      prior `baseline_lookback` bars, closing above the Asian low.
  FVG condition:      the displacement leg leaves a bullish 3-candle fair-value
                      gap: candle[d+1].low > candle[d-1].high. Gap = the zone
                      [d-1.high, d+1.low]. (Same definition as ZoneEngine.find_fvgs.)
  Entry rule:         pending limit at the gap TOP (= candle[d+1].low); fills when
                      price retraces down and trades into it (mitigation).
  Invalidation:       if price makes a new low <= `sweep_low` before the limit
                      fills, the intent is voided (the sweep failed).
  Expiry:             cancel if unfilled `mitigation_within` bars after the gap.
  Stop rule:          `sweep_low` - `sl_buffer_usd`.
  Target rule:        entry + `rr` x (entry - stop)   (fixed R; no trailing in v1).
  One trade per day:  first valid intent only.

Causality: the intent is armed at the gap-confirmation bar (d+1) and references
only candles up to d+1. The harness simulates the fill and exit strictly forward.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from research.setups.base import EntryIntent, MarketData
from src.data.enums import Direction, Timeframe
from src.data.schemas import Candle


def _day(c: Candle) -> datetime.date:
    return c.time_utc.astimezone(timezone.utc).date()


def _hour(c: Candle) -> int:
    return c.time_utc.astimezone(timezone.utc).hour


class LondonSweepReclaimLong:
    name = "london_sweep_reclaim_long"
    version = "v1"
    description = (
        "London sweep of Asian low -> reclaim -> bullish displacement -> "
        "FVG mitigation long; stop below swept low, fixed RR target."
    )

    def __init__(
        self,
        *,
        asian_start_h: int = 0,
        asian_end_h: int = 7,
        london_start_h: int = 7,
        london_end_h: int = 11,
        min_asian_candles: int = 12,
        min_asian_range_usd: float = 1.5,
        reclaim_within: int = 6,
        baseline_lookback: int = 20,
        displacement_factor: float = 1.5,
        mitigation_within: int = 12,
        sl_buffer_usd: float = 0.10,
        rr: float = 2.0,
    ) -> None:
        self.asian_start_h = asian_start_h
        self.asian_end_h = asian_end_h
        self.london_start_h = london_start_h
        self.london_end_h = london_end_h
        self.min_asian_candles = min_asian_candles
        self.min_asian_range_usd = min_asian_range_usd
        self.reclaim_within = reclaim_within
        self.baseline_lookback = baseline_lookback
        self.displacement_factor = displacement_factor
        self.mitigation_within = mitigation_within
        self.sl_buffer_usd = sl_buffer_usd
        self.rr = rr

    def rules(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "asian_window_utc": f"[{self.asian_start_h:02d}:00, {self.asian_end_h:02d}:00)",
            "london_window_utc": f"[{self.london_start_h:02d}:00, {self.london_end_h:02d}:00)",
            "min_asian_candles": self.min_asian_candles,
            "min_asian_range_usd": self.min_asian_range_usd,
            "reclaim_within_bars": self.reclaim_within,
            "displacement_factor": self.displacement_factor,
            "baseline_lookback": self.baseline_lookback,
            "mitigation_within_bars": self.mitigation_within,
            "sl_buffer_usd": self.sl_buffer_usd,
            "rr": self.rr,
            "session": "LONDON",
        }

    def _baseline_range(self, candles: List[Candle], idx: int) -> Optional[float]:
        lo = max(0, idx - self.baseline_lookback)
        window = candles[lo:idx]
        if len(window) < max(3, self.baseline_lookback // 2):
            return None
        return sum(c.high - c.low for c in window) / len(window)

    def scan(self, data: MarketData) -> List[EntryIntent]:
        candles = data.exec_candles
        if not candles:
            return []

        # Group exec candles by UTC day, preserving global indices.
        by_day: Dict[datetime.date, List[int]] = {}
        for i, c in enumerate(candles):
            by_day.setdefault(_day(c), []).append(i)

        intents: List[EntryIntent] = []
        for day, idxs in by_day.items():
            intent = self._scan_day(candles, idxs)
            if intent is not None:
                intents.append(intent)
        return intents

    def _scan_day(self, candles: List[Candle], idxs: List[int]) -> Optional[EntryIntent]:
        asian = [
            i for i in idxs
            if self.asian_start_h <= _hour(candles[i]) < self.asian_end_h
        ]
        if len(asian) < self.min_asian_candles:
            return None
        asian_low = min(candles[i].low for i in asian)
        asian_high = max(candles[i].high for i in asian)
        if (asian_high - asian_low) < self.min_asian_range_usd:
            return None

        london = [
            i for i in idxs
            if self.london_start_h <= _hour(candles[i]) < self.london_end_h
        ]
        if not london:
            return None

        # 1) Sweep: first London bar whose low prints below the Asian low.
        sweep_pos = None
        for pos, i in enumerate(london):
            if candles[i].low < asian_low:
                sweep_pos = pos
                break
        if sweep_pos is None:
            return None
        sweep_i = london[sweep_pos]
        sweep_low = candles[sweep_i].low

        # 2) Reclaim: a close back above the Asian low within reclaim_within bars.
        reclaim_pos = None
        for pos in range(sweep_pos + 1, min(sweep_pos + 1 + self.reclaim_within, len(london))):
            i = london[pos]
            if candles[i].low < sweep_low:          # deeper low -> sweep extends
                sweep_low = candles[i].low
            if candles[i].close > asian_low:
                reclaim_pos = pos
                break
        if reclaim_pos is None:
            return None

        # 3) Displacement: bullish, range >= factor x baseline, closing above Asian low.
        disp_pos = None
        for pos in range(reclaim_pos, len(london)):
            i = london[pos]
            baseline = self._baseline_range(candles, i)
            if baseline is None:
                continue
            c = candles[i]
            rng = c.high - c.low
            if c.close > c.open and rng >= self.displacement_factor * baseline and c.close > asian_low:
                disp_pos = pos
                break
        if disp_pos is None:
            return None
        disp_i = london[disp_pos]

        # 4) FVG: bullish 3-candle gap around the displacement candle.
        if disp_i - 1 < 0 or disp_i + 1 >= len(candles):
            return None
        prev_c, next_c = candles[disp_i - 1], candles[disp_i + 1]
        gap_bottom, gap_top = prev_c.high, next_c.low
        if gap_top <= gap_bottom:                    # no real gap -> no setup
            return None

        # Arm at the gap-confirmation bar (disp_i + 1); only past data used.
        arm_i = disp_i + 1
        entry_price = gap_top
        stop = sweep_low - self.sl_buffer_usd
        risk = entry_price - stop
        if risk <= 0:
            return None
        target = entry_price + self.rr * risk

        return EntryIntent(
            setup=self.name,
            version=self.version,
            day=datetime(_day(candles[arm_i]).year, _day(candles[arm_i]).month,
                         _day(candles[arm_i]).day, tzinfo=timezone.utc),
            direction=Direction.LONG,
            session="LONDON",
            arm_index=arm_i,
            arm_time=candles[arm_i].time_utc,
            entry_price=entry_price,
            stop=stop,
            target=target,
            invalidation_price=sweep_low,
            expiry_index=arm_i + self.mitigation_within,
            note=(
                f"swept Asian low {asian_low:.2f} to {sweep_low:.2f}; reclaim+disp; "
                f"FVG [{gap_bottom:.2f},{gap_top:.2f}]"
            ),
            context={
                "asian_low": asian_low,
                "asian_high": asian_high,
                "asian_range": asian_high - asian_low,
                "sweep_low": sweep_low,
                "fvg_bottom": gap_bottom,
                "fvg_top": gap_top,
                "risk_usd": risk,
            },
        )
