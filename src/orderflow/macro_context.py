"""Macro confirmation interface — honest by construction (INTELLIGENCE-002).

There is NO live macro feed in this system (no DXY, no US yields, no gold
futures stream, no economic calendar API). This module defines the interface
a future real feed must implement (tasks NEWS-001 / MACRO-001 / FUTURES-001)
and ships the ONLY currently-truthful implementation: a provider that says
"UNAVAILABLE".

Hard honesty rules:
- a MacroSignal with available=False carries bias "UNAVAILABLE" and can never
  be constructed to look available without data,
- the NullMacroProvider can never return an available signal,
- nothing in the live path treats UNAVAILABLE as confirmation or
  contradiction; it contributes exactly nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

_UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class MacroSignal:
    """One macro input (DXY / yields / futures). Defaults to honest absence."""

    available: bool = False
    bias: str = _UNAVAILABLE   # BULLISH_GOLD | BEARISH_GOLD | NEUTRAL | UNAVAILABLE
    detail: str = "no feed configured"

    def __post_init__(self) -> None:
        if not self.available and self.bias != _UNAVAILABLE:
            raise ValueError(
                "an unavailable macro signal cannot carry a bias (no faking)"
            )
        if self.available and self.bias == _UNAVAILABLE:
            raise ValueError("an available macro signal must carry a bias")


@dataclass(frozen=True)
class MacroContext:
    """All macro confirmations at one moment."""

    dxy: MacroSignal = field(default_factory=MacroSignal)
    us_yields: MacroSignal = field(default_factory=MacroSignal)
    gold_futures: MacroSignal = field(default_factory=MacroSignal)

    @property
    def any_available(self) -> bool:
        return any(s.available for s in (self.dxy, self.us_yields,
                                         self.gold_futures))

    def summary(self) -> str:
        if not self.any_available:
            return ("DXY/yields/futures: UNAVAILABLE "
                    "(no feed; NEWS-001/MACRO-001/FUTURES-001 pending; "
                    "never faked)")
        parts = [f"dxy={self.dxy.bias}", f"yields={self.us_yields.bias}",
                 f"futures={self.gold_futures.bias}"]
        return " ".join(parts)


class MacroProvider(Protocol):
    """A future real macro feed must implement this."""

    def assess(self, now: datetime) -> MacroContext: ...


class NullMacroProvider:
    """A truthful empty provider: everything is UNAVAILABLE."""

    def assess(self, now: datetime) -> MacroContext:
        return MacroContext()


def gold_pressure(ctx: MacroContext) -> tuple[str, str]:
    """Combine DXY + yields into a gold-pressure reading.

    DXY rising + yields rising  -> BEARISH_GOLD pressure;
    DXY falling + yields falling -> BULLISH_GOLD pressure;
    mixed -> NEUTRAL (conflict). Anything unavailable -> UNAVAILABLE.
    Pressure is CONFIRMATION ONLY — it adjusts confluence, never triggers.
    """
    if not (ctx.dxy.available and ctx.us_yields.available):
        return "UNAVAILABLE", "macro inputs unavailable"
    pair = (ctx.dxy.bias, ctx.us_yields.bias)
    if pair == ("BEARISH_GOLD", "BEARISH_GOLD"):
        return "BEARISH_GOLD", "DXY rising + yields rising"
    if pair == ("BULLISH_GOLD", "BULLISH_GOLD"):
        return "BULLISH_GOLD", "DXY falling + yields falling"
    return "NEUTRAL", f"mixed macro: dxy={ctx.dxy.bias} yields={ctx.us_yields.bias}"


# -- file-based provider (MACRO-001 / FUTURES-001 interim source) ---------------
#
# Until a real DXY/yields/futures feed exists, the operator may maintain
# configs/macro_context.json — an explicit, reviewed, TIMESTAMPED assertion:
#
#   {"as_of_utc": "2026-06-10T08:00:00+00:00", "max_age_hours": 12,
#    "dxy": "RISING", "us10y": "RISING", "us2y": "RISING",
#    "gold_futures": "BEARISH"}
#
# Honesty rules: a missing/malformed/STALE file reads as UNAVAILABLE (the
# as_of timestamp + max age make silent staleness impossible). Mapping:
# for dxy/yields, RISING => bearish-gold pressure, FALLING => bullish-gold;
# for gold_futures, BULLISH/BEARISH/NEUTRAL are taken directly.

_DOLLAR_MAP = {"RISING": "BEARISH_GOLD", "FALLING": "BULLISH_GOLD",
               "FLAT": "NEUTRAL"}
_FUTURES_MAP = {"BULLISH": "BULLISH_GOLD", "BEARISH": "BEARISH_GOLD",
                "NEUTRAL": "NEUTRAL"}


class FileMacroProvider:
    """Reads the operator-maintained macro context file (stale-aware)."""

    def __init__(self, path, *, default_max_age_hours: float = 12.0) -> None:
        from pathlib import Path

        self._path = Path(path)
        self._default_max_age = default_max_age_hours

    def assess(self, now: datetime) -> MacroContext:
        import json

        if not self._path.is_file():
            return MacroContext()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            as_of = datetime.fromisoformat(str(data["as_of_utc"]))
            if as_of.tzinfo is None:
                raise ValueError("as_of_utc must be timezone-aware")
            max_age = float(data.get("max_age_hours", self._default_max_age))
            age_hours = (now - as_of).total_seconds() / 3600.0
            if age_hours > max_age or age_hours < 0:
                return MacroContext()  # stale or future-dated: UNAVAILABLE
            detail = f"operator file, as of {as_of.isoformat()}"
            return MacroContext(
                dxy=self._dollar_signal(data.get("dxy"), detail),
                us_yields=self._dollar_signal(
                    data.get("us10y") or data.get("us2y"), detail
                ),
                gold_futures=self._futures_signal(
                    data.get("gold_futures"), detail
                ),
            )
        except (KeyError, TypeError, ValueError):
            return MacroContext()  # malformed: UNAVAILABLE, never guessed

    @staticmethod
    def _dollar_signal(raw, detail: str) -> MacroSignal:
        bias = _DOLLAR_MAP.get(str(raw or "").strip().upper())
        if bias is None:
            return MacroSignal()
        return MacroSignal(available=True, bias=bias, detail=detail)

    @staticmethod
    def _futures_signal(raw, detail: str) -> MacroSignal:
        bias = _FUTURES_MAP.get(str(raw or "").strip().upper())
        if bias is None:
            return MacroSignal()
        return MacroSignal(available=True, bias=bias, detail=detail)
