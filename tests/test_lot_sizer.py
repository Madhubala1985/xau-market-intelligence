"""Tests for milestone-aware adaptive lot sizing (SIZING-001).

Proves the Proven Defect is fixed: an adaptive budget below the broker
minimum lot is resolved EXPLICITLY (promoted within the phase ceiling or
blocked with full diagnostics) — never a vague "invalid lot size 0.0".
"""

import pytest

from src.risk.lot_sizer import LotVerdict, resolve_lot


def decide(**overrides):
    kwargs = dict(
        equity=2_000.0,
        risk_pct=0.002,      # DEFENSIVE 0.20% — the live-evidence budget
        ceiling_pct=0.010,   # PHASE_1 ceiling
        stop_distance=5.20,
    )
    kwargs.update(overrides)
    return resolve_lot(**kwargs)


# -- the exact live regression ---------------------------------------------------

def test_live_regression_defensive_budget_promotes_to_min_lot():
    """$2,000 equity, 0.20% budget ($4), 5.20 stop: raw lot 0.0077 < 0.01.
    Min-lot risk $5.20 (0.26%) fits the 1% PHASE_1 ceiling -> promoted."""
    out = decide()
    assert out.lot == pytest.approx(0.01)
    assert out.verdict == LotVerdict.MIN_LOT_PROMOTED
    assert out.approved is True
    assert out.min_lot_risk_usd == pytest.approx(5.20)
    assert out.realized_risk_pct == pytest.approx(0.0026)
    assert "promoted" in out.reason
    assert out.phase == "PHASE_1"
    assert "$10,000" in out.milestone


def test_never_a_vague_zero_lot():
    for kwargs in (
        {},                                  # promotion case
        {"stop_distance": 0.0},              # no stop
        {"risk_pct": 0.0},                   # no budget
        {"equity": 30_000.0, "ceiling_pct": 0.005, "stop_distance": 20.0},
        {"stop_distance": 400.0},            # absurd stop
    ):
        out = decide(**kwargs)
        assert out.verdict in (
            LotVerdict.SIZED, LotVerdict.MIN_LOT_PROMOTED,
            LotVerdict.MIN_LOT_RISK_TOO_HIGH, LotVerdict.STOP_TOO_WIDE,
            LotVerdict.NO_STOP, LotVerdict.NO_BUDGET,
        )
        assert out.reason  # always explained
        if out.lot == 0.0:
            assert out.approved is False  # zero ONLY with an explicit block


# -- blocking paths ---------------------------------------------------------------

def test_min_lot_risk_above_phase_ceiling_blocks_clearly():
    # PHASE_4: ceiling 0.5% of $30k = $150; stop 20.0 -> min-lot risk $20...
    # use small equity to exceed: $3,000 ceiling 0.5% = $15 < $20 min-lot risk.
    out = resolve_lot(equity=3_000.0, risk_pct=0.002, ceiling_pct=0.005,
                      stop_distance=20.0)
    assert out.lot == 0.0
    assert out.verdict == LotVerdict.MIN_LOT_RISK_TOO_HIGH
    assert "ceiling" in out.reason
    assert out.min_lot_risk_usd == pytest.approx(20.0)


def test_stop_too_wide_for_account_blocks_clearly():
    # min-lot risk $400 = 20% of $2,000 — over even the absolute 1% demo cap.
    out = decide(stop_distance=400.0)
    assert out.verdict == LotVerdict.STOP_TOO_WIDE
    assert out.lot == 0.0
    assert "too wide" in out.reason


def test_no_stop_and_no_budget_block():
    assert decide(stop_distance=0.0).verdict == LotVerdict.NO_STOP
    assert decide(risk_pct=0.0).verdict == LotVerdict.NO_BUDGET


# -- dynamic (never fixed) sizing --------------------------------------------------

def test_lot_scales_with_equity_budget_and_stop_distance():
    small = decide(equity=2_000.0, risk_pct=0.008)        # $16 budget
    big = decide(equity=20_000.0, risk_pct=0.008,
                 ceiling_pct=0.006)                        # $160 budget
    assert big.lot > small.lot
    tight_stop = decide(equity=20_000.0, risk_pct=0.008, ceiling_pct=0.006,
                        stop_distance=2.0)
    wide_stop = decide(equity=20_000.0, risk_pct=0.008, ceiling_pct=0.006,
                       stop_distance=8.0)
    assert tight_stop.lot > wide_stop.lot                 # stop drives size
    strong = decide(equity=20_000.0, risk_pct=0.008, ceiling_pct=0.006)
    weak = decide(equity=20_000.0, risk_pct=0.002, ceiling_pct=0.006)
    assert strong.lot > weak.lot                          # evidence drives size


def test_broker_step_math_rounds_down_never_up():
    # $20k equity, 0.55% = $110 over 7.0 stop -> raw 0.15714 -> 0.15 lot.
    out = resolve_lot(equity=20_000.0, risk_pct=0.0055, ceiling_pct=0.006,
                      stop_distance=7.0)
    assert out.verdict == LotVerdict.SIZED
    assert out.raw_lot == pytest.approx(0.15714, abs=1e-4)
    assert out.lot == pytest.approx(0.15)
    assert out.realized_risk_usd <= 110.0 + 1e-6          # never above budget


def test_milestone_context_per_phase():
    assert "$10,000" in decide(equity=5_000).milestone
    assert "$15,000" in decide(equity=12_000, ceiling_pct=0.008).milestone
    assert "$25,000" in decide(equity=20_000, ceiling_pct=0.006).milestone
    assert "beyond" in decide(equity=40_000, ceiling_pct=0.005).milestone


def test_diagnostics_serialize_completely():
    d = decide().to_dict()
    for key in ("lot", "verdict", "reason", "risk_pct", "risk_usd",
                "ceiling_pct", "ceiling_usd", "stop_distance",
                "min_lot_risk_usd", "raw_lot", "rounded_lot",
                "realized_risk_usd", "realized_risk_pct", "phase",
                "milestone"):
        assert key in d
