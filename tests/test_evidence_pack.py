"""Tests for the LIVE-VERIFY-001 evidence pack generator.

These verify the generator stays HONEST and SAFE:
- every source module is classified (no silent omissions),
- no module is marked live-proven (WINMT5-001 has not run),
- no module is cleared for demo order execution,
- the rendered markdown contains every required section.
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GEN_PATH = REPO_ROOT / "scripts" / "generate_evidence_pack.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_evidence_pack", GEN_PATH)
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass annotation resolution can find the module.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gen = _load_generator()


def test_every_src_module_is_classified():
    # build_evidence() raises if any discovered module lacks a classification.
    evidence = gen.build_evidence()
    discovered = set(gen._discover_src_modules())
    reported = {m["module"] for m in evidence["modules"]}
    assert reported == discovered
    assert evidence["totals"]["modules"] == len(discovered)


def test_all_modules_implemented():
    evidence = gen.build_evidence()
    assert all(m["implemented"] for m in evidence["modules"])
    assert evidence["totals"]["implemented"] == evidence["totals"]["modules"]


def test_no_module_is_live_proven():
    evidence = gen.build_evidence()
    assert evidence["totals"]["live_proven"] == 0
    assert all(m["live_proven"] is False for m in evidence["modules"])


def test_no_module_ready_for_demo_orders():
    evidence = gen.build_evidence()
    assert evidence["totals"]["ready_for_demo_order"] == 0
    assert all(m["ready_for_demo_order"] is False for m in evidence["modules"])


def test_mt5_boundary_modules_need_windows_validation():
    evidence = gen.build_evidence()
    by_name = {m["module"]: m for m in evidence["modules"]}
    for name in (
        "src.broker.mt5_data_adapter",
        "src.execution.gateway",
        "src.execution.shadow",
    ):
        assert by_name[name]["needs_windows_mt5"] is True
        assert by_name[name]["external_mock"] is True


def test_test_counts_are_populated_for_core_modules():
    evidence = gen.build_evidence()
    by_name = {m["module"]: m for m in evidence["modules"]}
    # A module with its own dedicated test file should report a positive count.
    assert by_name["src.risk.governor"]["test_count"] > 0
    assert by_name["src.risk.leverage_sizing"]["test_count"] > 0
    assert by_name["src.risk.pyramiding"]["test_count"] > 0


def test_markdown_has_required_sections():
    evidence = gen.build_evidence()
    md = gen.render_markdown(evidence, generated_at="2026-06-09T00:00:00Z")
    for section in (
        "# Implementation Evidence Pack (LIVE-VERIFY-001)",
        "## Totals",
        "## Module Matrix",
        "## What is stubbed / mocked",
        "## What is NOT live-proven",
        "## What still requires Windows MT5 validation",
        "## What is NOT ready for demo order execution",
        "## Phase 12 gate status",
    ):
        assert section in md
    assert "FORBIDDEN" in md  # real trading status surfaced


def test_generator_has_no_order_or_trade_calls():
    source = GEN_PATH.read_text(encoding="utf-8")
    # No order invocation (the docstring may mention the name in prose).
    assert "order_send(" not in source
    # No real-trading enablement (strings built so this test never self-matches
    # the pre-demo safety checker's tracked-file grep).
    assert ("REAL_TRADING_ENABLED" + "=true") not in source
    assert ("ALLOW_REAL_ORDERS" + "=true") not in source
