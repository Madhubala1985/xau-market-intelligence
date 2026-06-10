"""Threshold calibration replay (BACKTEST-001 readiness; INTELLIGENCE-002).

The graded gates introduced by INTELLIGENCE-001/002 use reasoned default
thresholds (chop-override confluence 0.65, continuation confluence 0.60,
continuation displacement 1.5x). This module measures how threshold VARIANTS
would have behaved on historical XAUUSDm candles, so threshold changes can be
made from evidence instead of taste.

Method (honest, bounded):
- slide a decision window across the historical M5 series; each step builds a
  PipelineInput exactly like the live loop (D1/H4 aggregated from the same
  series, clearly a backtest approximation) and runs the REAL DecisionPipeline
  configured with the variant's thresholds;
- decisions use ONLY the window (the pipeline is causal); the FUTURE horizon
  is used solely to score the outcome afterwards (stop hit vs target hit,
  first touch wins; both untouched => timeout, scored by the final move);
- outcomes are expressed in R (risk units). Expectancy(R) per variant is the
  comparison metric; near-misses (confluence >= 0.55, no entry) measure how
  much each variant leaves on the table.

HARD RULE: this module RECOMMENDS; it never mutates live configuration,
policies, or thresholds (04_ADAPTATION_POLICY.md). Applying a recommendation
is a normal reviewed task.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from src.data.aggregation import AggregationError, aggregate
from src.data.enums import BrokerConnectionStatus, Direction, Timeframe
from src.data.schemas import BrokerState, Candle
from src.strategy.pipeline import DecisionPipeline, PipelineInput

_NEAR_MISS = 0.55


@dataclass(frozen=True)
class ThresholdVariant:
    """One threshold combination to evaluate."""

    name: str
    chop_override_confluence: float = 0.65
    continuation_confluence: float = 0.60
    continuation_displacement: float = 1.5

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "chop_override_confluence": self.chop_override_confluence,
            "continuation_confluence": self.continuation_confluence,
            "continuation_displacement": self.continuation_displacement,
        }


DEFAULT_VARIANTS: Tuple[ThresholdVariant, ...] = (
    ThresholdVariant("current(0.65/0.60/1.5)"),
    ThresholdVariant("looser(0.55/0.50/1.3)", 0.55, 0.50, 1.3),
    ThresholdVariant("tighter(0.75/0.70/1.8)", 0.75, 0.70, 1.8),
)


@dataclass(frozen=True)
class VariantResult:
    variant: ThresholdVariant
    windows: int
    actionable: int
    approved: int
    wins: int
    losses: int
    timeouts: int
    expectancy_r: float
    win_rate: float
    near_misses: int

    def to_dict(self) -> dict:
        return {
            "variant": self.variant.to_dict(),
            "windows": self.windows,
            "actionable": self.actionable,
            "approved": self.approved,
            "wins": self.wins,
            "losses": self.losses,
            "timeouts": self.timeouts,
            "expectancy_r": round(self.expectancy_r, 4),
            "win_rate": round(self.win_rate, 4),
            "near_misses": self.near_misses,
        }


@dataclass(frozen=True)
class CalibrationReport:
    results: Tuple[VariantResult, ...]
    recommended: Optional[str]
    detail: str

    def to_dict(self) -> dict:
        return {
            "task": "BACKTEST-001-READINESS",
            "results": [r.to_dict() for r in self.results],
            "recommended": self.recommended,
            "detail": self.detail,
            "note": (
                "recommendation only — live thresholds are never mutated by "
                "this tool"
            ),
        }


class ThresholdCalibrator:
    """Replays threshold variants over a historical candle series."""

    def __init__(
        self,
        *,
        window: int = 200,
        step: int = 12,
        horizon: int = 36,
        min_trades: int = 5,
        balance: float = 10_000.0,
        spread: float = 0.25,
        risk_cap: float = 0.01,
    ) -> None:
        self._window = window
        self._step = step
        self._horizon = horizon
        self._min_trades = min_trades
        self._balance = balance
        self._spread = spread
        self._risk_cap = risk_cap

    def run(
        self,
        candles: Sequence[Candle],
        variants: Sequence[ThresholdVariant] = DEFAULT_VARIANTS,
    ) -> CalibrationReport:
        candles = list(candles)
        if len(candles) < self._window + self._horizon + self._step:
            return CalibrationReport(
                results=(), recommended=None,
                detail=(
                    f"insufficient history: {len(candles)} candles < "
                    f"{self._window + self._horizon + self._step} required"
                ),
            )
        daily, h4 = self._htf_frames(candles)
        results = tuple(
            self._run_variant(v, candles, daily, h4) for v in variants
        )
        recommended, detail = self._recommend(results)
        return CalibrationReport(results=results, recommended=recommended,
                                 detail=detail)

    # -- internals -------------------------------------------------------------
    def _run_variant(
        self, variant: ThresholdVariant, candles: List[Candle],
        daily: List[Candle], h4: List[Candle],
    ) -> VariantResult:
        pipeline = DecisionPipeline(
            max_spread=1.0,
            chop_override_confluence=variant.chop_override_confluence,
            continuation_confluence=variant.continuation_confluence,
            continuation_displacement=variant.continuation_displacement,
        )
        broker = BrokerState(
            time_utc=candles[0].time_utc,
            connection_status=BrokerConnectionStatus.CONNECTED,
            symbol="XAUUSD", balance=self._balance, equity=self._balance,
            open_positions=0, trade_allowed=True, leverage=200,
        )
        windows = actionable = approved = wins = losses = timeouts = 0
        near = 0
        r_sum = 0.0
        for i in range(self._window, len(candles) - self._horizon, self._step):
            past = candles[i - self._window:i]
            windows += 1
            result = pipeline.decide(PipelineInput(
                symbol="XAUUSD", exec_candles=past,
                daily_candles=self._cut(daily, past[-1]),
                h4_candles=self._cut(h4, past[-1]),
                broker=broker, current_spread=self._spread,
                risk_pct=self._risk_cap, now=past[-1].time_utc,
            ))
            decision = result.decision
            is_actionable = decision is not None and decision.direction in (
                Direction.LONG, Direction.SHORT
            )
            if is_actionable:
                actionable += 1
            conf = result.context.confluence if result.context else None
            if not (is_actionable and result.approved):
                if conf is not None and conf.score >= _NEAR_MISS:
                    near += 1
                continue
            approved += 1
            outcome_r = self._score(decision, candles[i:i + self._horizon])
            r_sum += outcome_r
            if outcome_r > 0.05:
                wins += 1
            elif outcome_r < -0.05:
                losses += 1
            else:
                timeouts += 1
        decided = wins + losses
        return VariantResult(
            variant=variant, windows=windows, actionable=actionable,
            approved=approved, wins=wins, losses=losses, timeouts=timeouts,
            expectancy_r=(r_sum / approved) if approved else 0.0,
            win_rate=(wins / decided) if decided else 0.0,
            near_misses=near,
        )

    def _score(self, decision, future: Sequence[Candle]) -> float:
        """Outcome in R units: first touch of stop (-1) or target (+R)."""
        entry = decision.entry_price
        stop = decision.stop_loss
        target = decision.take_profits[0] if decision.take_profits else None
        risk = abs(entry - stop)
        if risk <= 0:
            return 0.0
        is_long = decision.direction is Direction.LONG
        reward_r = (abs(target - entry) / risk) if target is not None else 2.0
        for c in future:
            stop_hit = c.low <= stop if is_long else c.high >= stop
            target_hit = (
                target is not None
                and (c.high >= target if is_long else c.low <= target)
            )
            if stop_hit and target_hit:
                return -1.0  # ambiguous candle: scored conservatively
            if stop_hit:
                return -1.0
            if target_hit:
                return reward_r
        final = future[-1].close if future else entry
        return ((final - entry) if is_long else (entry - final)) / risk

    @staticmethod
    def _htf_frames(candles: Sequence[Candle]) -> tuple[list, list]:
        """D1/H4 from the same series — a labelled backtest approximation."""
        try:
            daily = aggregate(candles, Timeframe.D1)
        except (AggregationError, ValueError):
            daily = []
        try:
            h4 = aggregate(candles, Timeframe.H4)
        except (AggregationError, ValueError):
            h4 = []
        return daily, h4

    @staticmethod
    def _cut(frames: List[Candle], last: Candle) -> List[Candle]:
        """Only HTF bars that completed BEFORE the decision moment."""
        return [c for c in frames if c.time_utc <= last.time_utc]

    def _recommend(
        self, results: Tuple[VariantResult, ...]
    ) -> tuple[Optional[str], str]:
        qualified = [r for r in results if r.approved >= self._min_trades]
        if not qualified:
            return None, (
                f"no variant produced >= {self._min_trades} trades; collect "
                "more history before drawing conclusions"
            )
        best = max(qualified, key=lambda r: r.expectancy_r)
        return best.variant.name, (
            f"best expectancy {best.expectancy_r:.2f}R over "
            f"{best.approved} trade(s) (win rate {best.win_rate:.0%}); "
            "apply only via a reviewed task with walk-forward validation"
        )
