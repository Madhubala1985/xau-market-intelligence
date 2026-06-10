#!/usr/bin/env python3
"""LIVE-VERIFY-001: implementation evidence pack generator.

Produces a compact, honest evidence pack describing, per source module:
  1. what is implemented,
  2. what is tested,
  3. what is stubbed / mocked at an external boundary,
  4. what is NOT live-proven,
  5. what is ready for live shadow,
  6. what is NOT ready for demo order execution,
  7. what still requires Windows MT5 validation.

This is a REPORT GENERATOR only. It performs read-only filesystem introspection
(it does NOT import or execute src modules, never calls order_send, never trades,
never reads or prints credentials). Output is written under reports/runtime/,
which is a git-ignored runtime artifact directory; re-run this script to refresh.

Usage:
    python scripts/generate_evidence_pack.py            # write md + json
    python scripts/generate_evidence_pack.py --stdout   # also print markdown
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
TESTS_DIR = REPO_ROOT / "tests"
OUT_DIR = REPO_ROOT / "reports" / "runtime"

_TEST_DEF = re.compile(r"^\s*def (test_\w+)\s*\(", re.MULTILINE)


@dataclass(frozen=True)
class ModuleEvidence:
    """Evidence for a single source module (all flags are honest, not aspirational)."""

    module: str                       # dotted path, e.g. src.risk.governor
    layer: str
    summary: str
    implemented: bool
    tested: bool
    test_file: Optional[str]          # relative path under tests/, if any
    test_count: int                   # auto-counted test functions
    test_note: str                    # e.g. "indirect (covered via ...)"
    external_mock: bool               # external boundary (MT5) injected/faked in tests
    live_proven: bool                 # proven against a real MT5 demo terminal
    ready_for_shadow: bool            # safe to run in live/replay shadow (no orders)
    ready_for_demo_order: bool        # cleared for demo order_send (Phase 12 gates)
    needs_windows_mt5: bool           # requires WINMT5-001 validation on Windows host


# --------------------------------------------------------------------------
# Curated classification table.
#
# Every src module MUST appear here; build_evidence() raises if a discovered
# module is unclassified, so the report can never silently omit something.
#
# Invariants encoded by policy (21/22/23 + CLAUDE.md):
#   - live_proven is False everywhere: no real MT5 terminal evidence exists yet
#     (WINMT5-001 not run).
#   - ready_for_demo_order is False everywhere: DEMO-001 preflight gates not passed.
# --------------------------------------------------------------------------

# Pure, deterministic analysis/decision modules: implemented, tested, shadow-ready,
# no MT5 dependency, not live-proven, not cleared for demo orders.
_PURE_SHADOW_READY = dict(
    external_mock=False,
    live_proven=False,
    ready_for_shadow=True,
    ready_for_demo_order=False,
    needs_windows_mt5=False,
)

# MT5 / order boundary modules: real code, but tests inject a fake client; require
# Windows MT5 validation; not live-proven; not cleared for demo orders.
_MT5_BOUNDARY = dict(
    external_mock=True,
    live_proven=False,
    ready_for_shadow=True,
    ready_for_demo_order=False,
    needs_windows_mt5=True,
)

_TABLE: Dict[str, dict] = {
    # utils
    "src.utils.time": dict(
        layer="utils", summary="UTC normalization helpers",
        test_file=None, test_note="indirect (covered via schemas/aggregation)",
        **_PURE_SHADOW_READY),
    # data
    "src.data.enums": dict(
        layer="data", summary="shared enumerations",
        test_file="test_schemas.py", test_note="indirect (used across schema tests)",
        **_PURE_SHADOW_READY),
    "src.data.schemas": dict(
        layer="data", summary="frozen, validated core data models",
        test_file="test_schemas.py", test_note="", **_PURE_SHADOW_READY),
    "src.data.validation": dict(
        layer="data", summary="series-level data validation engine",
        test_file="test_data_validation.py", test_note="", **_PURE_SHADOW_READY),
    "src.data.aggregation": dict(
        layer="data", summary="no-look-ahead timeframe aggregation",
        test_file="test_aggregation.py", test_note="", **_PURE_SHADOW_READY),
    "src.data.sessions": dict(
        layer="data", summary="session / kill-zone tiling",
        test_file="test_sessions.py", test_note="", **_PURE_SHADOW_READY),
    # structure
    "src.structure.market_structure": dict(
        layer="structure", summary="swing / BOS / CHOCH detection",
        test_file="test_market_structure.py", test_note="", **_PURE_SHADOW_READY),
    "src.structure.zones": dict(
        layer="structure", summary="FVG / order block / supply-demand zones",
        test_file="test_zones.py", test_note="", **_PURE_SHADOW_READY),
    "src.structure.premium_discount": dict(
        layer="structure", summary="premium/discount dealing range",
        test_file="test_premium_discount.py", test_note="", **_PURE_SHADOW_READY),
    # liquidity
    "src.liquidity.liquidity_map": dict(
        layer="liquidity", summary="resting-liquidity level map",
        test_file="test_liquidity_map.py", test_note="", **_PURE_SHADOW_READY),
    "src.liquidity.sweep": dict(
        layer="liquidity", summary="liquidity sweep classification",
        test_file="test_sweep.py", test_note="", **_PURE_SHADOW_READY),
    # regime
    "src.regime.htf_bias": dict(
        layer="regime", summary="Daily/4H higher-timeframe bias",
        test_file="test_htf_bias.py", test_note="", **_PURE_SHADOW_READY),
    "src.regime.regime_engine": dict(
        layer="regime", summary="trend/range/expansion/etc. regime",
        test_file="test_regime.py", test_note="", **_PURE_SHADOW_READY),
    # orderflow
    "src.orderflow.proxy": dict(
        layer="orderflow", summary="order-flow PROXY metrics (no trade signal)",
        test_file="test_orderflow_proxy.py", test_note="", **_PURE_SHADOW_READY),
    "src.orderflow.futures_confirmation": dict(
        layer="orderflow", summary="gold futures confirmation (context only)",
        test_file="test_futures_confirmation.py", test_note="", **_PURE_SHADOW_READY),
    # strategy
    "src.strategy.hypothesis": dict(
        layer="strategy", summary="trade hypothesis composer",
        test_file="test_hypothesis.py", test_note="", **_PURE_SHADOW_READY),
    "src.strategy.scoring": dict(
        layer="strategy", summary="confidence/uncertainty scoring",
        test_file="test_scoring.py", test_note="", **_PURE_SHADOW_READY),
    "src.regime.chop_classifier": dict(
        layer="regime",
        summary="CHOPPY decomposition into graded subtypes (INTELLIGENCE-001)",
        test_file="test_chop_classifier.py", test_note="", **_PURE_SHADOW_READY),
    "src.strategy.confluence": dict(
        layer="strategy",
        summary="MTF alignment + graded confluence scoring (INTELLIGENCE-001)",
        test_file="test_confluence.py", test_note="", **_PURE_SHADOW_READY),
    "src.risk.adaptive_risk": dict(
        layer="risk",
        summary="evidence-driven adaptive risk budget, policy-capped (INTELLIGENCE-001)",
        test_file="test_adaptive_risk.py", test_note="", **_PURE_SHADOW_READY),
    "src.reflection.opportunity_audit": dict(
        layer="reflection",
        summary="long no-trade opportunity audit (INTELLIGENCE-001; offline)",
        test_file="test_opportunity_audit.py", test_note="", **_PURE_SHADOW_READY),
    "src.strategy.pipeline": dict(
        layer="strategy", summary="DecisionPipeline orchestration (no execution)",
        test_file="test_pipeline.py", test_note="", **_PURE_SHADOW_READY),
    # trade management
    "src.trade_management.stop_placement": dict(
        layer="trade_management", summary="stop placement intelligence",
        test_file="test_stop_placement.py", test_note="", **_PURE_SHADOW_READY),
    "src.trade_management.trailing": dict(
        layer="trade_management", summary="trailing stop / partials engine",
        test_file="test_trailing.py", test_note="", **_PURE_SHADOW_READY),
    # risk
    "src.risk.governor": dict(
        layer="risk", summary="Risk Governor (final authority, no execution)",
        test_file="test_risk_governor.py", test_note="", **_PURE_SHADOW_READY),
    "src.risk.position_sizing": dict(
        layer="risk", summary="P7-002 risk-based position sizing",
        test_file="test_position_sizing.py", test_note="", **_PURE_SHADOW_READY),
    "src.risk.leverage_sizing": dict(
        layer="risk", summary="leverage-aware, tiered sizing (RISK-001)",
        test_file="test_leverage_sizing.py", test_note="", **_PURE_SHADOW_READY),
    "src.risk.pyramiding": dict(
        layer="risk", summary="protected pyramiding guard (RISK-001)",
        test_file="test_pyramiding.py", test_note="", **_PURE_SHADOW_READY),
    # journal / reflection
    "src.journal.journal": dict(
        layer="journal", summary="append-only restart-safe trade journal",
        test_file="test_journal.py", test_note="", **_PURE_SHADOW_READY),
    "src.reflection.reflection": dict(
        layer="reflection", summary="offline mistake/reflection engine",
        test_file="test_reflection.py", test_note="", **_PURE_SHADOW_READY),
    "src.reflection.readiness": dict(
        layer="reflection", summary="real-mode readiness review (report only)",
        test_file="test_readiness.py", test_note="", **_PURE_SHADOW_READY),
    # backtest
    "src.backtest.backtester": dict(
        layer="backtest", summary="causal event-driven backtester",
        test_file="test_backtester.py", test_note="", **_PURE_SHADOW_READY),
    "src.backtest.walk_forward": dict(
        layer="backtest", summary="walk-forward validation",
        test_file="test_walk_forward.py", test_note="", **_PURE_SHADOW_READY),
    # broker (MT5 boundary)
    "src.broker.errors": dict(
        layer="broker", summary="broker error types",
        test_file="test_mt5_data_adapter.py",
        test_note="indirect (covered via adapter tests)", **_MT5_BOUNDARY),
    "src.broker.mt5_settings": dict(
        layer="broker", summary="MT5 settings loader (DEMO-gated, masked)",
        test_file="test_mt5_data_adapter.py", test_note="", **_MT5_BOUNDARY),
    "src.broker.mt5_data_adapter": dict(
        layer="broker", summary="read-only MT5 demo data adapter (no order_send)",
        test_file="test_mt5_data_adapter.py", test_note="", **_MT5_BOUNDARY),
    "src.broker.connectivity": dict(
        layer="broker", summary="read-only MT5 demo connectivity validator (WINMT5-001)",
        test_file="test_winmt5_connectivity.py", test_note="", **_MT5_BOUNDARY),
    # execution (order boundary)
    "src.execution.gateway": dict(
        layer="execution", summary="execution gateway (gated; default no-send)",
        test_file="test_execution_gateway.py", test_note="", **_MT5_BOUNDARY),
    "src.execution.shadow": dict(
        layer="execution", summary="ShadowRunner (logs only, never sends)",
        test_file="test_shadow.py", test_note="", **_MT5_BOUNDARY),
    "src.execution.live_shadow": dict(
        layer="execution",
        summary="live MT5 data -> pipeline -> shadow journal (LIVE-001; never sends)",
        test_file="test_live_shadow.py", test_note="", **_MT5_BOUNDARY),
    "src.risk.state_tracker": dict(
        layer="risk",
        summary="journal-driven governor inputs: daily/weekly loss, streaks",
        test_file="test_risk_state_tracker.py", test_note="", **_PURE_SHADOW_READY),
    "src.risk.news_guard": dict(
        layer="risk",
        summary="fail-closed news-risk guard: manual block + static calendar (F-5)",
        test_file="test_news_guard.py", test_note="", **_PURE_SHADOW_READY),
    "src.execution.positions": dict(
        layer="execution",
        summary="broker-vs-journal position reconciliation, orphan detection (F-4)",
        test_file="test_positions.py", test_note="", **_MT5_BOUNDARY),
    "src.execution.demo_planner": dict(
        layer="execution",
        summary="sized+guarded+governed demo trade plans; never sends (F-3)",
        test_file="test_demo_planner.py", test_note="", **_MT5_BOUNDARY),
    "src.execution.demo_session": dict(
        layer="execution",
        summary="supervised demo session loop (DEMO-002; gateway-only orders)",
        test_file="test_demo_session.py", test_note="", **_MT5_BOUNDARY),
    "src.trade_management.position_manager": dict(
        layer="trade_management",
        summary="BE/trailing stop proposals for open positions (F-4; no MT5 calls)",
        test_file="test_positions.py", test_note="", **_PURE_SHADOW_READY),
    "src.execution.kill_switch": dict(
        layer="execution",
        summary="file-based manual halt honored by the gateway (DEMO-001)",
        test_file="test_demo_preflight.py", test_note="", **_PURE_SHADOW_READY),
    "src.execution.preflight": dict(
        layer="execution",
        summary="demo execution preflight gates (DEMO-001; places no orders)",
        test_file="test_demo_preflight.py", test_note="", **_MT5_BOUNDARY),
    "src.execution.session_profiles": dict(
        layer="execution",
        summary="policy-bounded session risk profiles (DEMO-EVAL; can only tighten)",
        test_file="test_session_profiles.py", test_note="", **_PURE_SHADOW_READY),
    "src.execution.market_hours": dict(
        layer="execution",
        summary="XAU market-hours schedule for closed-market pausing (CONTINUOUS-001)",
        test_file="test_market_hours.py", test_note="", **_PURE_SHADOW_READY),
    "src.execution.trading_service": dict(
        layer="execution",
        summary="continuous trading service loop + live terminal progress (CONTINUOUS-001)",
        test_file="test_trading_service.py", test_note="", **_MT5_BOUNDARY),
    "src.reflection.demo_evaluation": dict(
        layer="reflection",
        summary="post-session evaluation + reflection reports (DEMO-EVAL; offline)",
        test_file="test_demo_evaluation.py", test_note="", **_PURE_SHADOW_READY),
}


def _discover_src_modules() -> List[str]:
    """Return dotted module paths for every non-trivial src module."""
    modules: List[str] = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        if path.name == "__init__.py" or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(REPO_ROOT).with_suffix("")
        modules.append(".".join(rel.parts))
    return modules


def _count_tests(test_file: Optional[str]) -> int:
    if not test_file:
        return 0
    path = TESTS_DIR / test_file
    if not path.is_file():
        return 0
    return len(_TEST_DEF.findall(path.read_text(encoding="utf-8")))


def build_evidence() -> Dict[str, object]:
    """Build the structured evidence pack (deterministic; no timestamp)."""
    discovered = _discover_src_modules()
    missing = [m for m in discovered if m not in _TABLE]
    if missing:
        raise RuntimeError(
            "evidence table is missing classifications for: " + ", ".join(missing)
        )

    modules: List[ModuleEvidence] = []
    for name in discovered:
        spec = _TABLE[name]
        test_file = spec.get("test_file")
        count = _count_tests(test_file)
        modules.append(
            ModuleEvidence(
                module=name,
                layer=spec["layer"],
                summary=spec["summary"],
                implemented=True,
                tested=(count > 0 or bool(spec.get("test_note"))),
                test_file=test_file,
                test_count=count,
                test_note=spec.get("test_note", ""),
                external_mock=spec["external_mock"],
                live_proven=spec["live_proven"],
                ready_for_shadow=spec["ready_for_shadow"],
                ready_for_demo_order=spec["ready_for_demo_order"],
                needs_windows_mt5=spec["needs_windows_mt5"],
            )
        )

    # Count test functions once per distinct test file (several modules share a
    # file, e.g. the broker modules all map to test_mt5_data_adapter.py).
    distinct_test_files = {m.test_file: m.test_count for m in modules if m.test_file}
    totals = {
        "modules": len(modules),
        "implemented": sum(m.implemented for m in modules),
        "tested": sum(m.tested for m in modules),
        "mapped_test_files": len(distinct_test_files),
        "test_functions_in_mapped_files": sum(distinct_test_files.values()),
        "external_mock_boundary": sum(m.external_mock for m in modules),
        "live_proven": sum(m.live_proven for m in modules),
        "ready_for_shadow": sum(m.ready_for_shadow for m in modules),
        "ready_for_demo_order": sum(m.ready_for_demo_order for m in modules),
        "needs_windows_mt5": sum(m.needs_windows_mt5 for m in modules),
    }

    return {
        "task": "LIVE-VERIFY-001",
        "phase": "Phase 12: Live Demo Readiness",
        "real_trading": "FORBIDDEN",
        "demo_orders": "BLOCKED until WINMT5-001, LIVE-001, LIVE-002, DEMO-001 pass",
        "totals": totals,
        "modules": [asdict(m) for m in modules],
        "gates": _gate_status(),
    }


def _gate_status() -> List[Dict[str, str]]:
    """Phase 12 gate sequence status (21_LIVE_DEMO_VALIDATION_PLAN.md)."""
    return [
        {"gate": "RISK-001", "name": "Leverage-aware sizing + protected pyramiding",
         "status": "DONE"},
        {"gate": "LIVE-VERIFY-001", "name": "Implementation evidence pack",
         "status": "IN_PROGRESS"},
        {"gate": "WINMT5-001", "name": "MT5 demo connectivity (Windows host)",
         "status": "NOT_STARTED"},
        {"gate": "LIVE-001", "name": "Live/replay data -> pipeline -> shadow",
         "status": "NOT_STARTED"},
        {"gate": "LIVE-002", "name": "Supervised live shadow session",
         "status": "NOT_STARTED"},
        {"gate": "DEMO-001", "name": "Demo execution preflight",
         "status": "NOT_STARTED"},
        {"gate": "DEMO-002", "name": "Supervised MT5 demo trading run",
         "status": "NOT_STARTED"},
    ]


def _yn(value: bool) -> str:
    return "yes" if value else "no"


def render_markdown(evidence: Dict[str, object], *, generated_at: str) -> str:
    t = evidence["totals"]
    lines: List[str] = []
    lines.append("# Implementation Evidence Pack (LIVE-VERIFY-001)")
    lines.append("")
    lines.append(f"- Generated: {generated_at}")
    lines.append(f"- Phase: {evidence['phase']}")
    lines.append(f"- Real trading: **{evidence['real_trading']}**")
    lines.append(f"- Demo orders: **{evidence['demo_orders']}**")
    lines.append("")
    lines.append("## Totals")
    lines.append("")
    lines.append(f"- Modules: {t['modules']}")
    lines.append(f"- Implemented: {t['implemented']}/{t['modules']}")
    lines.append(f"- Tested: {t['tested']}/{t['modules']} "
                 f"({t['test_functions_in_mapped_files']} test functions across "
                 f"{t['mapped_test_files']} mapped test files)")
    lines.append(f"- External (MT5) boundary mocked in tests: {t['external_mock_boundary']}")
    lines.append(f"- Live-proven against real MT5: {t['live_proven']} "
                 f"(none — WINMT5-001 not run)")
    lines.append(f"- Ready for live shadow: {t['ready_for_shadow']}/{t['modules']}")
    lines.append(f"- Ready for demo order execution: {t['ready_for_demo_order']}/{t['modules']} "
                 f"(blocked until Phase 12 gates pass)")
    lines.append(f"- Requires Windows MT5 validation: {t['needs_windows_mt5']}")
    lines.append("")

    lines.append("## Module Matrix")
    lines.append("")
    header = ("| Module | Layer | Impl | Tested (#) | Ext-mock | Live-proven | "
              "Shadow-ready | Demo-order-ready | Needs Win MT5 |")
    sep = "|" + "|".join(["---"] * 9) + "|"
    lines.append(header)
    lines.append(sep)
    for m in evidence["modules"]:  # type: ignore[index]
        tested = f"{_yn(m['tested'])} ({m['test_count']})"
        lines.append(
            f"| {m['module']} | {m['layer']} | {_yn(m['implemented'])} | {tested} | "
            f"{_yn(m['external_mock'])} | {_yn(m['live_proven'])} | "
            f"{_yn(m['ready_for_shadow'])} | {_yn(m['ready_for_demo_order'])} | "
            f"{_yn(m['needs_windows_mt5'])} |"
        )
    lines.append("")

    lines.append("## What is stubbed / mocked")
    lines.append("")
    lines.append("These modules are real implementations, but their EXTERNAL "
                 "boundary (the MetaTrader5 client) is dependency-injected and "
                 "faked in tests. They are not yet exercised against a real MT5 "
                 "terminal:")
    lines.append("")
    for m in evidence["modules"]:  # type: ignore[index]
        if m["external_mock"]:
            lines.append(f"- {m['module']} — {m['summary']}")
    lines.append("")

    lines.append("## What is NOT live-proven")
    lines.append("")
    lines.append("No module has been validated against a real MT5 demo terminal "
                 "(WINMT5-001 has not run). All `live-proven` flags are `no`.")
    lines.append("")

    lines.append("## What still requires Windows MT5 validation")
    lines.append("")
    for m in evidence["modules"]:  # type: ignore[index]
        if m["needs_windows_mt5"]:
            lines.append(f"- {m['module']} — {m['summary']}")
    lines.append("")

    lines.append("## What is NOT ready for demo order execution")
    lines.append("")
    lines.append("Demo order execution remains BLOCKED for the whole system until "
                 "WINMT5-001, LIVE-001, LIVE-002, and DEMO-001 pass. No module is "
                 "cleared for `order_send`.")
    lines.append("")

    lines.append("## Phase 12 gate status")
    lines.append("")
    lines.append("| Gate | Name | Status |")
    lines.append("|---|---|---|")
    for g in evidence["gates"]:  # type: ignore[index]
        lines.append(f"| {g['gate']} | {g['name']} | {g['status']} |")
    lines.append("")
    return "\n".join(lines)


def write_pack(evidence: Dict[str, object]) -> Dict[str, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    md = render_markdown(evidence, generated_at=generated_at)
    payload = {"generated_at": generated_at, **evidence}

    md_path = OUT_DIR / "evidence_pack.md"
    json_path = OUT_DIR / "evidence_pack.json"
    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"markdown": md_path, "json": json_path}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdout", action="store_true", help="also print markdown")
    args = parser.parse_args()

    evidence = build_evidence()
    paths = write_pack(evidence)
    print(f"Wrote {paths['markdown'].relative_to(REPO_ROOT)}")
    print(f"Wrote {paths['json'].relative_to(REPO_ROOT)}")
    if args.stdout:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print()
        print(render_markdown(evidence, generated_at=generated_at))


if __name__ == "__main__":
    main()
