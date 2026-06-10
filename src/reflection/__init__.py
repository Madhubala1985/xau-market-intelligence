"""Reflection layer: offline mistake classification and daily review."""

from src.reflection.readiness import (
    GateStatus,
    ReadinessInputs,
    ReadinessReport,
    ReadinessReview,
    ReadinessVerdict,
)
from src.reflection.reflection import (
    DailyReview,
    MistakeCategory,
    RecordMistakes,
    ReflectionEngine,
)
from src.reflection.opportunity_audit import (
    OpportunityAudit,
    build_opportunity_audit,
    render_opportunity_audit_markdown,
)
from src.reflection.demo_evaluation import (
    Finding,
    FindingClass,
    PerformanceMetrics,
    ReflectionReport,
    SessionEvaluation,
    SessionEvaluator,
    build_reflection,
    render_evaluation_markdown,
    render_reflection_markdown,
)

__all__ = [
    "ReflectionEngine",
    "DailyReview",
    "RecordMistakes",
    "MistakeCategory",
    "ReadinessReview",
    "ReadinessInputs",
    "ReadinessReport",
    "ReadinessVerdict",
    "GateStatus",
    # Demo evaluation + reflection (DEMO-EVAL)
    "SessionEvaluator",
    "SessionEvaluation",
    "PerformanceMetrics",
    "Finding",
    "FindingClass",
    "ReflectionReport",
    "build_reflection",
    "render_evaluation_markdown",
    "render_reflection_markdown",
    # Opportunity audit (INTELLIGENCE-001)
    "OpportunityAudit",
    "build_opportunity_audit",
    "render_opportunity_audit_markdown",
]
