"""Trade management layer: stop placement (and later trailing) intelligence."""

from src.trade_management.stop_placement import (
    StopEvaluation,
    StopPlacement,
    StopPlacementEngine,
    StopVerdict,
)
from src.trade_management.trailing import (
    PartialPlan,
    PositionState,
    RunnerConditions,
    TrailingStopEngine,
    TrailMethod,
    TrailResult,
)

__all__ = [
    "StopPlacementEngine",
    "StopPlacement",
    "StopEvaluation",
    "StopVerdict",
    "TrailingStopEngine",
    "PositionState",
    "TrailResult",
    "TrailMethod",
    "RunnerConditions",
    "PartialPlan",
]
