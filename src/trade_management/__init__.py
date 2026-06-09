"""Trade management layer: stop placement, trailing, and position protection."""

from src.trade_management.stop_placement import (
    StopEvaluation,
    StopPlacement,
    StopPlacementEngine,
    StopVerdict,
)
from src.trade_management.position_manager import (
    PositionProtectionManager,
    StopProposal,
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
    # Position protection (Audit F-4)
    "PositionProtectionManager",
    "StopProposal",
]
