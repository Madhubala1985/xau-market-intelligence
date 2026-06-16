"""Render a ResearchResult to the evidence report the lab is required to emit.

The report is the deliverable: setup rules, the result table, win/loss examples
with the "why", spread/slippage sensitivity, session sensitivity, and the final
classification. It states sample size honestly and never claims success from a
handful of examples.
"""

from __future__ import annotations

from typing import List, Sequence

from research.harness import ResearchResult
from research.metrics import Classification, ExitReason, TradeResult
from src.data.enums import TradeOutcome


def _examples(results: Sequence[TradeResult], outcome: TradeOutcome, n: int) -> List[TradeResult]:
    pool = [r for r in results if r.outcome == outcome and r.filled]
    # Most extreme first so reviewers see the clearest cases.
    pool.sort(key=lambda r: r.r_multiple, reverse=(outcome == TradeOutcome.WIN))
    return pool[:n]


def _fmt_example(r: TradeResult) -> str:
    when = r.entry_time.isoformat() if r.entry_time else "n/a"
    px = f"{r.entry_price:.2f}" if r.entry_price is not None else "n/a"
    return (
        f"- **{r.day.date().isoformat()}** {r.direction.value} entry@{px} "
        f"({when}) → {r.r_multiple:+.2f}R [{r.exit_reason.value}] "
        f"MFE {r.mfe_r:+.2f}R / MAE {r.mae_r:+.2f}R — {r.note}"
    )


def _cancellation_reasons(results: Sequence[TradeResult]) -> str:
    inval = sum(1 for r in results if r.exit_reason == ExitReason.INVALIDATION)
    timeout = sum(1 for r in results if r.exit_reason == ExitReason.TIMEOUT)
    return f"invalidated={inval}, expired_unfilled={timeout}"


def _rank_key(r: ResearchResult) -> tuple:
    """Sort setups best-first: classification tier, then expectancy, then PF."""
    tier = {
        Classification.PROVEN_EDGE_CANDIDATE: 3,
        Classification.WEAK_EDGE: 2,
        Classification.NO_EDGE: 1,
        Classification.INSUFFICIENT_DATA: 0,
    }[r.classification]
    return (tier, r.metrics.expectancy, r.metrics.profit_factor)


def render_ranking(results: List[ResearchResult]) -> str:
    """Render the cross-setup quality ranking (the lab's top-level scoreboard)."""
    ordered = sorted(results, key=_rank_key, reverse=True)
    lines: List[str] = []
    a = lines.append
    a("# Setup Quality Ranking")
    a("")
    a("Best-first by classification tier, then expectancy, then profit factor. "
      "No automation is justified unless a setup reaches **Proven Edge Candidate**.")
    a("")
    a("| rank | setup | version | class | trades | win rate | expectancy R | PF | max DD R |")
    a("|---|---|---|---|---|---|---|---|---|")
    for n, r in enumerate(ordered, 1):
        m = r.metrics
        a(f"| {n} | {r.setup} | {r.version} | {r.classification.value} | "
          f"{m.trades} | {m.win_rate * 100:.1f}% | {m.expectancy:+.3f} | "
          f"{m.profit_factor:.2f} | {m.max_drawdown_r:.1f} |")
    a("")
    proven = [r for r in ordered if r.classification == Classification.PROVEN_EDGE_CANDIDATE]
    if proven:
        a(f"**Best setup:** `{proven[0].setup}` — Proven Edge Candidate. "
          "An execution-model proposal may follow (gated on out-of-sample confirmation).")
    else:
        a("**Best setup:** none qualifies as a Proven Edge Candidate. "
          "Automation stays forbidden; gather more data or refine rules as new versions.")
    a("")
    return "\n".join(lines)


def render(result: ResearchResult, n_examples: int = 5) -> str:
    m = result.metrics
    lines: List[str] = []
    a = lines.append

    a(f"# Research Result — {result.setup} ({result.version})")
    a("")
    a(f"- **Classification:** **{result.classification.value}**")
    a(f"- **Data span:** {result.data_span or 'NO DATA LOADED'}")
    a(f"- **Base costs:** spread {result.base_cost.spread:.2f} + "
      f"slippage {result.base_cost.slippage:.2f} (USD, adverse)")
    a("")

    a("## Exact mechanical rules")
    a("")
    for k, v in result.rules.items():
        a(f"- **{k}:** {v}")
    a("")

    a("## Result table (base costs)")
    a("")
    row = m.as_row()
    a("| metric | value |")
    a("|---|---|")
    for k, v in row.items():
        a(f"| {k} | {v} |")
    a(f"| wins / losses / breakeven | {m.wins} / {m.losses} / {m.breakevens} |")
    a(f"| cancelled before fill | {m.cancellations} ({_cancellation_reasons(result.results)}) |")
    a(f"| best / worst R | {m.best_r:+.2f} / {m.worst_r:+.2f} |")
    a("")

    if m.trades < 100:
        a(f"> ⚠️ **Only {m.trades} filled trades** (< 100). Per lab policy this is "
          f"**Insufficient Data**: no edge claim is valid from this sample. "
          f"Load more history and re-run.")
        a("")

    a("## Spread / slippage sensitivity")
    a("")
    a("| cost profile | spread | slippage | trades | win rate | expectancy R | total R |")
    a("|---|---|---|---|---|---|---|")
    for s in result.sensitivity:
        a(f"| {s.cost.label} | {s.cost.spread:.2f} | {s.cost.slippage:.2f} | "
          f"{s.trades} | {s.win_rate * 100:.1f}% | {s.expectancy:+.3f} | {s.total_r:+.1f} |")
    a("")

    a("## Session sensitivity")
    a("")
    a("| session | trades | win rate | expectancy R | total R |")
    a("|---|---|---|---|---|")
    for sess, sm in sorted(result.by_session.items()):
        a(f"| {sess} | {sm.trades} | {sm.win_rate * 100:.1f}% | "
          f"{sm.expectancy:+.3f} | {sm.total_r:+.1f} |")
    a("")

    wins = _examples(result.results, TradeOutcome.WIN, n_examples)
    losses = _examples(result.results, TradeOutcome.LOSS, n_examples)

    a("## Winning examples")
    a("")
    a("\n".join(_fmt_example(r) for r in wins) if wins else "- (none)")
    a("")
    a("## Losing examples (why they lost)")
    a("")
    a("\n".join(_fmt_example(r) for r in losses) if losses else "- (none)")
    a("")

    a("## Automation verdict")
    a("")
    if result.classification == Classification.PROVEN_EDGE_CANDIDATE:
        a("- Automation **may be proposed** for this setup. Next step: a separate "
          "execution-model proposal gated on out-of-sample / walk-forward confirmation.")
    else:
        a(f"- Automation is **NOT justified** ({result.classification.value}). "
          "Execution stays retired. Refine rules as a NEW version or gather more data.")
    a("")
    return "\n".join(lines)
