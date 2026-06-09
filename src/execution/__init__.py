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
from src.execution.kill_switch import KillSwitch
from src.execution.preflight import (
    DemoPreflight,
    GateResult,
    GateStatus,
    PreflightReport,
)
from src.execution.positions import (
    PositionReconciler,
    ReconciliationReport,
)
from src.execution.demo_planner import (
    DemoTradePlanner,
    PlanCheck,
    TradePlan,
    confidence_tier,
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
    # Demo preflight (DEMO-001)
    "KillSwitch",
    "DemoPreflight",
    "PreflightReport",
    "GateResult",
    "GateStatus",
    # Position safety + demo planning (DEMO-002 blockers F-3/F-4)
    "PositionReconciler",
    "ReconciliationReport",
    "DemoTradePlanner",
    "TradePlan",
    "PlanCheck",
    "confidence_tier",
]
