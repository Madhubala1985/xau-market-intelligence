"""Asian range + London/NY session-expansion context (Task INTELLIGENCE-002).

Gold's intraday playbook (13_XAUUSD_SMC_PLAYBOOK.md, 14_SESSION_KILLZONE
POLICY): the Asian session (00:00-08:00 UTC) builds a range whose high/low
hold resting liquidity; London commonly sweeps one side and expands;
New York continues or traps/reverses. This module derives that context
honestly from the live exec candles:

- Asian range high/low for the CURRENT UTC day,
- where price sits relative to the range (ABOVE / INSIDE / BELOW),
- whether London/NY took out the Asian high/low (sweep of Asian liquidity),
- whether the post-Asian session is genuinely EXPANDING (post-Asian range
  vs the Asian range) or still CONTAINED.

If today's Asian session has not produced enough candles (e.g. service
started mid-day with a short feed, or it IS the Asian session), the context
reports known=False and everything downstream treats it as neutral — never
as fabricated levels.

Read-only price-path arithmetic; no credentials, no trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence

from src.data.schemas import Candle

_ASIAN_END_HOUR = 8  # 00:00-08:00 UTC (src/data/sessions.py tiling)
_MIN_ASIAN_CANDLES = 6
_EXPANSION_RATIO = 1.2


@dataclass(frozen=True)
class AsianRangeContext:
    """Today's Asian range and what London/NY did with it."""

    known: bool
    high: Optional[float] = None
    low: Optional[float] = None
    position: str = "UNKNOWN"     # ABOVE | INSIDE | BELOW | UNKNOWN
    swept: str = "NONE"           # NONE | HIGH | LOW | BOTH
    expansion_ratio: float = 0.0  # post-Asian range / Asian range
    expanding: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "known": self.known,
            "high": self.high,
            "low": self.low,
            "position": self.position,
            "swept": self.swept,
            "expansion_ratio": round(self.expansion_ratio, 3),
            "expanding": self.expanding,
            "reason": self.reason,
        }


class AsianRangeEngine:
    """Derives today's Asian range context from exec-timeframe candles."""

    def __init__(self, *, min_candles: int = _MIN_ASIAN_CANDLES,
                 expansion_ratio: float = _EXPANSION_RATIO) -> None:
        self._min_candles = min_candles
        self._expansion_ratio = expansion_ratio

    def analyze(
        self, candles: Sequence[Candle], now: datetime
    ) -> AsianRangeContext:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware (UTC)")
        now = now.astimezone(timezone.utc)
        today = now.date()

        asian = [
            c for c in candles
            if c.time_utc.astimezone(timezone.utc).date() == today
            and c.time_utc.astimezone(timezone.utc).hour < _ASIAN_END_HOUR
        ]
        if len(asian) < self._min_candles:
            return AsianRangeContext(
                known=False,
                reason=(
                    f"only {len(asian)} Asian candle(s) for {today.isoformat()}"
                    " in the feed; context unavailable (not fabricated)"
                ),
            )
        high = max(c.high for c in asian)
        low = min(c.low for c in asian)
        asian_range = max(high - low, 1e-9)

        post = [
            c for c in candles
            if c.time_utc.astimezone(timezone.utc).date() == today
            and c.time_utc.astimezone(timezone.utc).hour >= _ASIAN_END_HOUR
        ]
        swept_high = any(c.high > high for c in post)
        swept_low = any(c.low < low for c in post)
        swept = (
            "BOTH" if swept_high and swept_low
            else "HIGH" if swept_high
            else "LOW" if swept_low
            else "NONE"
        )
        if post:
            post_range = max(c.high for c in post) - min(c.low for c in post)
            ratio = post_range / asian_range
        else:
            ratio = 0.0
        last_close = candles[-1].close
        position = (
            "ABOVE" if last_close > high
            else "BELOW" if last_close < low
            else "INSIDE"
        )
        expanding = ratio >= self._expansion_ratio
        return AsianRangeContext(
            known=True, high=high, low=low, position=position, swept=swept,
            expansion_ratio=ratio, expanding=expanding,
            reason=(
                f"asian {low:.2f}-{high:.2f}, price {position}, swept={swept}, "
                f"post/asian range {ratio:.2f}x "
                f"({'expanding' if expanding else 'contained'})"
            ),
        )
