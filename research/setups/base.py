"""Shared contract for mechanical setups.

A setup turns history into a list of EntryIntents. An EntryIntent is a fully
specified pending order:

    arm_index     - M5 index at which the setup armed (decision time). The
                    simulator may only act on candles strictly AFTER this.
    entry_price   - limit price; the trade fills when price trades into it.
    stop / target - absolute prices; risk = |entry - stop|, scored in R.
    invalidation  - price that voids the pending order before it fills.
    expiry_index  - M5 index after which an unfilled intent is cancelled.

The setup must NEVER look past arm_index when constructing an intent (no
look-ahead). The harness enforces forward-only simulation on top.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Protocol, Sequence

from src.data.enums import Direction, Timeframe
from src.data.schemas import Candle


@dataclass(frozen=True)
class EntryIntent:
    setup: str
    version: str
    day: datetime
    direction: Direction
    session: str
    arm_index: int
    arm_time: datetime
    entry_price: float
    stop: float
    target: float
    invalidation_price: float
    expiry_index: int
    note: str = ""
    context: Dict[str, float] = field(default_factory=dict)

    @property
    def risk(self) -> float:
        return abs(self.entry_price - self.stop)


@dataclass
class MarketData:
    """Multi-timeframe history container passed to setups and the harness."""

    by_tf: Dict[Timeframe, List[Candle]]

    def tf(self, timeframe: Timeframe) -> List[Candle]:
        return self.by_tf.get(timeframe, [])

    @property
    def exec_candles(self) -> List[Candle]:
        """Execution timeframe used for arming + fill simulation (M5)."""
        return self.by_tf.get(Timeframe.M5, [])


class Setup(Protocol):
    """A mechanical setup. Implementations are stateless and deterministic."""

    name: str
    version: str
    description: str

    def rules(self) -> Dict[str, object]:
        """Return the exact mechanical rules (for the report; auditable)."""
        ...

    def scan(self, data: MarketData) -> List[EntryIntent]:
        """Return all entry intents detected over the dataset (causal)."""
        ...
