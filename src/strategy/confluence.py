"""Multi-timeframe alignment + graded confluence (Task INTELLIGENCE-001).

Two engines that turn the already-implemented gold intelligence (structure,
sweeps, zones, premium/discount, displacement, session, spread, order-flow
proxy) into ONE graded, explainable assessment instead of scattered booleans:

1. MtfAlignmentEngine — real multi-timeframe directional alignment:
   D1 / H4 / H1 / M15 structure bias plus the M5 execution-window bias,
   combined into a weighted alignment score and a supported direction.
   H1 and M15 candles are honest aggregations of the live M5 feed (no fake
   data; if aggregation yields too few bars, that timeframe reads None and
   simply contributes nothing).

2. ConfluenceEngine — graded evidence scoring for ONE candidate direction:
   each component scores [0, 1]; the weighted total drives (a) whether a
   marginal regime (tradeable chop subtype) may be overridden, (b) the
   adaptive risk budget, and (c) the terminal's "what evidence is missing"
   explanation. Confluence NEVER authorizes a trade by itself — hypothesis
   invariants (thesis + invalidation + stop), the confidence engine, and the
   Risk Governor still gate everything downstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence, Tuple

from src.data.enums import Direction, SessionType
from src.data.schemas import Candle
from src.data.session_levels import AsianRangeContext
from src.liquidity.sweep import SweepEvent, SweepStatus
from src.orderflow.proxy import OrderFlowProxy, ProxyPressure
from src.structure.market_structure import (
    Bias,
    MarketStructureEngine,
    StructureEventType,
    StructureResult,
)
from src.structure.premium_discount import PriceZone
from src.structure.zones import Zone, ZoneKind

_KILL_ZONES = {
    SessionType.LONDON, SessionType.NEW_YORK, SessionType.LONDON_NY_OVERLAP
}

# Component weights (sum == 1.0). MTF + sweep dominate; micro-evidence refines.
_WEIGHTS: Dict[str, float] = {
    "mtf": 0.20,
    "sweep": 0.16,
    "bos_choch": 0.12,
    "premium_discount": 0.10,
    "displacement": 0.10,
    "fvg": 0.08,
    "order_block": 0.08,
    "asian_range": 0.05,   # Asian liquidity / London-NY expansion context
    "session": 0.05,
    "spread": 0.03,
    "orderflow": 0.03,
}


def _dir_to_bias(direction: Direction) -> Bias:
    return Bias.BULLISH if direction is Direction.LONG else Bias.BEARISH


@dataclass(frozen=True)
class MtfAlignment:
    """Per-timeframe structure bias and the combined directional alignment."""

    d1: Optional[Bias]
    h4: Optional[Bias]
    h1: Optional[Bias]
    m15: Optional[Bias]
    m5: Optional[Bias]
    direction: Optional[Direction]   # supported direction, or None
    score: float                      # weighted agreement in [0, 1]
    reason: str
    # INTELLIGENCE-002: optional M1 trigger state (display/refinement only —
    # it carries no alignment weight), per-timeframe data sources (true MT5
    # fetch vs honest aggregation vs missing), and an explicit conflict
    # explanation when alignment is mixed.
    m1: Optional[str] = None
    sources: Dict[str, str] = field(default_factory=dict)
    conflict: str = ""

    def to_dict(self) -> dict:
        as_str = lambda b: b.value if b is not None else None  # noqa: E731
        return {
            "d1": as_str(self.d1),
            "h4": as_str(self.h4),
            "h1": as_str(self.h1),
            "m15": as_str(self.m15),
            "m5": as_str(self.m5),
            "m1": self.m1,
            "direction": self.direction.value if self.direction else None,
            "score": round(self.score, 4),
            "reason": self.reason,
            "sources": dict(self.sources),
            "conflict": self.conflict,
        }


class MtfAlignmentEngine:
    """Combines D1/H4/H1/M15/M5 structure biases into one alignment."""

    _TF_WEIGHTS = (("d1", 0.30), ("h4", 0.25), ("h1", 0.20),
                   ("m15", 0.15), ("m5", 0.10))

    def __init__(self, *, swing_strength: int = 2,
                 min_direction_score: float = 0.5) -> None:
        self._structure = MarketStructureEngine(strength=swing_strength)
        self._min_score = min_direction_score

    def align(
        self,
        *,
        daily: Sequence[Candle],
        h4: Sequence[Candle],
        h1: Sequence[Candle],
        m15: Sequence[Candle],
        m5_bias: Optional[Bias],
        m1_state: Optional[str] = None,
        sources: Optional[Dict[str, str]] = None,
    ) -> MtfAlignment:
        biases = {
            "d1": self._bias(daily),
            "h4": self._bias(h4),
            "h1": self._bias(h1),
            "m15": self._bias(m15),
            "m5": m5_bias,
        }
        sources = dict(sources or {})
        scores = {Bias.BULLISH: 0.0, Bias.BEARISH: 0.0}
        available = 0.0
        for name, weight in self._TF_WEIGHTS:
            b = biases[name]
            if b is None:
                continue
            available += weight
            if b in scores:
                scores[b] += weight
        if available <= 0:
            return MtfAlignment(
                **biases, direction=None, score=0.0,
                reason="no timeframe data available",
                m1=m1_state, sources=sources,
                conflict="no timeframe data",
            )
        bull = scores[Bias.BULLISH] / available
        bear = scores[Bias.BEARISH] / available
        if bull >= bear and bull >= self._min_score:
            direction, score = Direction.LONG, bull
        elif bear > bull and bear >= self._min_score:
            direction, score = Direction.SHORT, bear
        else:
            direction, score = None, max(bull, bear)
        reason = (
            f"bullish weight {bull:.2f} vs bearish {bear:.2f} "
            f"over {available:.2f} available"
        )
        conflict = ""
        if direction is None:
            parts = [
                f"{name}={biases[name].value}"
                for name, _ in self._TF_WEIGHTS if biases[name] is not None
            ]
            conflict = "mixed alignment: " + (", ".join(parts) or "no data")
        return MtfAlignment(**biases, direction=direction, score=score,
                            reason=reason, m1=m1_state, sources=sources,
                            conflict=conflict)

    def _bias(self, candles: Sequence[Candle]) -> Optional[Bias]:
        if len(candles) < 5:
            return None
        bias = self._structure.analyze(candles).final_bias
        return None if bias is Bias.NEUTRAL else bias


@dataclass(frozen=True)
class ConfluenceReport:
    """Graded evidence for ONE candidate direction (never an authorization)."""

    direction: Optional[Direction]
    score: float                      # weighted total in [0, 1]
    components: Dict[str, float] = field(default_factory=dict)
    missing: Tuple[str, ...] = ()     # components < 0.5: the absent evidence
    statuses: Dict[str, str] = field(default_factory=dict)  # terminal labels
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "direction": self.direction.value if self.direction else None,
            "score": round(self.score, 4),
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "missing": list(self.missing),
            "statuses": dict(self.statuses),
            "reason": self.reason,
        }


class ConfluenceEngine:
    """Scores graded confluence for a candidate direction."""

    def __init__(self, *, zone_lookback: int = 60) -> None:
        self._zone_lookback = zone_lookback

    def assess(
        self,
        direction: Optional[Direction],
        *,
        mtf: MtfAlignment,
        sweeps: Sequence[SweepEvent],
        structure: StructureResult,
        zones: Sequence[Zone],
        price_zone: Optional[PriceZone],
        displacement_ratio: float,
        session: SessionType,
        spread_ratio: float,          # current spread / allowed max
        orderflow: Optional[OrderFlowProxy],
        total_candles: int,
        asian: Optional[AsianRangeContext] = None,
    ) -> ConfluenceReport:
        if direction not in (Direction.LONG, Direction.SHORT):
            return ConfluenceReport(
                direction=None, score=0.0,
                missing=tuple(sorted(_WEIGHTS)),
                reason="no candidate direction (MTF unaligned)",
            )
        want = _dir_to_bias(direction)
        statuses: Dict[str, str] = {}

        components = {
            "mtf": mtf.score if mtf.direction is direction else 0.0,
            "sweep": self._sweep_score(sweeps, want, total_candles, statuses),
            "bos_choch": self._structure_score(structure, want, statuses),
            "fvg": self._zone_score(
                zones, ZoneKind.FAIR_VALUE_GAP, want, total_candles,
                statuses, "fvg",
            ),
            "order_block": self._order_block_score(
                zones, want, total_candles, statuses
            ),
            "premium_discount": self._pd_score(price_zone, direction, statuses),
            "asian_range": self._asian_score(asian, direction, statuses),
            "displacement": min(1.0, max(0.0, (displacement_ratio - 1.0) / 1.5)),
            "session": (1.0 if session in _KILL_ZONES
                        else 0.5 if session is SessionType.ASIAN else 0.2),
            "spread": max(0.0, min(1.0, 1.0 - spread_ratio)),
            "orderflow": self._orderflow_score(orderflow, want, statuses),
        }
        statuses["mtf"] = f"{mtf.score:.2f}->{mtf.direction.value if mtf.direction else 'NONE'}"
        statuses["displacement"] = f"{displacement_ratio:.1f}x"
        statuses["session"] = session.value
        statuses["spread"] = f"{spread_ratio:.0%} of max"
        statuses["premium_discount"] = (
            price_zone.value if price_zone is not None else "UNKNOWN"
        )

        score = sum(_WEIGHTS[k] * v for k, v in components.items())
        missing = tuple(sorted(k for k, v in components.items() if v < 0.5))
        return ConfluenceReport(
            direction=direction,
            score=score,
            components=components,
            missing=missing,
            statuses=statuses,
            reason=(
                f"{direction.value} confluence {score:.2f}; "
                f"missing: {', '.join(missing) if missing else 'none'}"
            ),
        )

    # -- component scoring -------------------------------------------------------
    @staticmethod
    def _sweep_score(
        sweeps: Sequence[SweepEvent], want: Bias, total: int,
        statuses: Dict[str, str], lookback: int = 30,
    ) -> float:
        aligned = [
            s for s in sweeps
            if s.rejection_bias is want and s.sweep_index >= total - lookback
        ]
        if any(s.status is SweepStatus.TRUE_SWEEP for s in aligned):
            statuses["sweep"] = "TRUE_SWEEP"
            return 1.0
        if any(s.status is SweepStatus.PENDING for s in aligned):
            statuses["sweep"] = "PENDING"
            return 0.5
        statuses["sweep"] = "NONE"
        return 0.0

    @staticmethod
    def _structure_score(
        structure: StructureResult, want: Bias, statuses: Dict[str, str]
    ) -> float:
        events = list(structure.events)
        if not events:
            statuses["bos_choch"] = "NONE"
            return 0.3
        last = events[-1]
        label = f"{last.event_type.value}:{last.bias.value}"
        statuses["bos_choch"] = label
        if last.bias is want:
            return 1.0 if last.event_type is StructureEventType.BOS else 0.8
        # latest break is against the candidate: CHOCH against is the worst
        return 0.0 if last.event_type is StructureEventType.CHOCH else 0.2

    def _zone_score(
        self, zones: Sequence[Zone], kind: ZoneKind, want: Bias, total: int,
        statuses: Dict[str, str], key: str,
    ) -> float:
        recent = [
            z for z in zones
            if z.kind is kind and z.bias is want and not z.mitigated
            and z.created_index >= total - self._zone_lookback
        ]
        statuses[key] = "ALIGNED" if recent else "NONE"
        return 1.0 if recent else 0.0

    def _order_block_score(
        self, zones: Sequence[Zone], want: Bias, total: int,
        statuses: Dict[str, str],
    ) -> float:
        ob = self._zone_score(zones, ZoneKind.ORDER_BLOCK, want, total, {}, "x")
        sd = self._zone_score(zones, ZoneKind.SUPPLY_DEMAND, want, total, {}, "x")
        score = max(ob, 0.7 * sd)
        statuses["order_block"] = (
            "OB_ALIGNED" if ob else "SD_ALIGNED" if sd else "NONE"
        )
        return score

    @staticmethod
    def _pd_score(
        zone: Optional[PriceZone], direction: Direction,
        statuses: Dict[str, str],
    ) -> float:
        if zone is None:
            return 0.3
        if direction is Direction.SHORT:
            return {PriceZone.PREMIUM: 1.0, PriceZone.EQUILIBRIUM: 0.5,
                    PriceZone.DISCOUNT: 0.2}[zone]
        return {PriceZone.DISCOUNT: 1.0, PriceZone.EQUILIBRIUM: 0.5,
                PriceZone.PREMIUM: 0.2}[zone]

    @staticmethod
    def _asian_score(
        asian: Optional[AsianRangeContext], direction: Direction,
        statuses: Dict[str, str],
    ) -> float:
        """Asian liquidity / London-NY expansion support for the candidate.

        SHORT is best served by a sweep ABOVE the Asian high (buy-side
        liquidity taken) or by expansion BELOW the range; LONG mirrors it.
        Unknown context is neutral-low — honest absence, never fabricated.
        """
        if asian is None or not asian.known:
            statuses["asian_range"] = "UNKNOWN"
            return 0.3
        statuses["asian_range"] = (
            f"{asian.position} swept={asian.swept} "
            f"{'EXPANDING' if asian.expanding else 'CONTAINED'}"
        )
        if direction is Direction.SHORT:
            if asian.swept in ("HIGH", "BOTH"):
                return 1.0                       # buy-side taken; trap above
            if asian.position == "BELOW" and asian.expanding:
                return 0.8                       # expansion below the range
            if asian.position == "INSIDE":
                return 0.3
            return 0.4
        if asian.swept in ("LOW", "BOTH"):
            return 1.0
        if asian.position == "ABOVE" and asian.expanding:
            return 0.8
        if asian.position == "INSIDE":
            return 0.3
        return 0.4

    @staticmethod
    def _orderflow_score(
        proxy: Optional[OrderFlowProxy], want: Bias, statuses: Dict[str, str]
    ) -> float:
        if proxy is None:
            statuses["orderflow"] = "N/A"
            return 0.5
        statuses["orderflow"] = proxy.pressure.value
        wanted = (
            ProxyPressure.BULLISH if want is Bias.BULLISH
            else ProxyPressure.BEARISH
        )
        if proxy.pressure is wanted:
            return 1.0
        if proxy.pressure is ProxyPressure.NEUTRAL:
            return 0.5
        return 0.0
