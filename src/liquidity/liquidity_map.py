"""Liquidity map engine (Task P3-002).

Builds a map of resting liquidity levels from a Candle series, per
15_LIQUIDITY_ENGINEERING.md. Scope is the MAP only: detecting where liquidity
rests. Sweep / manipulation detection is a separate task (P3-003) and is not
implemented here.

Detected level kinds:
- swing highs / swing lows (reusing the P3-001 structure engine),
- equal highs / equal lows (clusters of near-equal swings),
- session highs / lows (reusing the P2-002 session engine),
- previous day high/low and previous week high/low.

Side convention (15_LIQUIDITY_ENGINEERING.md):
- high-type levels are BUY_SIDE liquidity (rests above price),
- low-type levels are SELL_SIDE liquidity (rests below price).

No look-ahead: every level is derived only from the supplied candles. Swings are
confirmed fractal pivots; previous day/week are completed past periods; session
extremes use only the candles present. Building on a prefix never references data
beyond that prefix.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from src.data.enums import SessionType
from src.data.schemas import Candle
from src.data.sessions import SessionConfig, SessionEngine
from src.structure.market_structure import MarketStructureEngine, SwingType


class LiquiditySide(str, Enum):
    BUY_SIDE = "BUY_SIDE"
    SELL_SIDE = "SELL_SIDE"


class LiquidityKind(str, Enum):
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"
    EQUAL_HIGHS = "EQUAL_HIGHS"
    EQUAL_LOWS = "EQUAL_LOWS"
    SESSION_HIGH = "SESSION_HIGH"
    SESSION_LOW = "SESSION_LOW"
    PREV_DAY_HIGH = "PREV_DAY_HIGH"
    PREV_DAY_LOW = "PREV_DAY_LOW"
    PREV_WEEK_HIGH = "PREV_WEEK_HIGH"
    PREV_WEEK_LOW = "PREV_WEEK_LOW"


# Which kinds rest above (buy-side) vs below (sell-side) price.
_BUY_SIDE_KINDS = frozenset(
    {
        LiquidityKind.SWING_HIGH,
        LiquidityKind.EQUAL_HIGHS,
        LiquidityKind.SESSION_HIGH,
        LiquidityKind.PREV_DAY_HIGH,
        LiquidityKind.PREV_WEEK_HIGH,
    }
)

_MAIN_SESSIONS = frozenset(
    {
        SessionType.ASIAN,
        SessionType.LONDON,
        SessionType.NEW_YORK,
        SessionType.LONDON_NY_OVERLAP,
    }
)


def _side_for(kind: LiquidityKind) -> LiquiditySide:
    return LiquiditySide.BUY_SIDE if kind in _BUY_SIDE_KINDS else LiquiditySide.SELL_SIDE


@dataclass(frozen=True)
class LiquidityLevel:
    """A single resting-liquidity level."""

    kind: LiquidityKind
    side: LiquiditySide
    price: float
    time_utc: datetime
    touches: int = 1
    label: str = ""
    indices: Tuple[int, ...] = ()


@dataclass(frozen=True)
class LiquidityMap:
    """A collection of detected liquidity levels."""

    levels: Tuple[LiquidityLevel, ...] = ()

    def of_kind(self, kind: LiquidityKind) -> List[LiquidityLevel]:
        return [lvl for lvl in self.levels if lvl.kind is kind]

    def buy_side(self) -> List[LiquidityLevel]:
        return [lvl for lvl in self.levels if lvl.side is LiquiditySide.BUY_SIDE]

    def sell_side(self) -> List[LiquidityLevel]:
        return [lvl for lvl in self.levels if lvl.side is LiquiditySide.SELL_SIDE]


class LiquidityMapEngine:
    """Builds a LiquidityMap from a candle series."""

    def __init__(
        self,
        *,
        swing_strength: int = 2,
        equal_tolerance: float = 0.1,
        session_config: Optional[SessionConfig] = None,
    ) -> None:
        if equal_tolerance < 0:
            raise ValueError("equal_tolerance must be >= 0")
        self._structure = MarketStructureEngine(strength=swing_strength)
        self._equal_tolerance = equal_tolerance
        self._session_engine = SessionEngine(session_config)

    def build(self, candles: Sequence[Candle]) -> LiquidityMap:
        if not candles:
            return LiquidityMap(())

        swings = self._structure.find_swings(candles)
        levels: List[LiquidityLevel] = []
        levels += self._swing_levels(swings)
        levels += self._equal_levels(swings)
        levels += self._session_levels(candles)
        levels += self._prev_period_levels(candles)

        # Deterministic ordering: by price (desc), then kind name.
        levels.sort(key=lambda lvl: (-lvl.price, lvl.kind.value))
        return LiquidityMap(tuple(levels))

    # -- swings ------------------------------------------------------------
    def _swing_levels(self, swings) -> List[LiquidityLevel]:
        out: List[LiquidityLevel] = []
        for sp in swings:
            kind = (
                LiquidityKind.SWING_HIGH
                if sp.swing_type is SwingType.HIGH
                else LiquidityKind.SWING_LOW
            )
            out.append(
                LiquidityLevel(
                    kind=kind,
                    side=_side_for(kind),
                    price=sp.price,
                    time_utc=sp.time_utc,
                    indices=(sp.index,),
                )
            )
        return out

    # -- equal highs / lows ------------------------------------------------
    def _equal_levels(self, swings) -> List[LiquidityLevel]:
        highs = [
            (sp.index, sp.price, sp.time_utc)
            for sp in swings
            if sp.swing_type is SwingType.HIGH
        ]
        lows = [
            (sp.index, sp.price, sp.time_utc)
            for sp in swings
            if sp.swing_type is SwingType.LOW
        ]
        out: List[LiquidityLevel] = []
        out += self._equal_clusters(highs, LiquidityKind.EQUAL_HIGHS)
        out += self._equal_clusters(lows, LiquidityKind.EQUAL_LOWS)
        return out

    def _equal_clusters(
        self, points: List[Tuple[int, float, datetime]], kind: LiquidityKind
    ) -> List[LiquidityLevel]:
        if len(points) < 2:
            return []
        ordered = sorted(points, key=lambda p: p[1])
        clusters: List[List[Tuple[int, float, datetime]]] = []
        current = [ordered[0]]
        for point in ordered[1:]:
            if point[1] - current[-1][1] <= self._equal_tolerance:
                current.append(point)
            else:
                clusters.append(current)
                current = [point]
        clusters.append(current)

        out: List[LiquidityLevel] = []
        is_high = kind is LiquidityKind.EQUAL_HIGHS
        for cluster in clusters:
            if len(cluster) < 2:
                continue
            prices = [p[1] for p in cluster]
            price = max(prices) if is_high else min(prices)
            time_utc = max(p[2] for p in cluster)  # most recent touch
            indices = tuple(sorted(p[0] for p in cluster))
            out.append(
                LiquidityLevel(
                    kind=kind,
                    side=_side_for(kind),
                    price=price,
                    time_utc=time_utc,
                    touches=len(cluster),
                    indices=indices,
                )
            )
        return out

    # -- session highs / lows ---------------------------------------------
    def _session_levels(self, candles: Sequence[Candle]) -> List[LiquidityLevel]:
        out: List[LiquidityLevel] = []
        for occ in self._session_engine.track_session_levels(candles):
            if occ.session not in _MAIN_SESSIONS:
                continue
            out.append(
                LiquidityLevel(
                    kind=LiquidityKind.SESSION_HIGH,
                    side=LiquiditySide.BUY_SIDE,
                    price=occ.high,
                    time_utc=occ.start_utc,
                    label=occ.session.value,
                )
            )
            out.append(
                LiquidityLevel(
                    kind=LiquidityKind.SESSION_LOW,
                    side=LiquiditySide.SELL_SIDE,
                    price=occ.low,
                    time_utc=occ.start_utc,
                    label=occ.session.value,
                )
            )
        return out

    # -- previous day / week ----------------------------------------------
    def _prev_period_levels(self, candles: Sequence[Candle]) -> List[LiquidityLevel]:
        out: List[LiquidityLevel] = []
        out += self._prev_group_levels(
            candles,
            key=lambda c: c.time_utc.date(),
            high_kind=LiquidityKind.PREV_DAY_HIGH,
            low_kind=LiquidityKind.PREV_DAY_LOW,
        )
        out += self._prev_group_levels(
            candles,
            key=lambda c: c.time_utc.isocalendar()[:2],  # (ISO year, ISO week)
            high_kind=LiquidityKind.PREV_WEEK_HIGH,
            low_kind=LiquidityKind.PREV_WEEK_LOW,
        )
        return out

    def _prev_group_levels(
        self,
        candles: Sequence[Candle],
        *,
        key,
        high_kind: LiquidityKind,
        low_kind: LiquidityKind,
    ) -> List[LiquidityLevel]:
        groups: Dict[object, List[Candle]] = {}
        for candle in candles:
            groups.setdefault(key(candle), []).append(candle)
        keys = sorted(groups.keys())
        if len(keys) < 2:
            return []
        # The period immediately before the current (latest) period.
        prev_candles = groups[keys[-2]]

        high_candle = max(prev_candles, key=lambda c: c.high)
        low_candle = min(prev_candles, key=lambda c: c.low)
        return [
            LiquidityLevel(
                kind=high_kind,
                side=_side_for(high_kind),
                price=high_candle.high,
                time_utc=high_candle.time_utc,
            ),
            LiquidityLevel(
                kind=low_kind,
                side=_side_for(low_kind),
                price=low_candle.low,
                time_utc=low_candle.time_utc,
            ),
        ]
