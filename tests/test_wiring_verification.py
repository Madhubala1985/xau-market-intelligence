"""Tests for the executable wiring verification (FINAL-INTELLIGENCE)."""

import json
from pathlib import Path

from src.reflection.wiring_verification import (
    render_wiring_markdown,
    verify_wiring,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
VALID = {"LIVE", "PARTIAL", "UNAVAILABLE_BY_CONFIG", "PLACEHOLDER", "MISSING"}


def test_verification_runs_the_real_pipeline_and_finds_no_missing_layer():
    report = verify_wiring(REPO_ROOT)
    assert report.missing == 0, [
        e.layer for e in report.entries if e.status == "MISSING"
    ]
    layers = {e.layer for e in report.entries}
    for required in (
        "mtf_true_data", "liquidity_sweep", "bos_choch", "fvg",
        "order_blocks", "premium_discount", "asian_range",
        "london_ny_expansion", "displacement", "dangerous_volatility",
        "news", "macro_dxy_yields", "futures_confirmation",
        "m1_refinement", "adaptive_risk", "execution_path",
        "opportunity_audit", "journal_reconciliation", "stop_management",
    ):
        assert required in layers, required


def test_every_status_is_a_valid_classification():
    report = verify_wiring(REPO_ROOT)
    for e in report.entries:
        assert e.status in VALID, e
        assert e.evidence  # every entry carries observed evidence


def test_provider_layers_reflect_config_availability(tmp_path):
    # In an empty repo root the provider layers are honestly unavailable.
    report = verify_wiring(tmp_path)
    by_layer = {e.layer: e for e in report.entries}
    assert by_layer["news"].status == "UNAVAILABLE_BY_CONFIG"
    assert by_layer["macro_dxy_yields"].status == "UNAVAILABLE_BY_CONFIG"
    assert by_layer["futures_confirmation"].status == "UNAVAILABLE_BY_CONFIG"
    # ...while the executed pipeline layers stay LIVE regardless of config.
    assert by_layer["liquidity_sweep"].status == "LIVE"
    assert by_layer["adaptive_risk"].status == "LIVE"


def test_report_renders_and_serializes():
    report = verify_wiring(REPO_ROOT)
    md = render_wiring_markdown(report)
    assert "Final Wiring Verification" in md
    payload = report.to_dict()
    json.dumps(payload)
    assert payload["summary"]["MISSING"] == 0
