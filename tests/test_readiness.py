"""Tests for P11-002 real-mode readiness review (report only)."""

import dataclasses

from src.execution import ExecutionFlags
from src.reflection import (
    ReadinessInputs,
    ReadinessReport,
    ReadinessReview,
    ReadinessVerdict,
)


def all_gates_inputs(**overrides) -> ReadinessInputs:
    kwargs = dict(
        tests_passing=True,
        backtest_validated=True,
        walkforward_validated=True,
        demo_validated=True,
        shadow_validated=True,
        risk_governor_present=True,
        stop_loss_enforced=True,
        journal_restart_safe=True,
        execution_flags=ExecutionFlags(),  # real disabled by default
        manual_approval=False,
    )
    kwargs.update(overrides)
    return ReadinessInputs(**kwargs)


def review() -> ReadinessReview:
    return ReadinessReview()


# ---------------------------------------------------------------------------
# Default is NOT READY
# ---------------------------------------------------------------------------

def test_default_inputs_not_ready():
    report = review().review(ReadinessInputs())
    assert report.verdict is ReadinessVerdict.NOT_READY
    assert report.is_ready is False
    assert len(report.failed_gates) >= 1
    assert report.real_execution_allowed is False


# ---------------------------------------------------------------------------
# Gate failures keep it NOT READY
# ---------------------------------------------------------------------------

def test_single_failing_gate_blocks_readiness():
    report = review().review(all_gates_inputs(walkforward_validated=False, manual_approval=True))
    assert report.verdict is ReadinessVerdict.NOT_READY
    assert "walkforward_validated" in report.failed_gates


def test_real_flags_enabled_fail_safety_gate():
    flags = ExecutionFlags(allow_real_orders=True)  # unsafe pre-real state
    report = review().review(all_gates_inputs(execution_flags=flags, manual_approval=True))
    assert report.verdict is ReadinessVerdict.NOT_READY
    assert "real_currently_disabled" in report.failed_gates


# ---------------------------------------------------------------------------
# All gates pass: still needs manual approval
# ---------------------------------------------------------------------------

def test_all_gates_pass_but_no_manual_approval():
    report = review().review(all_gates_inputs(manual_approval=False))
    assert report.verdict is ReadinessVerdict.NOT_READY
    assert report.failed_gates == ()
    assert "manual approval" in report.reason


def test_all_gates_pass_with_manual_approval_is_ready():
    report = review().review(all_gates_inputs(manual_approval=True))
    assert report.verdict is ReadinessVerdict.READY
    assert report.failed_gates == ()
    # Even when READY, the report never authorizes execution.
    assert report.real_execution_allowed is False


# ---------------------------------------------------------------------------
# Report only: never authorizes / executes
# ---------------------------------------------------------------------------

def test_report_never_authorizes_execution():
    ready = review().review(all_gates_inputs(manual_approval=True))
    assert ready.real_execution_allowed is False


def test_review_has_no_execution_method():
    methods = dir(ReadinessReview)
    for banned in ("execute", "order", "send", "enable_real", "trade", "buy", "sell"):
        assert not any(banned in m.lower() for m in methods)


def test_report_has_no_execution_field():
    field_names = {f.name for f in dataclasses.fields(ReadinessReport)}
    # The only execution-related field explicitly states it is never allowed.
    assert "real_execution_allowed" in field_names
    forbidden = {"order", "send", "execute", "authorize"}
    assert field_names.isdisjoint(forbidden)


def test_summary_text_contains_verdict():
    report = review().review(ReadinessInputs())
    assert "NOT_READY" in report.summary
