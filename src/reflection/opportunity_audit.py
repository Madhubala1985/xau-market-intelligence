"""Long no-trade opportunity audit (Task INTELLIGENCE-001).

When the continuous service goes a long stretch without an entry during an
ACTIVE session, the right question is not "why is the model broken?" but
"was no-trade correct?" — and it must be answered from evidence, not vibes.

This auditor reads the per-cycle intelligence stats (regime subtype, MTF
alignment, confluence, sweep/displacement statuses, entry actions) collected
by the session and produces a classified report:

- NO_TRADE_CORRECT      the market genuinely offered nothing (dangerous /
                        low-quality conditions dominated, no near-misses),
- POSSIBLY_TOO_STRICT   repeated near-misses: evidence was present but gates
                        kept blocking — a Hypothesis for backtesting,
- MIXED                 some of both; read the findings.

Every finding carries one of the standard classifications (Proven Defect /
High-Confidence Defect / Hypothesis / Observation / Market Artifact / Design
Improvement). Offline analysis only: this module never mutates policy or
parameters (04_ADAPTATION_POLICY.md) and holds no credentials.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from src.reflection.demo_evaluation import Finding, FindingClass

_ACTIVE_SESSIONS = {"LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"}
_HARD_CHOP = {"DANGEROUS_CHOP", "LOW_QUALITY_CHOP"}
_NEAR_MISS_CONFLUENCE = 0.55


@dataclass(frozen=True)
class OpportunityAudit:
    """Audit of one long no-trade stretch (credential-free)."""

    cycles_examined: int
    active_session_cycles: int
    trades_taken: int
    near_misses: int                 # confluence >= 0.55 but no entry
    mtf_aligned_cycles: int
    sweep_evidence_cycles: int
    displacement_cycles: int
    tradeable_chop_cycles: int
    hard_block_chop_cycles: int
    verdict: str                     # NO_TRADE_CORRECT | POSSIBLY_TOO_STRICT | MIXED
    detail: str
    regime_distribution: Dict[str, int]
    findings: Tuple[Finding, ...]

    def to_dict(self) -> dict:
        return {
            "task": "INTELLIGENCE-001",
            "cycles_examined": self.cycles_examined,
            "active_session_cycles": self.active_session_cycles,
            "trades_taken": self.trades_taken,
            "near_misses": self.near_misses,
            "mtf_aligned_cycles": self.mtf_aligned_cycles,
            "sweep_evidence_cycles": self.sweep_evidence_cycles,
            "displacement_cycles": self.displacement_cycles,
            "tradeable_chop_cycles": self.tradeable_chop_cycles,
            "hard_block_chop_cycles": self.hard_block_chop_cycles,
            "verdict": self.verdict,
            "detail": self.detail,
            "regime_distribution": dict(self.regime_distribution),
            "findings": [f.to_dict() for f in self.findings],
        }


def build_opportunity_audit(stats: Sequence[dict]) -> OpportunityAudit:
    """Audit a window of cycle-stat dicts (CycleStat.to_dict output)."""
    stats = list(stats)
    active = [s for s in stats if (s.get("session") or "") in _ACTIVE_SESSIONS]
    trades = sum(
        1 for s in stats if s.get("entry_action") in ("SENT", "SIMULATED")
    )
    regimes = Counter(s.get("regime") or "UNKNOWN" for s in stats)

    near_misses = 0
    mtf_aligned = 0
    sweep_evidence = 0
    displacement = 0
    tradeable_chop = 0
    hard_chop = 0
    for s in stats:
        score = s.get("confluence_score")
        if (
            score is not None and score >= _NEAR_MISS_CONFLUENCE
            and s.get("entry_action") not in ("SENT", "SIMULATED")
        ):
            near_misses += 1
        if s.get("mtf_direction") and (s.get("mtf_score") or 0) >= 0.6:
            mtf_aligned += 1
        intel = s.get("intel") or {}
        statuses = (intel.get("confluence") or {}).get("statuses", {})
        if statuses.get("sweep") in ("TRUE_SWEEP", "PENDING"):
            sweep_evidence += 1
        if (intel.get("displacement_ratio") or 0) >= 1.5:
            displacement += 1
        subtype = s.get("regime_subtype")
        if subtype in _HARD_CHOP:
            hard_chop += 1
        elif subtype is not None:
            tradeable_chop += 1

    findings: List[Finding] = []
    n = max(1, len(stats))
    near_rate = near_misses / n

    if trades == 0 and near_rate >= 0.20:
        verdict = "POSSIBLY_TOO_STRICT"
        detail = (
            f"{near_misses}/{len(stats)} cycles reached confluence >= "
            f"{_NEAR_MISS_CONFLUENCE} without any entry"
        )
        findings.append(Finding(
            FindingClass.HYPOTHESIS,
            "gates may be over-filtering",
            detail + "; whether those were profitable opportunities is "
            "unproven without hindsight data",
            "backtest before changing",
        ))
    elif trades == 0 and (hard_chop / n >= 0.5 or near_misses == 0):
        verdict = "NO_TRADE_CORRECT"
        detail = (
            f"hard-block conditions dominated ({hard_chop}/{len(stats)} "
            f"dangerous/low-quality chop cycles, {near_misses} near-misses)"
        )
        findings.append(Finding(
            FindingClass.MARKET_ARTIFACT,
            "market offered no qualifying evidence",
            detail + "; staying flat was correct patience",
            "monitor",
        ))
    else:
        verdict = "MIXED"
        detail = (
            f"{trades} entr(ies), {near_misses} near-miss(es), "
            f"{hard_chop} hard-block chop cycle(s)"
        )
        findings.append(Finding(
            FindingClass.OBSERVATION,
            "mixed window",
            detail,
            "monitor",
        ))

    if mtf_aligned > 0 and sweep_evidence > 0 and displacement > 0 and trades == 0:
        findings.append(Finding(
            FindingClass.HYPOTHESIS,
            "aligned MTF + sweep + displacement coincided without an entry",
            f"mtf_aligned={mtf_aligned}, sweep_evidence={sweep_evidence}, "
            f"displacement={displacement} cycles in this window; check which "
            "gate blocked on those specific cycles (entry_detail per cycle)",
            "backtest before changing",
        ))
    if sweep_evidence == 0 and displacement == 0 and trades == 0:
        findings.append(Finding(
            FindingClass.OBSERVATION,
            "no sweep or displacement evidence appeared",
            "the two strongest entry triggers were absent the whole window",
            "monitor",
        ))

    return OpportunityAudit(
        cycles_examined=len(stats),
        active_session_cycles=len(active),
        trades_taken=trades,
        near_misses=near_misses,
        mtf_aligned_cycles=mtf_aligned,
        sweep_evidence_cycles=sweep_evidence,
        displacement_cycles=displacement,
        tradeable_chop_cycles=tradeable_chop,
        hard_block_chop_cycles=hard_chop,
        verdict=verdict,
        detail=detail,
        regime_distribution=dict(regimes),
        findings=tuple(findings),
    )


def render_opportunity_audit_markdown(audit: OpportunityAudit) -> str:
    lines = [
        "# Opportunity Audit (INTELLIGENCE-001)",
        "",
        f"- Verdict: **{audit.verdict}**",
        f"- Detail: {audit.detail}",
        f"- Cycles examined: {audit.cycles_examined} "
        f"(active-session: {audit.active_session_cycles})",
        f"- Trades taken: {audit.trades_taken}",
        f"- Near-misses (confluence >= {_NEAR_MISS_CONFLUENCE}, no entry): "
        f"{audit.near_misses}",
        f"- MTF-aligned cycles: {audit.mtf_aligned_cycles}",
        f"- Sweep-evidence cycles: {audit.sweep_evidence_cycles}",
        f"- Displacement cycles: {audit.displacement_cycles}",
        f"- Tradeable-chop cycles: {audit.tradeable_chop_cycles}",
        f"- Hard-block-chop cycles: {audit.hard_block_chop_cycles}",
        "",
        "## Regimes",
        "",
    ]
    for regime, count in sorted(audit.regime_distribution.items(),
                                key=lambda kv: -kv[1]):
        lines.append(f"- {regime}: {count}")
    lines += ["", "## Findings", ""]
    for f in audit.findings:
        lines.append(
            f"- **{f.classification.value}** — {f.title}: {f.detail} "
            f"_[{f.action}]_"
        )
    lines.append("")
    return "\n".join(lines)
