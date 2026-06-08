"""Core data layer: schemas and shared enumerations."""

from src.data.enums import (
    BrokerConnectionStatus,
    DecisionStatus,
    Direction,
    SessionType,
    Timeframe,
    TradeOutcome,
)
from src.data.schemas import (
    BrokerState,
    Candle,
    SessionState,
    SpreadSnapshot,
    Tick,
    TradeDecision,
    TradeRecord,
)
from src.data.aggregation import (
    AggregationError,
    TimeframeAggregator,
    aggregate,
)
from src.data.sessions import (
    DEFAULT_SEGMENTS,
    SessionConfig,
    SessionEngine,
    SessionLevels,
    SessionSegment,
)
from src.data.validation import (
    DataValidator,
    IssueSeverity,
    ValidationCode,
    ValidationConfig,
    ValidationIssue,
    ValidationReport,
    ValidationStatus,
)

__all__ = [
    # enums
    "BrokerConnectionStatus",
    "DecisionStatus",
    "Direction",
    "SessionType",
    "Timeframe",
    "TradeOutcome",
    # schemas
    "BrokerState",
    "Candle",
    "SessionState",
    "SpreadSnapshot",
    "Tick",
    "TradeDecision",
    "TradeRecord",
    # validation
    "DataValidator",
    "ValidationConfig",
    "ValidationReport",
    "ValidationIssue",
    "ValidationStatus",
    "ValidationCode",
    "IssueSeverity",
    # aggregation
    "TimeframeAggregator",
    "aggregate",
    "AggregationError",
    # sessions
    "SessionEngine",
    "SessionConfig",
    "SessionSegment",
    "SessionLevels",
    "DEFAULT_SEGMENTS",
]
