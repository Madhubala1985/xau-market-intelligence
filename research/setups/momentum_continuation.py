"""Setup 6 (v1): session-agnostic momentum continuation (H1-aligned displacement+FVG).

Built to test the owner's hypothesis: momentum can come at ANY time, so a setup
should not be boxed into London/NY windows. This one runs 24h (whenever the
market trades) and can fire multiple times a day.

Thesis: when the H1 trend is established, a strong M5 displacement in the trend
direction that leaves an FVG marks a momentum leg; price retraces into the FVG
and continues. We trade the continuation, stop beyond the displacement leg, and
target a larger multiple (momentum legs tend to run, so rr defaults to 3.0).

EXACT MECHANICAL RULES (v1 — frozen; principled defaults, NOT tuned to any day):
  HTF context:    most recent CLOSED H1 BOS/CHOCH bias (MarketStructureEngine).
  Window:         24h (active_start_h=0, active_end_h=24) — session-agnostic.
  Momentum:       M5 candle in the trend direction with range >=
                  displacement_factor x baseline (default 2.0 — stronger than the
                  killzone setups' 1.5), leaving a trend-direction FVG.
  Entry:          pending limit at the FVG near edge (continuation retest).
  Stop:           beyond the displacement leg (3-candle) by sl_buffer_usd.
  Invalidation:   price trading beyond the leg extreme before fill voids it.
  Expiry:         cancel if unfilled mitigation_within bars after the FVG.
  Target:         entry +/- rr x risk (rr default 3.0 to let momentum run).
  Cadence:        multiple per day, but a cooldown of `cooldown_bars` after each
                  arm prevents stacking many intents on the same leg.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from research.setups._common import (
    baseline_range,
    bear_fvg,
    bull_fvg,
    day_midnight,
    is_bear_displacement,
    is_bull_displacement,
    utc_day,
    utc_hour,
)
from research.setups.base import EntryIntent, MarketData
from src.data.enums import Direction, Timeframe
from src.structure.market_structure import Bias, MarketStructureEngine


class MomentumContinuation:
    name = "momentum_continuation"
    version = "v1"
    description = (
        "Session-agnostic: H1 trend + strong M5 displacement leaving an FVG -> "
        "continuation entry on FVG retest; stop beyond the leg; rr=3 to run."
    )

    def __init__(
        self,
        *,
        active_start_h: int = 0,
        active_end_h: int = 24,
        baseline_lookback: int = 20,
        displacement_factor: float = 2.0,
        swing_strength: int = 2,
        mitigation_within: int = 12,
        cooldown_bars: int = 12,
        sl_buffer_usd: float = 0.10,
        rr: float = 3.0,
    ) -> None:
        self.active_start_h = active_start_h
        self.active_end_h = active_end_h
        self.baseline_lookback = baseline_lookback
        self.displacement_factor = displacement_factor
        self.swing_strength = swing_strength
        self.mitigation_within = mitigation_within
        self.cooldown_bars = cooldown_bars
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
            "cooldown_bars": self.cooldown_bars,
            "sl_buffer_usd": self.sl_buffer_usd, "rr": self.rr,
            "session": "ANY", "cadence": "multiple per day",
        }

    def scan(self, data: MarketData) -> List[EntryIntent]:
        candles = data.exec_candles
        h1 = data.tf(Timeframe.H1)
        if not candles or not h1:
            return []
        h1_events = self._structure.analyze(h1).events
        events_by_time = sorted((h1[e.index].time_utc, e.bias) for e in h1_events)

        intents: List[EntryIntent] = []
        last_arm = -10 ** 9
        for i in range(self.baseline_lookback, len(candles) - 1):
            if not (self.active_start_h <= utc_hour(candles[i]) < self.active_end_h):
                continue
            if i - last_arm < self.cooldown_bars:
                continue
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
            leg_lo = min(candles[i - 1].low, c.low, candles[i + 1].low)
            leg_hi = max(candles[i - 1].high, c.high, candles[i + 1].high)
            gap_bottom, gap_top = gap
            if is_long:
                entry_price, stop, invalidation = gap_top, leg_lo - self.sl_buffer_usd, leg_lo
                risk = entry_price - stop
                target = entry_price + self.rr * risk
            else:
                entry_price, stop, invalidation = gap_bottom, leg_hi + self.sl_buffer_usd, leg_hi
                risk = stop - entry_price
                target = entry_price - self.rr * risk
            if risk <= 0:
                continue

            intents.append(EntryIntent(
                setup=self.name, version=self.version,
                day=day_midnight(utc_day(candles[arm_i])),
                direction=Direction.LONG if is_long else Direction.SHORT,
                session="ANY", arm_index=arm_i, arm_time=candles[arm_i].time_utc,
                entry_price=entry_price, stop=stop, target=target,
                invalidation_price=invalidation,
                expiry_index=arm_i + self.mitigation_within,
                note=(f"H1 {trend.value}; M5 momentum displacement+FVG "
                      f"[{gap_bottom:.2f},{gap_top:.2f}] rr={self.rr}"),
                context={"trend": 1.0 if is_long else -1.0, "fvg_bottom": gap_bottom,
                         "fvg_top": gap_top, "risk_usd": risk},
            ))
            last_arm = i
        return intents

    def _trend_at(self, events_by_time, when) -> Bias:
        trend = Bias.NEUTRAL
        for t, bias in events_by_time:
            if t <= when:
                trend = bias
            else:
                break
        return trend
