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
]
