"""Real-mode readiness review (Task P11-002).

Verifies all gates before real-money trading and produces a readiness REPORT.
References 03_RISK_POLICY.md, 05_EXECUTION_POLICY.md, 11_DECISION_LOG.md (INIT-002,
real readiness), and the CLAUDE.md Trading Safety Rule.

This is a report generator only. It performs NO execution and NEVER authorizes
real trading: ReadinessReport.real_execution_allowed is always False. Real-money
execution remains forbidden until a separate, explicit manual-approval process.

Verdict logic:
- Default (no evidence supplied) -> NOT_READY.
- Any failing gate -> NOT_READY (with the failing gate names).
- All gates pass but no manual approval -> NOT_READY (awaiting approval).
- All gates pass AND manual approval granted -> READY (report only; still no
  execution is performed here).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from src.execution.gateway import ExecutionFlags


class ReadinessVerdict(str, Enum):
    READY = "READY"
    NOT_READY = "NOT_READY"


@dataclass(frozen=True)
class GateStatus:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ReadinessInputs:
    """Evidence for each readiness gate (all default to not-satisfied)."""

    tests_passing: bool = False
    backtest_validated: bool = False
    walkforward_validated: bool = False
    demo_validated: bool = False
    shadow_validated: bool = False
    risk_governor_present: bool = False
    stop_loss_enforced: bool = False
    journal_restart_safe: bool = False
    execution_flags: Optional[ExecutionFlags] = None
    manual_approval: bool = False


@dataclass(frozen=True)
class ReadinessReport:
    verdict: ReadinessVerdict
    gates: Tuple[GateStatus, ...]
    failed_gates: Tuple[str, ...]
    manual_approval: bool
    reason: str
    # This report never authorizes execution (CLAUDE.md Trading Safety Rule).
    real_execution_allowed: bool = False

    @property
    def is_ready(self) -> bool:
        return self.verdict is ReadinessVerdict.READY

    @property
    def summary(self) -> str:
        failed = ", ".join(self.failed_gates) or "none"
        return f"{self.verdict.value} (failed gates: {failed}); {self.reason}"


class ReadinessReview:
    """Builds a real-mode readiness report. Reporting only; never executes."""

    def review(self, inputs: ReadinessInputs) -> ReadinessReport:
        flags = inputs.execution_flags or ExecutionFlags()
        real_disabled = not flags.allow_real_orders and not flags.real_trading_enabled

        gates: List[GateStatus] = [
            GateStatus("tests_passing", inputs.tests_passing, "full test suite green"),
            GateStatus("backtest_validated", inputs.backtest_validated, "backtest passed"),
            GateStatus(
                "walkforward_validated", inputs.walkforward_validated,
                "walk-forward validation passed",
            ),
            GateStatus("demo_validated", inputs.demo_validated, "demo execution validated"),
            GateStatus("shadow_validated", inputs.shadow_validated, "live shadow validated"),
            GateStatus(
                "risk_governor_present", inputs.risk_governor_present,
                "risk governor wired with final authority",
            ),
            GateStatus(
                "stop_loss_enforced", inputs.stop_loss_enforced,
                "stop-loss required on every trade",
            ),
            GateStatus(
                "journal_restart_safe", inputs.journal_restart_safe,
                "journal persists and reloads",
            ),
            GateStatus(
                "real_currently_disabled", real_disabled,
                "real-money flags are off (safe pre-real state)",
            ),
        ]

        failed = tuple(g.name for g in gates if not g.passed)
        if failed:
            verdict = ReadinessVerdict.NOT_READY
            reason = "one or more readiness gates failed"
        elif not inputs.manual_approval:
            verdict = ReadinessVerdict.NOT_READY
            reason = "all gates pass; awaiting explicit manual approval for real mode"
        else:
            verdict = ReadinessVerdict.READY
            reason = "all gates pass and manual approval granted (report only; no execution)"

        return ReadinessReport(
            verdict=verdict,
            gates=tuple(gates),
            failed_gates=failed,
            manual_approval=inputs.manual_approval,
            reason=reason,
            real_execution_allowed=False,
        )
