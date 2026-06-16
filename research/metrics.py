"""Result accounting and edge classification for the research lab.

Everything here is in R-multiples (risk-normalized), so position sizing cancels
out — we measure DECISION QUALITY, not the sizing engine. Classification
thresholds are explicit, versioned constants: an edge is judged by the same
rules every time, never tuned after seeing a result.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Sequence

from src.data.enums import Direction, TradeOutcome

# --- classification thresholds (v1, frozen) --------------------------------
# Recorded here so the bar to "Proven Edge Candidate" is fixed in advance.
CLASSIFIER_VERSION = "v1"
MIN_OCCURRENCES = 100          # below this => Insufficient Data, full stop
PROVEN_MIN_EXPECTANCY = 0.10   # >= +0.10R/trade average
PROVEN_MIN_PROFIT_FACTOR = 1.30
PROVEN_MAX_COST_DECAY = 0.50   # expectancy must keep >=50% under the cost stress grid
WEAK_MIN_EXPECTANCY = 0.0      # > 0 but failing a "proven" gate => Weak Edge


class Classification(str, Enum):
    PROVEN_EDGE_CANDIDATE = "Proven Edge Candidate"
    WEAK_EDGE = "Weak Edge"
    NO_EDGE = "No Edge"
    INSUFFICIENT_DATA = "Insufficient Data"


class ExitReason(str, Enum):
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    INVALIDATION = "INVALIDATION"   # structural invalidation before/around fill
    TIMEOUT = "TIMEOUT"             # entry/exit window expired
    END_OF_DATA = "END_OF_DATA"     # ran out of candles while in a trade


@dataclass
class TradeResult:
    """One realized (or cancelled) occurrence of a setup, scored in R."""

    setup: str
    version: str
    day: datetime
    direction: Direction
    session: str
    entry_time: Optional[datetime]
    entry_price: Optional[float]
    stop: float
    target: float
    exit_time: Optional[datetime]
    exit_price: Optional[float]
    r_multiple: float
    outcome: TradeOutcome
    exit_reason: ExitReason
    mfe_r: float = 0.0   # max favorable excursion in R while open
    mae_r: float = 0.0   # max adverse excursion in R while open
    note: str = ""       # human-readable "why" for win/loss review
    context: Dict[str, float] = field(default_factory=dict)

    @property
    def filled(self) -> bool:
        return self.entry_price is not None and self.exit_reason not in (
            ExitReason.INVALIDATION,
            ExitReason.TIMEOUT,
        )


@dataclass
class Metrics:
    occurrences: int            # total signals (including cancelled-before-fill)
    trades: int                 # filled trades only
    wins: int
    losses: int
    breakevens: int
    cancellations: int
    win_rate: float             # over filled trades
    avg_r: float
    median_r: float
    expectancy: float           # == avg_r over filled trades
    profit_factor: float
    total_r: float
    max_drawdown_r: float
    max_consecutive_losses: int
    best_r: float
    worst_r: float

    def as_row(self) -> Dict[str, str]:
        return {
            "occurrences": str(self.occurrences),
            "trades": str(self.trades),
            "win_rate": f"{self.win_rate * 100:.1f}%",
            "avg_R": f"{self.avg_r:+.3f}",
            "median_R": f"{self.median_r:+.3f}",
            "expectancy_R": f"{self.expectancy:+.3f}",
            "profit_factor": f"{self.profit_factor:.2f}",
            "total_R": f"{self.total_r:+.1f}",
            "max_DD_R": f"{self.max_drawdown_r:.1f}",
            "max_consec_losses": str(self.max_consecutive_losses),
        }


def _max_drawdown_r(r_series: Sequence[float]) -> float:
    """Peak-to-trough drawdown of the cumulative-R equity curve (positive number)."""
    peak = 0.0
    cum = 0.0
    max_dd = 0.0
    for r in r_series:
        cum += r
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return max_dd


def _max_consecutive_losses(outcomes: Sequence[TradeOutcome]) -> int:
    run = best = 0
    for o in outcomes:
        if o == TradeOutcome.LOSS:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def compute_metrics(results: Sequence[TradeResult]) -> Metrics:
    """Aggregate per-trade results into the metric block the lab reports."""
    occurrences = len(results)
    filled = [r for r in results if r.filled]
    cancellations = occurrences - len(filled)

    r_series = [r.r_multiple for r in filled]
    outcomes = [r.outcome for r in filled]
    wins = sum(1 for o in outcomes if o == TradeOutcome.WIN)
    losses = sum(1 for o in outcomes if o == TradeOutcome.LOSS)
    breakevens = sum(1 for o in outcomes if o == TradeOutcome.BREAKEVEN)

    n = len(filled)
    gross_profit = sum(r for r in r_series if r > 0)
    gross_loss = -sum(r for r in r_series if r < 0)
    profit_factor = (
        gross_profit / gross_loss if gross_loss > 0
        else (float("inf") if gross_profit > 0 else 0.0)
    )

    return Metrics(
        occurrences=occurrences,
        trades=n,
        wins=wins,
        losses=losses,
        breakevens=breakevens,
        cancellations=cancellations,
        win_rate=(wins / n) if n else 0.0,
        avg_r=(sum(r_series) / n) if n else 0.0,
        median_r=statistics.median(r_series) if r_series else 0.0,
        expectancy=(sum(r_series) / n) if n else 0.0,
        profit_factor=profit_factor,
        total_r=sum(r_series),
        max_drawdown_r=_max_drawdown_r(r_series),
        max_consecutive_losses=_max_consecutive_losses(outcomes),
        best_r=max(r_series) if r_series else 0.0,
        worst_r=min(r_series) if r_series else 0.0,
    )


def classify(base: Metrics, cost_stress_expectancy: Optional[Sequence[float]] = None) -> Classification:
    """Classify an edge from base metrics + (optional) cost-stress expectancies.

    Decision order (fixed):
      1. fewer than MIN_OCCURRENCES filled trades -> Insufficient Data.
      2. expectancy <= 0 or profit factor < 1     -> No Edge.
      3. meets all "proven" gates (expectancy, profit factor, and holds up under
         the cost-stress grid) -> Proven Edge Candidate.
      4. otherwise positive but fragile -> Weak Edge.
    """
    if base.trades < MIN_OCCURRENCES:
        return Classification.INSUFFICIENT_DATA
    if base.expectancy <= 0 or base.profit_factor < 1.0:
        return Classification.NO_EDGE

    holds_under_cost = True
    if cost_stress_expectancy:
        worst = min(cost_stress_expectancy)
        # Must stay positive AND retain enough of the base edge under stress.
        holds_under_cost = (
            worst > 0 and worst >= PROVEN_MAX_COST_DECAY * base.expectancy
        )

    proven = (
        base.expectancy >= PROVEN_MIN_EXPECTANCY
        and base.profit_factor >= PROVEN_MIN_PROFIT_FACTOR
        and holds_under_cost
    )
    if proven:
        return Classification.PROVEN_EDGE_CANDIDATE
    return Classification.WEAK_EDGE
