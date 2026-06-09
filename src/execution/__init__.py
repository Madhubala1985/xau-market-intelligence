"""Execution layer: MT5 demo execution gateway (risk-gated, demo-only)."""

from src.execution.gateway import (
    ExecutionCheck,
    ExecutionFlags,
    ExecutionGateway,
    ExecutionResult,
    ExecutionStatus,
    OrderState,
    load_execution_flags,
)
from src.execution.shadow import (
    ShadowReport,
    ShadowRunner,
)
from src.execution.live_shadow import (
    LiveCycleResult,
    LiveShadowReport,
    LiveShadowSession,
    make_live_pipeline,
)

__all__ = [
    "ExecutionGateway",
    "ExecutionFlags",
    "ExecutionResult",
    "ExecutionStatus",
    "OrderState",
    "ExecutionCheck",
    "load_execution_flags",
    "ShadowRunner",
    "ShadowReport",
    # Live shadow (LIVE-001)
    "LiveShadowSession",
    "LiveShadowReport",
    "LiveCycleResult",
    "make_live_pipeline",
]
