"""Setup 8 (v1): M5 big-bar mean-reversion — the intraday edge from the scan.

The edge scan showed the OPPOSITE character intraday: on M5, fading a big bar has
positive short-horizon forward return (big_bar_reversion +0.20 ATR over 8 bars,
~55% directional). This setup fades an outsized M5 bar back toward the mean.

EXACT MECHANICAL RULES (v1 — frozen):
  Exec timeframe: M5.
  Signal:         a bar whose move (close-open over its range) exceeds
                  `trigger_atr` x ATR(atr_len) -> fade it (down bar -> long,
                  up bar -> short).
  Entry:          MARKET next bar open.
  Stop / target:  `stop_atr` / `tp_atr` x ATR; optional `max_hold_bars` time stop.
  Cooldown:       `cooldown` bars between entries.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from research.setups.base import EntryIntent, MarketData
from research.setups._common import day_midnight, utc_day
from research.setups.donchian_breakout_trend import _atr
from src.data.enums import Direction, Timeframe


class MeanReversionM5:
    name = "mean_reversion_m5"
    version = "v1"
    description = "M5 big-bar fade (mean reversion); market entry, ATR stop/target."
    exec_timeframe = Timeframe.M5

    def __init__(self, *, atr_len: int = 14, trigger_atr: float = 1.5,
                 stop_atr: float = 1.5, tp_atr: float = 1.5,
                 cooldown: int = 6, max_hold_bars: Optional[int] = 8) -> None:
        self.atr_len = atr_len
        self.trigger_atr = trigger_atr
        self.stop_atr = stop_atr
        self.tp_atr = tp_atr
        self.cooldown = cooldown
        self.max_hold_bars = max_hold_bars

    def rules(self) -> Dict[str, object]:
        return {
            "name": self.name, "version": self.version, "description": self.description,
            "exec_timeframe": "M5", "atr_len": self.atr_len,
            "trigger_atr": self.trigger_atr, "stop_atr": self.stop_atr,
            "tp_atr": self.tp_atr, "cooldown": self.cooldown,
            "max_hold_bars": self.max_hold_bars, "entry": "MARKET next bar",
            "session": "ANY",
        }

    def scan(self, data: MarketData) -> List[EntryIntent]:
        candles = data.tf(Timeframe.M5)
        n = len(candles)
        intents: List[EntryIntent] = []
        last_arm = -10 ** 9
        for i in range(self.atr_len + 1, n - 1):
            atr = _atr(candles, i, self.atr_len)
            if atr is None or atr <= 0:
                continue
            move = candles[i].close - candles[i].open
            if abs(move) < self.trigger_atr * atr:
                continue
            if i - last_arm < self.cooldown:
                continue
            is_long = move < 0                      # fade a down bar -> long
            entry_ref = candles[i + 1].open
            if is_long:
                stop, target = entry_ref - self.stop_atr * atr, entry_ref + self.tp_atr * atr
            else:
                stop, target = entry_ref + self.stop_atr * atr, entry_ref - self.tp_atr * atr
            risk = abs(entry_ref - stop)
            if risk <= 0:
                continue
            intents.append(EntryIntent(
                setup=self.name, version=self.version,
                day=day_midnight(utc_day(candles[i + 1])),
                direction=Direction.LONG if is_long else Direction.SHORT,
                session="ANY", arm_index=i, arm_time=candles[i].time_utc,
                entry_price=entry_ref, stop=stop, target=target,
                invalidation_price=stop, expiry_index=i + 1, entry_type="MARKET",
                max_hold_bars=self.max_hold_bars,
                note=f"fade {'down' if is_long else 'up'} bar {move:+.2f} (ATR {atr:.2f})",
                context={"atr": atr, "risk_usd": risk},
            ))
            last_arm = i
        return intents
