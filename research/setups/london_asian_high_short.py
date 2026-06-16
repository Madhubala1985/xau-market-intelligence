"""Setup 2 (v1): London sweep of Asian high -> rejection -> bearish CHOCH -> FVG -> short.

Mirror of Setup 1 on the sell side, with a structural CHOCH gate instead of a
plain displacement: price runs the liquidity above the Asian high, rejects, then
the up-structure breaks to the downside (change of character). The bearish leg
leaves an FVG; we sell the mitigation, stop above the swept high.

EXACT MECHANICAL RULES (v1 — frozen):
  Asian range:    M5 highs/lows in [asian_start_h, asian_end_h) UTC.
  Window:         everything occurs in [london_start_h, london_end_h) UTC.
  No-trade:       skip if < min_asian_candles or Asian range < min_asian_range_usd.
  Sweep:          first London M5 high > Asian high (sweep_high = that high,
                  extended if a later bar prints higher before rejection).
  Rejection:      within reclaim_within bars, a candle CLOSES back below Asian high.
  CHOCH:          MarketStructureEngine detects a BEARISH CHOCH on the London
                  slice at/after the rejection bar (reused canonical engine).
  FVG:            after the CHOCH, the first bearish 3-candle FVG.
  Entry:          pending limit at the FVG bottom (near edge; price rises into it).
  Invalidation:   a new high >= sweep_high before fill voids the intent.
  Expiry:         cancel if unfilled mitigation_within bars after the FVG.
  Stop:           sweep_high + sl_buffer_usd.
  Target:         entry - rr x (stop - entry).
  One trade/day.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from research.setups._common import (
    bear_fvg,
    baseline_range,
    day_midnight,
    group_by_day,
    range_of,
    utc_day,
    window_indices,
)
from research.setups.base import EntryIntent, MarketData
from src.data.enums import Direction
from src.structure.market_structure import (
    Bias,
    MarketStructureEngine,
    StructureEventType,
)


class LondonAsianHighShort:
    name = "london_asian_high_short"
    version = "v1"
    description = (
        "London sweep of Asian high -> rejection -> bearish CHOCH -> "
        "FVG mitigation short; stop above swept high, fixed RR target."
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
        choch_within: int = 10,
        baseline_lookback: int = 20,
        swing_strength: int = 2,
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
        self.choch_within = choch_within
        self.baseline_lookback = baseline_lookback
        self.swing_strength = swing_strength
        self.mitigation_within = mitigation_within
        self.sl_buffer_usd = sl_buffer_usd
        self.rr = rr
        self._structure = MarketStructureEngine(strength=swing_strength)

    def rules(self) -> Dict[str, object]:
        return {
            "name": self.name, "version": self.version, "description": self.description,
            "asian_window_utc": f"[{self.asian_start_h:02d}:00,{self.asian_end_h:02d}:00)",
            "london_window_utc": f"[{self.london_start_h:02d}:00,{self.london_end_h:02d}:00)",
            "min_asian_candles": self.min_asian_candles,
            "min_asian_range_usd": self.min_asian_range_usd,
            "reclaim_within_bars": self.reclaim_within,
            "choch_within_bars": self.choch_within,
            "swing_strength": self.swing_strength,
            "mitigation_within_bars": self.mitigation_within,
            "sl_buffer_usd": self.sl_buffer_usd, "rr": self.rr, "session": "LONDON",
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
        asian = window_indices(candles, idxs, self.asian_start_h, self.asian_end_h)
        if len(asian) < self.min_asian_candles:
            return None
        asian_low, asian_high = range_of(candles, asian)
        if (asian_high - asian_low) < self.min_asian_range_usd:
            return None

        london = window_indices(candles, idxs, self.london_start_h, self.london_end_h)
        if len(london) < self.swing_strength * 2 + 2:
            return None

        # 1) sweep of Asian high
        sweep_pos = next((p for p, i in enumerate(london)
                          if candles[i].high > asian_high), None)
        if sweep_pos is None:
            return None
        sweep_high = candles[london[sweep_pos]].high

        # 2) rejection: close back below Asian high
        reclaim_pos = None
        for p in range(sweep_pos + 1, min(sweep_pos + 1 + self.reclaim_within, len(london))):
            i = london[p]
            sweep_high = max(sweep_high, candles[i].high)
            if candles[i].close < asian_high:
                reclaim_pos = p
                break
        if reclaim_pos is None:
            return None

        # 3) bearish CHOCH on the London slice at/after rejection (canonical engine)
        london_candles = [candles[i] for i in london]
        events = self._structure.analyze(london_candles).events
        choch_pos = next(
            (e.index for e in events
             if e.bias is Bias.BEARISH
             and e.event_type is StructureEventType.CHOCH
             and reclaim_pos <= e.index <= reclaim_pos + self.choch_within),
            None,
        )
        if choch_pos is None:
            return None

        # 4) first bearish FVG at/after the CHOCH bar
        fvg_pos = None
        gap = None
        for p in range(choch_pos, len(london)):
            g = bear_fvg(london_candles, p)
            if g is not None:
                fvg_pos, gap = p, g
                break
        if gap is None:
            return None
        gap_bottom, gap_top = gap
        arm_local = fvg_pos + 1
        if arm_local >= len(london):
            return None
        arm_i = london[arm_local]

        entry_price = gap_bottom            # near edge: price rises into the gap
        stop = sweep_high + self.sl_buffer_usd
        risk = stop - entry_price
        if risk <= 0:
            return None
        target = entry_price - self.rr * risk

        return EntryIntent(
            setup=self.name, version=self.version,
            day=day_midnight(utc_day(candles[arm_i])),
            direction=Direction.SHORT, session="LONDON",
            arm_index=arm_i, arm_time=candles[arm_i].time_utc,
            entry_price=entry_price, stop=stop, target=target,
            invalidation_price=sweep_high,
            expiry_index=arm_i + self.mitigation_within,
            note=(f"swept Asian high {asian_high:.2f} to {sweep_high:.2f}; "
                  f"bearish CHOCH; FVG [{gap_bottom:.2f},{gap_top:.2f}]"),
            context={"asian_high": asian_high, "asian_low": asian_low,
                     "sweep_high": sweep_high, "fvg_bottom": gap_bottom,
                     "fvg_top": gap_top, "risk_usd": risk},
        )
