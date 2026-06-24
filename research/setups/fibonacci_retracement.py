"""Setup 9 (v1): mechanical Fibonacci-retracement continuation.

Fully mechanical, no discretion:
  1. Swing highs/lows from MarketStructureEngine (configurable swing_strength).
  2. Trend confirmation: a down-leg counts only after a LOWER HIGH + LOWER LOW
     (mirror: up-leg needs HIGHER HIGH + HIGHER LOW).
  3. Fib drawn on the last completed swing leg (impulse high<->low).
  4. Entry trigger = price TAGS the [0.5, 0.786] retracement zone, THEN an
     explicit confirmation: a candle CLOSES back through the 0.5 level (rejection).
     No "reaction"/discretion. Entry is MARKET on the next bar's open.
  5. Stop fixed beyond the swing (origin of the impulse) + buffer; target at a
     fixed R-multiple. Leg invalidated if price breaks the swing before confirming,
     or if no confirmation within `confirm_within` bars of the leg completing.

Down-leg (downtrend) -> SHORT the retracement; up-leg (uptrend) -> LONG. One
entry per completed leg.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from research.setups._common import day_midnight, utc_day
from research.setups.base import EntryIntent, MarketData
from src.data.enums import Direction, Timeframe
from src.data.schemas import Candle
from src.structure.market_structure import MarketStructureEngine, SwingType


class FibonacciRetracement:
    name = "fibonacci_retracement"
    version = "v1"
    description = (
        "Mechanical Fib retracement: swing detection -> trend (LH+LL / HH+HL) -> "
        "tag 0.5-0.786 zone -> close back through 0.5 -> market entry; stop beyond "
        "swing, fixed RR."
    )
    exec_timeframe = Timeframe.H1

    def __init__(
        self,
        *,
        swing_strength: int = 3,
        exec_timeframe: Timeframe = Timeframe.H1,
        fib_near: float = 0.5,
        fib_far: float = 0.786,
        confirm_level: float = 0.5,
        confirm_within: int = 24,
        sl_buffer_usd: float = 0.10,
        rr: float = 2.0,
        require_trend: bool = True,
    ) -> None:
        self.swing_strength = swing_strength
        self.exec_timeframe = exec_timeframe
        self.fib_near = fib_near
        self.fib_far = fib_far
        self.confirm_level = confirm_level
        self.confirm_within = confirm_within
        self.sl_buffer_usd = sl_buffer_usd
        self.rr = rr
        self.require_trend = require_trend
        self._engine = MarketStructureEngine(strength=swing_strength)

    def rules(self) -> Dict[str, object]:
        return {
            "name": self.name, "version": self.version, "description": self.description,
            "exec_timeframe": self.exec_timeframe.value,
            "swing_strength": self.swing_strength,
            "fib_zone": f"[{self.fib_near}, {self.fib_far}]",
            "confirm_level": self.confirm_level,
            "confirm_within_bars": self.confirm_within,
            "sl_buffer_usd": self.sl_buffer_usd, "rr": self.rr,
            "require_trend": self.require_trend, "entry": "MARKET next bar",
            "session": "ANY",
        }

    def scan(self, data: MarketData) -> List[EntryIntent]:
        candles = data.tf(self.exec_timeframe)
        if len(candles) < self.swing_strength * 2 + 4:
            return []
        swings = self._engine.find_swings(candles)  # confirmed, causal (sorted)

        intents: List[EntryIntent] = []
        last_high = last_low = prev_high = prev_low = None
        for sp in swings:
            if sp.swing_type is SwingType.HIGH:
                prev_high, last_high = last_high, sp
            else:
                prev_low, last_low = last_low, sp

            # Down-leg completes when a LOW confirms after a HIGH.
            if (sp.swing_type is SwingType.LOW and last_high is not None
                    and last_high.index < sp.index):
                trend_ok = (not self.require_trend) or (
                    prev_high is not None and prev_low is not None
                    and last_high.price < prev_high.price   # lower high
                    and sp.price < prev_low.price)           # lower low
                if trend_ok:
                    it = self._scan_leg(candles, Direction.SHORT,
                                        high=last_high.price, low=sp.price,
                                        start_idx=sp.confirmed_index)
                    if it is not None:
                        intents.append(it)

            # Up-leg completes when a HIGH confirms after a LOW.
            if (sp.swing_type is SwingType.HIGH and last_low is not None
                    and last_low.index < sp.index):
                trend_ok = (not self.require_trend) or (
                    prev_low is not None and prev_high is not None
                    and last_low.price > prev_low.price       # higher low
                    and sp.price > prev_high.price)           # higher high
                if trend_ok:
                    it = self._scan_leg(candles, Direction.LONG,
                                        high=sp.price, low=last_low.price,
                                        start_idx=sp.confirmed_index)
                    if it is not None:
                        intents.append(it)
        return intents

    def _scan_leg(self, candles: List[Candle], direction: Direction,
                  *, high: float, low: float, start_idx: int) -> Optional[EntryIntent]:
        rng = high - low
        if rng <= 0:
            return None
        is_short = direction == Direction.SHORT
        # Retracement levels (fraction of the impulse retraced back).
        if is_short:                         # down-impulse: retrace UP from low
            zone_enter = low + self.fib_near * rng     # 0.5 level
            confirm_px = low + self.confirm_level * rng
        else:                                 # up-impulse: retrace DOWN from high
            zone_enter = high - self.fib_near * rng
            confirm_px = high - self.confirm_level * rng

        tagged = False
        end = min(start_idx + 1 + self.confirm_within, len(candles))
        for i in range(start_idx + 1, end):
            c = candles[i]
            if is_short:
                if c.high > high:             # swing broken -> leg invalid
                    return None
                if c.high >= zone_enter:
                    tagged = True
                if tagged and c.close < confirm_px and i + 1 < len(candles):
                    return self._intent(candles, i, direction, high, low)
            else:
                if c.low < low:
                    return None
                if c.low <= zone_enter:
                    tagged = True
                if tagged and c.close > confirm_px and i + 1 < len(candles):
                    return self._intent(candles, i, direction, high, low)
        return None

    def _intent(self, candles, arm_i, direction, high, low) -> Optional[EntryIntent]:
        is_short = direction == Direction.SHORT
        entry_ref = candles[arm_i + 1].open
        if is_short:
            stop = high + self.sl_buffer_usd
            risk = stop - entry_ref
            target = entry_ref - self.rr * risk
        else:
            stop = low - self.sl_buffer_usd
            risk = entry_ref - stop
            target = entry_ref + self.rr * risk
        if risk <= 0:
            return None
        return EntryIntent(
            setup=self.name, version=self.version,
            day=day_midnight(utc_day(candles[arm_i + 1])),
            direction=direction, session="ANY",
            arm_index=arm_i, arm_time=candles[arm_i].time_utc,
            entry_price=entry_ref, stop=stop, target=target,
            invalidation_price=stop, expiry_index=arm_i + 1, entry_type="MARKET",
            note=(f"fib {'short' if is_short else 'long'} leg H={high:.2f} L={low:.2f}; "
                  f"tagged 0.5-{self.fib_far} zone; close back through {self.confirm_level}"),
            context={"swing_high": high, "swing_low": low, "risk_usd": risk,
                     "trend": -1.0 if is_short else 1.0},
        )
