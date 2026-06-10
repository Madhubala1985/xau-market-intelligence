"""M1 entry refinement (FINAL-INTELLIGENCE).

M1 NEVER creates a trade and NEVER overrides higher-timeframe logic. It only
refines the timing of an entry that the M5/M15/HTF stack has ALREADY
qualified:

- VETO_DELAY   the last M1 candles show strong rejection AGAINST the trade
               direction or erratic microstructure: skip THIS cycle's entry
               (the setup may re-qualify next cycle),
- CAUTION      microstructure is noisy: enter, but it is flagged for the
               terminal and the journal,
- CONFIRM      micro displacement agrees with the direction,
- PASS         nothing notable; no effect,
- UNAVAILABLE  no/short M1 feed; honestly no effect (never fabricated).

A veto is the ONLY effect M1 can have on gating, and a veto can only ever
REMOVE an entry this cycle — it cannot add one, change direction, loosen a
stop, or bypass any other layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from src.data.enums import Direction
from src.data.schemas import Candle


class M1State:
    PASS = "PASS"
    CONFIRM = "CONFIRM"
    CAUTION = "CAUTION"
    VETO_DELAY = "VETO_DELAY"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class M1Refinement:
    state: str
    reason: str
    rejection_share: float   # opposing wick share of the last candles
    micro_displacement: float  # last body vs recent median range

    @property
    def vetoes_entry(self) -> bool:
        return self.state == M1State.VETO_DELAY

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "reason": self.reason,
            "rejection_share": round(self.rejection_share, 3),
            "micro_displacement": round(self.micro_displacement, 3),
        }


class M1RefinementEngine:
    """Assesses M1 microstructure for an ALREADY-QUALIFIED entry."""

    def __init__(
        self,
        *,
        min_candles: int = 10,
        veto_rejection_share: float = 0.65,
        confirm_displacement: float = 1.5,
        caution_wick_share: float = 0.55,
    ) -> None:
        self._min_candles = min_candles
        self._veto_rejection = veto_rejection_share
        self._confirm_displacement = confirm_displacement
        self._caution_wick = caution_wick_share

    def assess(
        self,
        m1_candles: Optional[Sequence[Candle]],
        direction: Optional[Direction],
    ) -> M1Refinement:
        if direction not in (Direction.LONG, Direction.SHORT):
            return M1Refinement(M1State.PASS, "no qualified entry to refine",
                                0.0, 0.0)
        if not m1_candles or len(m1_candles) < self._min_candles:
            return M1Refinement(
                M1State.UNAVAILABLE,
                "no/short M1 feed; refinement unavailable (no effect)",
                0.0, 0.0,
            )
        recent = list(m1_candles)[-self._min_candles:]
        last3 = recent[-3:]
        rejection = self._opposing_wick_share(last3, direction)
        displacement = self._micro_displacement(recent)
        wick = self._wick_share(last3)

        if rejection >= self._veto_rejection:
            return M1Refinement(
                M1State.VETO_DELAY,
                f"M1 rejection against entry (opposing wick share "
                f"{rejection:.2f}); delay this cycle",
                rejection, displacement,
            )
        if displacement >= self._confirm_displacement and self._aligned(
            recent[-1], direction
        ):
            return M1Refinement(
                M1State.CONFIRM,
                f"M1 micro displacement {displacement:.1f}x agrees",
                rejection, displacement,
            )
        if wick >= self._caution_wick:
            return M1Refinement(
                M1State.CAUTION,
                f"noisy M1 microstructure (wick share {wick:.2f})",
                rejection, displacement,
            )
        return M1Refinement(M1State.PASS, "M1 microstructure unremarkable",
                            rejection, displacement)

    # -- features ----------------------------------------------------------------
    @staticmethod
    def _opposing_wick_share(candles: Sequence[Candle],
                             direction: Direction) -> float:
        """Wick AGAINST the trade direction as a share of range (mean)."""
        shares = []
        for c in candles:
            full = c.high - c.low
            if full <= 0:
                continue
            body_top = max(c.open, c.close)
            body_bottom = min(c.open, c.close)
            if direction is Direction.LONG:
                opposing = c.high - body_top      # upper rejection vs longs
            else:
                opposing = body_bottom - c.low    # lower rejection vs shorts
            shares.append(opposing / full)
        return sum(shares) / len(shares) if shares else 0.0

    @staticmethod
    def _micro_displacement(recent: Sequence[Candle]) -> float:
        ranges = sorted(c.high - c.low for c in recent)
        median = ranges[len(ranges) // 2]
        if median <= 0:
            return 0.0
        return abs(recent[-1].close - recent[-1].open) / median

    @staticmethod
    def _wick_share(candles: Sequence[Candle]) -> float:
        shares = []
        for c in candles:
            full = c.high - c.low
            if full <= 0:
                continue
            shares.append(1.0 - abs(c.close - c.open) / full)
        return sum(shares) / len(shares) if shares else 0.0

    @staticmethod
    def _aligned(candle: Candle, direction: Direction) -> bool:
        if direction is Direction.LONG:
            return candle.close > candle.open
        return candle.close < candle.open
