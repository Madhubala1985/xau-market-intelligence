"""Demo session evaluation + reflection reports (Task DEMO-EVAL).

Turns one supervised demo session (its session report JSON + the demo trade
journal) into:

1. a SessionEvaluation — the serious performance report: decision totals,
   trades taken/skipped, no-trade reasons, regime/session/confidence/spread
   distributions, news and risk blocks, realized P&L, max drawdown, win/loss,
   mistakes, and findings classified as
       PROVEN_DEFECT / HIGH_CONFIDENCE_DEFECT / HYPOTHESIS / OBSERVATION /
       DESIGN_IMPROVEMENT;
2. a ReflectionReport — what the model did well, where it was too strict or
   too loose, what it may have missed, what it correctly avoided, what must be
   backtested before changing, and what can be fixed immediately.

Honesty rules (04_ADAPTATION_POLICY.md):
- This module is OFFLINE analysis only. It never mutates policy, parameters,
  or live behavior; its output is evidence for human-approved changes.
- Without hindsight price data we cannot PROVE an untaken trade would have
  won; "missed opportunity" claims are therefore classified as HYPOTHESIS and
  routed to "backtest before changing", never to "fix immediately".
- Modes are kept separate: real MT5 demo orders (journal records carrying an
  MT5 ticket), dry-run simulated orders (counted by the session), and shadow
  decisions (analysis-only journal decisions) are never summed together.

No credentials are read, stored, or emitted.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from src.data.enums import TradeOutcome
from src.data.schemas import TradeDecision, TradeRecord
from src.reflection.reflection import ReflectionEngine
from src.risk.state_tracker import collapse_records

# Regimes in which "no trade" is the correct behavior, not a missed chance.
_UNTRADEABLE_REGIMES = {"CHOPPY", "NEWS_RISK", "NO_TRADE", "COMPRESSION"}
_CLOSED_OUTCOMES = {TradeOutcome.WIN, TradeOutcome.LOSS, TradeOutcome.BREAKEVEN}
_HIGH_CONFIDENCE = 0.70


class FindingClass(str, Enum):
    PROVEN_DEFECT = "PROVEN_DEFECT"
    HIGH_CONFIDENCE_DEFECT = "HIGH_CONFIDENCE_DEFECT"
    HYPOTHESIS = "HYPOTHESIS"
    OBSERVATION = "OBSERVATION"
    MARKET_ARTIFACT = "MARKET_ARTIFACT"
    DESIGN_IMPROVEMENT = "DESIGN_IMPROVEMENT"


@dataclass(frozen=True)
class Finding:
    classification: FindingClass
    title: str
    detail: str
    action: str  # "fix immediately" | "backtest before changing" | "monitor"

    def to_dict(self) -> dict:
        return {
            "classification": self.classification.value,
            "title": self.title,
            "detail": self.detail,
            "action": self.action,
        }


@dataclass(frozen=True)
class PerformanceMetrics:
    """Realized performance over the session's CLOSED trades."""

    trades_closed: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float           # wins / (wins + losses); 0.0 if none decided
    pnl_total: float
    max_drawdown: float       # peak-to-trough of the cumulative realized P&L
    open_positions: int

    def to_dict(self) -> dict:
        return {
            "trades_closed": self.trades_closed,
            "wins": self.wins,
            "losses": self.losses,
            "breakeven": self.breakeven,
            "win_rate": round(self.win_rate, 4),
            "pnl_total": round(self.pnl_total, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "open_positions": self.open_positions,
        }


@dataclass(frozen=True)
class SessionEvaluation:
    """The full post-session evaluation (credential-free)."""

    symbol: str
    mode: str
    profile: str
    verdict: str
    started_at_utc: str
    ended_at_utc: str
    cycles: int
    decisions_total: int
    actionable_decisions: int
    approved_decisions: int
    trades_real: int          # actual MT5 demo orders (tickets captured)
    trades_simulated: int     # dry-run rehearsal approvals (never sent)
    trades_rejected: int
    entries_blocked: int
    stop_updates: int
    violations: int
    no_trade_reasons: Dict[str, int]
    entry_actions: Dict[str, int]
    regime_distribution: Dict[str, int]
    session_distribution: Dict[str, int]
    htf_bias_distribution: Dict[str, int]
    confidence_buckets: Dict[str, int]
    spread_stats: Dict[str, float]
    news_risky_cycles: int
    news_unknown_cycles: int
    risk_blocked_cycles: int
    market_untradeable: bool
    performance: PerformanceMetrics
    mistakes: Dict[str, int]
    findings: Tuple[Finding, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "task": "DEMO-EVAL",
            "symbol": self.symbol,
            "mode": self.mode,
            "profile": self.profile,
            "verdict": self.verdict,
            "started_at_utc": self.started_at_utc,
            "ended_at_utc": self.ended_at_utc,
            "cycles": self.cycles,
            "decisions_total": self.decisions_total,
            "actionable_decisions": self.actionable_decisions,
            "approved_decisions": self.approved_decisions,
            "trades_real": self.trades_real,
            "trades_simulated": self.trades_simulated,
            "trades_rejected": self.trades_rejected,
            "entries_blocked": self.entries_blocked,
            "stop_updates": self.stop_updates,
            "violations": self.violations,
            "no_trade_reasons": dict(self.no_trade_reasons),
            "entry_actions": dict(self.entry_actions),
            "regime_distribution": dict(self.regime_distribution),
            "session_distribution": dict(self.session_distribution),
            "htf_bias_distribution": dict(self.htf_bias_distribution),
            "confidence_buckets": dict(self.confidence_buckets),
            "spread_stats": dict(self.spread_stats),
            "news_risky_cycles": self.news_risky_cycles,
            "news_unknown_cycles": self.news_unknown_cycles,
            "risk_blocked_cycles": self.risk_blocked_cycles,
            "market_untradeable": self.market_untradeable,
            "performance": self.performance.to_dict(),
            "mistakes": dict(self.mistakes),
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass(frozen=True)
class ReflectionReport:
    """Post-session reflection: evidence-based, never self-applying."""

    did_well: Tuple[str, ...]
    too_strict: Tuple[str, ...]
    too_loose: Tuple[str, ...]
    missed_opportunities: Tuple[str, ...]
    avoided_correctly: Tuple[str, ...]
    backtest_before_change: Tuple[str, ...]
    fix_immediately: Tuple[str, ...]
    summary: str

    def to_dict(self) -> dict:
        return {
            "task": "DEMO-EVAL",
            "did_well": list(self.did_well),
            "too_strict": list(self.too_strict),
            "too_loose": list(self.too_loose),
            "missed_opportunities": list(self.missed_opportunities),
            "avoided_correctly": list(self.avoided_correctly),
            "backtest_before_change": list(self.backtest_before_change),
            "fix_immediately": list(self.fix_immediately),
            "summary": self.summary,
        }


class SessionEvaluator:
    """Builds a SessionEvaluation from a session report + journal contents."""

    def __init__(self, reflection: Optional[ReflectionEngine] = None) -> None:
        self._reflection = reflection or ReflectionEngine()

    def evaluate(
        self,
        session_payload: dict,
        records: Sequence[TradeRecord],
        decisions: Sequence[TradeDecision] = (),
    ) -> SessionEvaluation:
        report = self._report_of(session_payload)
        stats: List[dict] = list(report.get("cycle_stats", []))
        started = str(report.get("started_at_utc", ""))
        ended = str(report.get("ended_at_utc", ""))

        latest = collapse_records(list(records))
        session_records = self._in_window(latest, started, ended)
        real_trades = [r for r in session_records if self._has_ticket(r)]
        closed = [r for r in real_trades if r.outcome in _CLOSED_OUTCOMES]
        open_now = [r for r in real_trades if r.outcome is TradeOutcome.OPEN]

        performance = self._performance(closed, len(open_now))
        review = self._reflection.review(session_records)
        mistakes = {c.value: n for c, n in review.mistakes}

        # Distributions from cycle stats.
        regime_dist = Counter(s["regime"] for s in stats if s.get("regime"))
        session_dist = Counter(s["session"] for s in stats if s.get("session"))
        bias_dist = Counter(s["htf_bias"] for s in stats if s.get("htf_bias"))
        entry_actions = Counter(
            s.get("entry_action", "NONE") for s in stats
        )
        no_trade_reasons = Counter(
            s["reason"] for s in stats
            if not s.get("approved") and s.get("reason")
        )
        confidence_values = [
            float(s["confidence"]) for s in stats
            if s.get("confidence") is not None
        ]
        spreads = [
            float(s["spread_price"]) for s in stats
            if s.get("spread_price") is not None
        ]
        actionable = sum(
            1 for s in stats if s.get("direction") in ("LONG", "SHORT")
        )
        approved = sum(1 for s in stats if s.get("approved"))
        news_risky = sum(1 for s in stats if s.get("news_risky"))
        news_unknown = sum(1 for s in stats if not s.get("news_known", False))
        risk_blocked = sum(1 for s in stats if s.get("risk_action") == "BLOCK")

        market_untradeable = self._market_untradeable(stats, actionable)

        evaluation = SessionEvaluation(
            symbol=str(report.get("symbol", "")),
            mode=str(report.get("mode", "")),
            profile=str(report.get("profile", "")),
            verdict=str(report.get("verdict", "")),
            started_at_utc=started,
            ended_at_utc=ended,
            cycles=int(report.get("cycles", len(stats))),
            decisions_total=int(report.get("decisions_logged", len(stats))),
            actionable_decisions=actionable,
            approved_decisions=approved,
            trades_real=int(report.get("orders_sent", len(real_trades))),
            trades_simulated=int(report.get("orders_simulated", 0)),
            trades_rejected=int(report.get("orders_rejected", 0)),
            entries_blocked=int(report.get("entries_blocked", 0)),
            stop_updates=int(report.get("stop_updates", 0)),
            violations=int(report.get("violations", 0)),
            no_trade_reasons=dict(no_trade_reasons),
            entry_actions=dict(entry_actions),
            regime_distribution=dict(regime_dist),
            session_distribution=dict(session_dist),
            htf_bias_distribution=dict(bias_dist),
            confidence_buckets=self._buckets(confidence_values),
            spread_stats=self._spread_stats(spreads),
            news_risky_cycles=news_risky,
            news_unknown_cycles=news_unknown,
            risk_blocked_cycles=risk_blocked,
            market_untradeable=market_untradeable,
            performance=performance,
            mistakes=mistakes,
        )
        findings = self._findings(evaluation, stats, session_records)
        return replace(evaluation, findings=tuple(findings))

    # -- findings (classified, honest) -------------------------------------
    def _findings(
        self,
        ev: SessionEvaluation,
        stats: List[dict],
        records: Sequence[TradeRecord],
    ) -> List[Finding]:
        findings: List[Finding] = []

        # Executed trades missing a stop or thesis would be a proven defect:
        # both are schema/gateway-mandatory, so their absence means a layer
        # was bypassed.
        for r in records:
            if r.outcome in (_CLOSED_OUTCOMES | {TradeOutcome.OPEN}):
                if r.stop_loss is None:
                    findings.append(Finding(
                        FindingClass.PROVEN_DEFECT,
                        "executed trade without stop-loss",
                        f"record {r.record_id} has no stop-loss; the gateway "
                        "mandates one — a safety layer was bypassed",
                        "fix immediately",
                    ))
                if not (r.thesis and r.thesis.strip()):
                    findings.append(Finding(
                        FindingClass.PROVEN_DEFECT,
                        "executed trade without thesis",
                        f"record {r.record_id} has no thesis",
                        "fix immediately",
                    ))

        if ev.violations > 0:
            findings.append(Finding(
                FindingClass.HIGH_CONFIDENCE_DEFECT,
                "session recorded violations",
                f"{ev.violations} violation event(s) (see session report "
                "events); the session verdict requires attention",
                "fix immediately",
            ))

        if ev.news_unknown_cycles > 0:
            findings.append(Finding(
                FindingClass.OBSERVATION,
                "news state unknown during some cycles",
                f"{ev.news_unknown_cycles} cycle(s) had no news source; "
                "fail-closed blocking engaged by design. Maintain "
                "configs/news_windows.json before sessions.",
                "monitor",
            ))

        cap_blocked = ev.entry_actions.get("CAP_REACHED", 0)
        if cap_blocked > 0:
            findings.append(Finding(
                FindingClass.OBSERVATION,
                "session order cap blocked approved entries",
                f"{cap_blocked} approved entr(ies) hit the artificial session "
                "max_orders cap. For serious evaluation use a policy-governed "
                "profile (max_orders=None).",
                "monitor",
            ))

        # Approved-but-not-executed with high confidence: possible missed
        # opportunity — honestly a hypothesis until backtested.
        missed = [
            s for s in stats
            if s.get("approved")
            and s.get("entry_action") in ("PLAN_BLOCKED", "ENTRY_BLOCKED",
                                          "CAP_REACHED")
            and (s.get("confidence") or 0.0) >= _HIGH_CONFIDENCE
        ]
        if missed:
            findings.append(Finding(
                FindingClass.HYPOTHESIS,
                "high-confidence entries were blocked",
                f"{len(missed)} approved decision(s) with confidence >= "
                f"{_HIGH_CONFIDENCE} were blocked downstream. Whether they "
                "were profitable opportunities is unproven without hindsight "
                "data.",
                "backtest before changing",
            ))

        # One planner/gateway gate dominating the blocks.
        block_reasons = Counter(
            s.get("entry_detail", "") for s in stats
            if s.get("entry_action") in ("PLAN_BLOCKED", "ENTRY_BLOCKED")
            and s.get("entry_detail")
        )
        if block_reasons:
            top_reason, top_count = block_reasons.most_common(1)[0]
            blocked_total = sum(block_reasons.values())
            if blocked_total >= 3 and top_count / blocked_total >= 0.5:
                findings.append(Finding(
                    FindingClass.HYPOTHESIS,
                    "one gate dominates entry blocks",
                    f"{top_count}/{blocked_total} blocks share one cause: "
                    f"{top_reason[:160]}. The gate may be too strict — or "
                    "correct; evidence needed.",
                    "backtest before changing",
                ))

        if ev.market_untradeable:
            findings.append(Finding(
                FindingClass.OBSERVATION,
                "market conditions were genuinely poor",
                "untradeable regimes (choppy/news/compression) dominated the "
                "window and no setup formed; taking no trades was correct "
                "behavior, not over-filtering.",
                "monitor",
            ))

        if ev.performance.losses >= 2 and ev.performance.win_rate < 0.34:
            findings.append(Finding(
                FindingClass.HYPOTHESIS,
                "low realized win rate",
                f"win rate {ev.performance.win_rate:.0%} over "
                f"{ev.performance.trades_closed} closed trade(s); sample is "
                "small — collect more sessions before concluding.",
                "backtest before changing",
            ))

        if ev.mistakes.get("OVERCONFIDENCE", 0) > 0:
            findings.append(Finding(
                FindingClass.HIGH_CONFIDENCE_DEFECT,
                "losses on high-confidence trades",
                f"{ev.mistakes['OVERCONFIDENCE']} loss(es) carried high "
                "confidence; review the confidence components for those "
                "cycles.",
                "backtest before changing",
            ))

        # Standing design gap recorded by the intelligence audit: zone/PD
        # engines exist but are not wired into the live decision path.
        findings.append(Finding(
            FindingClass.DESIGN_IMPROVEMENT,
            "FVG/order-block and premium-discount engines are not in the "
            "live decision path",
            "src/structure/zones.py and src/structure/premium_discount.py "
            "are implemented and tested but DecisionPipeline does not use "
            "them; setups rely on sweep-reclaim + HTF bias only "
            "(24_INTELLIGENCE_AUDIT_ROADMAP.md).",
            "backtest before changing",
        ))
        return findings

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _report_of(payload: dict) -> dict:
        """Accept either the runner payload (with 'report') or a report dict."""
        inner = payload.get("report")
        if isinstance(inner, dict):
            merged = dict(inner)
            # the runner stores mode/symbol at the top level too
            merged.setdefault("mode", payload.get("mode", ""))
            merged.setdefault("symbol", payload.get("symbol", ""))
            merged.setdefault("profile", payload.get("profile", ""))
            return merged
        return payload

    @staticmethod
    def _has_ticket(record: TradeRecord) -> bool:
        return bool(record.notes and "ticket=" in record.notes)

    @staticmethod
    def _in_window(
        records: Sequence[TradeRecord], started: str, ended: str
    ) -> List[TradeRecord]:
        """Records whose open or close falls inside the session window."""
        try:
            t0 = datetime.fromisoformat(started)
            t1 = datetime.fromisoformat(ended)
        except (TypeError, ValueError):
            return list(records)
        out: List[TradeRecord] = []
        for r in records:
            stamps = [t for t in (r.opened_at_utc, r.closed_at_utc,
                                  r.created_at_utc) if t is not None]
            if any(t0 <= t <= t1 for t in stamps):
                out.append(r)
        return out

    @staticmethod
    def _performance(
        closed: Sequence[TradeRecord], open_positions: int
    ) -> PerformanceMetrics:
        wins = sum(1 for r in closed if r.outcome is TradeOutcome.WIN)
        losses = sum(1 for r in closed if r.outcome is TradeOutcome.LOSS)
        breakeven = sum(1 for r in closed if r.outcome is TradeOutcome.BREAKEVEN)
        decided = wins + losses
        pnls = [
            r.pnl for r in sorted(
                closed,
                key=lambda r: r.closed_at_utc or r.created_at_utc,
            )
            if r.pnl is not None
        ]
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for pnl in pnls:
            equity += pnl
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
        return PerformanceMetrics(
            trades_closed=len(closed),
            wins=wins,
            losses=losses,
            breakeven=breakeven,
            win_rate=(wins / decided) if decided else 0.0,
            pnl_total=sum(pnls),
            max_drawdown=max_dd,
            open_positions=open_positions,
        )

    @staticmethod
    def _buckets(values: Sequence[float]) -> Dict[str, int]:
        buckets = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0,
                   "0.6-0.8": 0, "0.8-1.0": 0}
        for v in values:
            v = max(0.0, min(1.0, v))
            idx = min(int(v / 0.2), 4)
            key = list(buckets)[idx]
            buckets[key] += 1
        return buckets

    @staticmethod
    def _spread_stats(spreads: Sequence[float]) -> Dict[str, float]:
        if not spreads:
            return {"min": 0.0, "mean": 0.0, "max": 0.0, "samples": 0}
        return {
            "min": round(min(spreads), 6),
            "mean": round(sum(spreads) / len(spreads), 6),
            "max": round(max(spreads), 6),
            "samples": len(spreads),
        }

    @staticmethod
    def _market_untradeable(stats: List[dict], actionable: int) -> bool:
        """True when no setup formed AND untradeable regimes dominated."""
        if actionable > 0:
            return False
        regimes = [s.get("regime") for s in stats if s.get("regime")]
        if not regimes:
            return False
        bad = sum(1 for r in regimes if r in _UNTRADEABLE_REGIMES)
        return bad / len(regimes) >= 0.5


# -- reflection ----------------------------------------------------------------

def build_reflection(ev: SessionEvaluation) -> ReflectionReport:
    """Derive the reflection sections from a SessionEvaluation (offline)."""
    did_well: List[str] = []
    too_strict: List[str] = []
    too_loose: List[str] = []
    missed: List[str] = []
    avoided: List[str] = []
    backtest: List[str] = []
    fix_now: List[str] = []

    if ev.violations == 0:
        did_well.append("zero safety violations across the session")
    if ev.decisions_total >= ev.cycles and ev.cycles > 0:
        did_well.append(
            f"every cycle journaled a decision ({ev.decisions_total} "
            f"decisions over {ev.cycles} cycles)"
        )
    if ev.stop_updates > 0:
        did_well.append(
            f"{ev.stop_updates} protective stop update(s) applied via the "
            "gateway (never widened)"
        )
    if ev.performance.wins > 0:
        did_well.append(
            f"{ev.performance.wins} winning trade(s), realized P&L "
            f"{ev.performance.pnl_total:.2f}"
        )

    if ev.news_risky_cycles > 0:
        avoided.append(
            f"{ev.news_risky_cycles} cycle(s) under news risk were blocked "
            "from entries"
        )
    if ev.market_untradeable:
        avoided.append(
            "untradeable regimes dominated and the model stayed flat — "
            "correct patience, not over-filtering"
        )
    if ev.risk_blocked_cycles > 0:
        avoided.append(
            f"the Risk Governor blocked {ev.risk_blocked_cycles} cycle(s); "
            "risk policy remained final authority"
        )

    for f in ev.findings:
        line = f"{f.title}: {f.detail}"
        if f.classification in (FindingClass.PROVEN_DEFECT,
                                FindingClass.HIGH_CONFIDENCE_DEFECT):
            if f.action == "fix immediately":
                fix_now.append(line)
            else:
                backtest.append(line)
        elif f.classification in (FindingClass.HYPOTHESIS,
                                  FindingClass.DESIGN_IMPROVEMENT):
            backtest.append(line)
        if f.title == "one gate dominates entry blocks":
            too_strict.append(line)
        if f.title == "high-confidence entries were blocked":
            missed.append(line)
        if f.title == "session order cap blocked approved entries":
            too_strict.append(line)
        if f.title in ("losses on high-confidence trades",
                       "low realized win rate"):
            too_loose.append(line)

    if not too_strict and ev.actionable_decisions == 0 and not ev.market_untradeable:
        too_strict.append(
            "no actionable setup formed although regimes were not hostile; "
            "review whether setup detection (sweep-reclaim only) is too "
            "narrow — backtest before changing"
        )

    summary = (
        f"mode={ev.mode or 'n/a'} profile={ev.profile or 'n/a'} "
        f"cycles={ev.cycles} decisions={ev.decisions_total} "
        f"real_trades={ev.trades_real} simulated={ev.trades_simulated} "
        f"closed={ev.performance.trades_closed} "
        f"pnl={ev.performance.pnl_total:.2f} "
        f"max_dd={ev.performance.max_drawdown:.2f} "
        f"verdict={ev.verdict or 'n/a'}"
    )
    return ReflectionReport(
        did_well=tuple(did_well),
        too_strict=tuple(too_strict),
        too_loose=tuple(too_loose),
        missed_opportunities=tuple(missed),
        avoided_correctly=tuple(avoided),
        backtest_before_change=tuple(backtest),
        fix_immediately=tuple(fix_now),
        summary=summary,
    )


# -- markdown rendering ----------------------------------------------------------

def _dist_lines(title: str, dist: Dict[str, int]) -> List[str]:
    lines = [f"### {title}", ""]
    if not dist:
        lines.append("- (none)")
    for key, count in sorted(dist.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- {key}: {count}")
    lines.append("")
    return lines


def render_evaluation_markdown(ev: SessionEvaluation) -> str:
    lines: List[str] = ["# Demo Session Evaluation (DEMO-EVAL)", ""]
    lines += [
        f"- Symbol: {ev.symbol}",
        f"- Mode: **{ev.mode or 'n/a'}** (real demo orders vs dry-run are "
        "never mixed)",
        f"- Profile: {ev.profile or 'n/a'}",
        f"- Verdict: **{ev.verdict or 'n/a'}**",
        f"- Window: {ev.started_at_utc} .. {ev.ended_at_utc}",
        "",
        "## Totals",
        "",
        f"- cycles: {ev.cycles}",
        f"- decisions: {ev.decisions_total}",
        f"- actionable decisions: {ev.actionable_decisions}",
        f"- approved decisions: {ev.approved_decisions}",
        f"- REAL MT5 demo orders sent: {ev.trades_real}",
        f"- dry-run simulated orders: {ev.trades_simulated}",
        f"- broker-rejected orders: {ev.trades_rejected}",
        f"- entries blocked: {ev.entries_blocked}",
        f"- protective stop updates: {ev.stop_updates}",
        f"- violations: {ev.violations}",
        f"- news-risky cycles: {ev.news_risky_cycles}",
        f"- news-unknown cycles: {ev.news_unknown_cycles}",
        f"- risk-governor-blocked cycles: {ev.risk_blocked_cycles}",
        f"- market genuinely untradeable: {ev.market_untradeable}",
        "",
        "## Performance (closed real demo trades)",
        "",
    ]
    p = ev.performance
    lines += [
        f"- closed trades: {p.trades_closed} "
        f"(W{p.wins}/L{p.losses}/BE{p.breakeven})",
        f"- win rate: {p.win_rate:.0%}",
        f"- realized P&L: {p.pnl_total:.2f}",
        f"- max drawdown (realized curve): {p.max_drawdown:.2f}",
        f"- still open: {p.open_positions}",
        "",
        "## Distributions",
        "",
    ]
    lines += _dist_lines("Regimes", ev.regime_distribution)
    lines += _dist_lines("Sessions", ev.session_distribution)
    lines += _dist_lines("HTF bias", ev.htf_bias_distribution)
    lines += _dist_lines("Confidence", ev.confidence_buckets)
    lines += _dist_lines("Entry actions", ev.entry_actions)
    lines += _dist_lines("No-trade reasons", ev.no_trade_reasons)
    s = ev.spread_stats
    lines += [
        "### Spread (price units)",
        "",
        f"- min {s.get('min')} / mean {s.get('mean')} / max {s.get('max')} "
        f"over {s.get('samples')} samples",
        "",
        "## Mistakes (reflection engine)",
        "",
    ]
    if ev.mistakes:
        lines += [f"- {k}: {v}" for k, v in sorted(ev.mistakes.items())]
    else:
        lines.append("- none detected")
    lines += ["", "## Findings (classified)", ""]
    for f in ev.findings:
        lines.append(
            f"- **{f.classification.value}** — {f.title}: {f.detail} "
            f"_[{f.action}]_"
        )
    if not ev.findings:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def render_reflection_markdown(rr: ReflectionReport) -> str:
    def section(title: str, items: Tuple[str, ...]) -> List[str]:
        out = [f"## {title}", ""]
        out += [f"- {i}" for i in items] if items else ["- (nothing to report)"]
        out.append("")
        return out

    lines: List[str] = ["# Demo Session Reflection (DEMO-EVAL)", "",
                        f"Summary: {rr.summary}", ""]
    lines += section("What the model did well", rr.did_well)
    lines += section("Where it was too strict", rr.too_strict)
    lines += section("Where it was too loose", rr.too_loose)
    lines += section("Possibly missed opportunities (unproven)",
                     rr.missed_opportunities)
    lines += section("Bad conditions avoided correctly", rr.avoided_correctly)
    lines += section("Must be backtested before changing",
                     rr.backtest_before_change)
    lines += section("Can be fixed immediately", rr.fix_immediately)
    lines += [
        "---",
        "",
        "No live self-mutation: this report proposes evidence-based changes "
        "only; applying any of them requires the normal task/test/commit "
        "workflow (04_ADAPTATION_POLICY.md).",
        "",
    ]
    return "\n".join(lines)
