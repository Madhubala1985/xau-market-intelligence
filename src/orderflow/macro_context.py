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
    """The only truthful provider today: everything is UNAVAILABLE."""

    def assess(self, now: datetime) -> MacroContext:
        return MacroContext()
