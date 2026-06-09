"""Trade management layer: stop placement (and later trailing) intelligence."""

from src.trade_management.stop_placement import (
    StopEvaluation,
    StopPlacement,
    StopPlacementEngine,
    StopVerdict,
)

__all__ = [
    "StopPlacementEngine",
    "StopPlacement",
    "StopEvaluation",
    "StopVerdict",
]
