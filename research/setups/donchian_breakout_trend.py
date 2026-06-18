"""Setup 7 (v1): H1 Donchian breakout trend-continuation — the data-chosen edge.

The edge scan (scripts/edge_scan.py) over 2 years of H1 gold showed ONE strong,
sample-large, horizon-growing directional edge: a close beyond the prior 20-bar
high/low keeps going (+0.60 ATR over 24h, 55.5% directional, n=1478), while
mean-reversion on H1 loses. This setup trades exactly that and nothing else.

EXACT MECHANICAL RULES (v1 — frozen; standard low-DOF params, not fished):
  Exec timeframe: H1.
  Breakout:       FRESH close above the prior `lookback`-bar high -> long; below
                  the prior `lookback`-bar low -> short. "Fresh" = the previous
                  bar was not already beyond that level (one entry per leg).
  Entry:          MARKET at the next H1 bar's open (momentum; no waiting for a
                  pullback that may never come).
  Stop:           entry -/+ `stop_atr` x ATR(atr_len)  (ATR stop, NOT a tight
                  structural stop that gets wicked — directly addresses the
                  "stops too tight" concern).
  Target:         entry +/- `tp_atr` x ATR(atr_len).
  Cooldown:       no new entry for `cooldown` bars after one (avoid stacking the
                  same leg).
  No session box: H1 breakouts are traded whenever they occur.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from research.setups.base import EntryIntent, MarketData
from research.setups._common import day_midnight, utc_day
from src.data.enums import Direction, Timeframe
from src.data.schemas import Candle


def _atr(candles: List[Candle], i: int, n: int) -> Optional[float]:
    if i < n:
        return None
    trs = []
    for k in range(i - n + 1, i + 1):
        pc = candles[k - 1].close
        h, l = candles[k].high, candles[k].low
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / n


class DonchianBreakoutTrend:
    name = "donchian_breakout_trend"
    version = "v1"
    description = (
        "H1 fresh 20-bar Donchian breakout -> market entry next bar; ATR stop & "
        "target; trend-continuation (the edge-scan-selected signal)."
    )
    exec_timeframe = Timeframe.H1

    def __init__(
        self,
        *,
        lookback: int = 20,
        atr_len: int = 14,
        stop_atr: float = 2.0,
        tp_atr: float = 4.0,
        cooldown: int = 12,
        max_hold_bars: Optional[int] = None,
        trend_filter_ema: Optional[int] = None,
        atr_regime_lookback: Optional[int] = None,
        atr_regime_min_pctile: float = 0.5,
        exec_timeframe: Timeframe = Timeframe.H1,
    ) -> None:
        self.exec_timeframe = exec_timeframe  # instance overrides the class default
        self.lookback = lookback
        self.atr_len = atr_len
        self.stop_atr = stop_atr
        self.tp_atr = tp_atr
        self.cooldown = cooldown
        self.max_hold_bars = max_hold_bars
        # Regime gates (optional): only trade breakouts aligned with a slow EMA
        # trend, and/or only when ATR is in a high-volatility state.
        self.trend_filter_ema = trend_filter_ema
        self.atr_regime_lookback = atr_regime_lookback
        self.atr_regime_min_pctile = atr_regime_min_pctile

    def rules(self) -> Dict[str, object]:
        return {
            "name": self.name, "version": self.version, "description": self.description,
            "exec_timeframe": "H1", "lookback": self.lookback, "atr_len": self.atr_len,
            "stop_atr": self.stop_atr, "tp_atr": self.tp_atr, "cooldown": self.cooldown,
            "max_hold_bars": self.max_hold_bars, "entry": "MARKET next bar", "session": "ANY",
            "trend_filter_ema": self.trend_filter_ema,
            "atr_regime_lookback": self.atr_regime_lookback,
            "atr_regime_min_pctile": self.atr_regime_min_pctile,
        }

    def _ema(self, candles: List[Candle], span: int) -> List[float]:
        k = 2.0 / (span + 1)
        out: List[float] = []
        e = candles[0].close
        for c in candles:
            e = c.close * k + e * (1 - k)
            out.append(e)
        return out

    def _atr_series(self, candles: List[Candle]) -> List[Optional[float]]:
        return [_atr(candles, i, self.atr_len) for i in range(len(candles))]

    def scan(self, data: MarketData) -> List[EntryIntent]:
        candles = data.tf(self.exec_timeframe)
        n = len(candles)
        if n <= self.lookback + 1:
            return []
        ema = self._ema(candles, self.trend_filter_ema) if self.trend_filter_ema else None
        atr_ser = self._atr_series(candles) if self.atr_regime_lookback else None

        intents: List[EntryIntent] = []
        last_arm = -10 ** 9
        for i in range(self.lookback + 1, n - 1):
            prior_high = max(c.high for c in candles[i - self.lookback:i])
            prior_low = min(c.low for c in candles[i - self.lookback:i])
            prev_high = max(c.high for c in candles[i - 1 - self.lookback:i - 1])
            prev_low = min(c.low for c in candles[i - 1 - self.lookback:i - 1])
            c = candles[i]
            fresh_long = c.close > prior_high and candles[i - 1].close <= prev_high
            fresh_short = c.close < prior_low and candles[i - 1].close >= prev_low
            if not (fresh_long or fresh_short):
                continue
            if i - last_arm < self.cooldown:
                continue
            atr = _atr(candles, i, self.atr_len)
            if atr is None or atr <= 0:
                continue

            # Regime gate 1: breakout must align with the slow-EMA trend.
            if ema is not None:
                if fresh_long and c.close <= ema[i]:
                    continue
                if fresh_short and c.close >= ema[i]:
                    continue
            # Regime gate 2: only in a high-volatility state (ATR percentile).
            if atr_ser is not None:
                lo = max(0, i - self.atr_regime_lookback)
                window = [a for a in atr_ser[lo:i] if a is not None]
                if window:
                    rank = sum(1 for a in window if a <= atr) / len(window)
                    if rank < self.atr_regime_min_pctile:
                        continue

            entry_ref = candles[i + 1].open  # market fill reference (next-bar open)
            is_long = fresh_long
            if is_long:
                stop = entry_ref - self.stop_atr * atr
                target = entry_ref + self.tp_atr * atr
            else:
                stop = entry_ref + self.stop_atr * atr
                target = entry_ref - self.tp_atr * atr
            risk = abs(entry_ref - stop)
            if risk <= 0:
                continue

            intents.append(EntryIntent(
                setup=self.name, version=self.version,
                day=day_midnight(utc_day(candles[i + 1])),
                direction=Direction.LONG if is_long else Direction.SHORT,
                session="ANY", arm_index=i, arm_time=candles[i].time_utc,
                entry_price=entry_ref, stop=stop, target=target,
                invalidation_price=stop,         # unused for MARKET entries
                expiry_index=i + 1, entry_type="MARKET",
                max_hold_bars=self.max_hold_bars,
                note=(f"{'long' if is_long else 'short'} {self.lookback}-bar breakout "
                      f"@~{entry_ref:.2f}; ATR {atr:.2f}; stop {self.stop_atr}xATR "
                      f"target {self.tp_atr}xATR"),
                context={"atr": atr, "risk_usd": risk,
                         "trend": 1.0 if is_long else -1.0},
            ))
            last_arm = i
        return intents
