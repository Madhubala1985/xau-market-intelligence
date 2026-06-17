"""Causal backtest/replay harness for the research lab.

Given a setup's EntryIntents and the M5 exec series, the harness simulates each
intent strictly FORWARD in time under conservative (adverse) cost assumptions,
then aggregates results, runs a spread/slippage stress grid, breaks results down
by session, and classifies the edge.

Fill model (conservative, fixed for every setup):
- An intent armed at bar `arm_index` may only fill at bar `arm_index + 1` or
  later (no same-bar look-ahead).
- LONG fills when a later bar's LOW trades down to entry_price; entry pays
  +(spread + slippage) adverse. SHORT mirrors (HIGH up to entry, pays it down).
- Invalidation is checked before fill; if the invalidation price is touched
  first, the intent is cancelled (no trade).
- After fill, stop/target are checked bar-by-bar. If ONE bar touches both, the
  STOP is assumed first (worst case). Exits pay slippage adverse.
- If neither is hit before the series ends, the trade exits at the last close
  (END_OF_DATA) so nothing is silently dropped.
- R is risk-normalized: realized_pnl / |entry - stop|. Costs therefore shrink R.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Sequence

from research.metrics import (
    Classification,
    ExitReason,
    Metrics,
    TradeResult,
    classify,
    compute_metrics,
)
from research.setups.base import EntryIntent, MarketData, Setup
from src.data.enums import Direction, Timeframe, TradeOutcome
from src.data.schemas import Candle


@dataclass(frozen=True)
class CostModel:
    """Adverse costs in price units (USD for XAU/USD)."""

    spread: float = 0.20
    slippage: float = 0.30
    label: str = "base"


# Stress grid applied to every setup. Fixed in advance (no per-result tuning).
DEFAULT_COST_GRID: tuple[CostModel, ...] = (
    CostModel(0.10, 0.10, "tight"),
    CostModel(0.20, 0.30, "base"),
    CostModel(0.40, 0.50, "wide"),
    CostModel(0.70, 0.80, "stress"),
)


@dataclass
class SensitivityRow:
    cost: CostModel
    expectancy: float
    win_rate: float
    total_r: float
    trades: int


@dataclass
class ResearchResult:
    setup: str
    version: str
    rules: Dict[str, object]
    base_cost: CostModel
    metrics: Metrics
    classification: Classification
    results: List[TradeResult]
    sensitivity: List[SensitivityRow] = field(default_factory=list)
    by_session: Dict[str, Metrics] = field(default_factory=dict)
    data_span: str = ""


def _simulate_intent(
    intent: EntryIntent,
    candles: Sequence[Candle],
    cost: CostModel,
) -> TradeResult:
    """Simulate one EntryIntent forward in time; return a scored TradeResult."""
    is_long = intent.direction == Direction.LONG
    risk = intent.risk

    def _result(
        entry_price: Optional[float],
        entry_time: Optional[datetime],
        exit_price: Optional[float],
        exit_time: Optional[datetime],
        r: float,
        outcome: TradeOutcome,
        reason: ExitReason,
        mfe_r: float = 0.0,
        mae_r: float = 0.0,
        note: str = "",
    ) -> TradeResult:
        return TradeResult(
            setup=intent.setup, version=intent.version, day=intent.day,
            direction=intent.direction, session=intent.session,
            entry_time=entry_time, entry_price=entry_price,
            stop=intent.stop, target=intent.target,
            exit_time=exit_time, exit_price=exit_price,
            r_multiple=r, outcome=outcome, exit_reason=reason,
            mfe_r=mfe_r, mae_r=mae_r, note=note or intent.note,
            context=dict(intent.context),
        )

    # --- 1) wait for fill (forward only) ---
    fill_price: Optional[float] = None
    fill_time: Optional[datetime] = None
    fill_idx: Optional[int] = None

    # MARKET entries (breakout/momentum) fill at the next bar's open, adverse cost.
    if intent.entry_type == "MARKET":
        j = intent.arm_index + 1
        if j >= len(candles):
            return _result(None, None, None, None, 0.0,
                           TradeOutcome.NO_TRADE, ExitReason.TIMEOUT,
                           note="no next bar to fill market entry")
        nxt = candles[j]
        fill_price = nxt.open + (cost.spread + cost.slippage) if is_long \
            else nxt.open - (cost.spread + cost.slippage)
        fill_time, fill_idx = nxt.time_utc, j

    last_idx = min(intent.expiry_index, len(candles) - 1)
    for i in range(intent.arm_index + 1, last_idx + 1):
        if fill_idx is not None:
            break
        c = candles[i]
        # Invalidation before fill: sweep failed (new extreme beyond invalidation).
        if is_long and c.low <= intent.invalidation_price:
            return _result(None, None, None, None, 0.0,
                           TradeOutcome.NO_TRADE, ExitReason.INVALIDATION,
                           note="invalidated: new low <= sweep low before fill")
        if (not is_long) and c.high >= intent.invalidation_price:
            return _result(None, None, None, None, 0.0,
                           TradeOutcome.NO_TRADE, ExitReason.INVALIDATION,
                           note="invalidated: new high >= sweep high before fill")
        # Limit fill: price trades into the level (mitigation). Adverse cost.
        if is_long and c.low <= intent.entry_price:
            fill_price = intent.entry_price + cost.spread + cost.slippage
            fill_time, fill_idx = c.time_utc, i
            break
        if (not is_long) and c.high >= intent.entry_price:
            fill_price = intent.entry_price - cost.spread - cost.slippage
            fill_time, fill_idx = c.time_utc, i
            break

    if fill_idx is None:
        return _result(None, None, None, None, 0.0,
                       TradeOutcome.NO_TRADE, ExitReason.TIMEOUT,
                       note="no mitigation within window")

    # --- 2) manage to stop / target (forward only, stop-first on ties) ---
    mfe = mae = 0.0
    for i in range(fill_idx, len(candles)):
        c = candles[i]
        if is_long:
            mfe = max(mfe, (c.high - fill_price) / risk)
            mae = min(mae, (c.low - fill_price) / risk)
            hit_stop = c.low <= intent.stop
            hit_tp = c.high >= intent.target
        else:
            mfe = max(mfe, (fill_price - c.low) / risk)
            mae = min(mae, (fill_price - c.high) / risk)
            hit_stop = c.high >= intent.stop
            hit_tp = c.low <= intent.target
        if hit_stop:  # stop checked first (conservative)
            exit_price = intent.stop - cost.slippage if is_long else intent.stop + cost.slippage
            r = ((exit_price - fill_price) if is_long else (fill_price - exit_price)) / risk
            return _result(fill_price, fill_time, exit_price, c.time_utc, r,
                           TradeOutcome.LOSS, ExitReason.STOP_LOSS, mfe, mae,
                           note="stopped at swept low")
        if hit_tp:
            exit_price = intent.target - cost.slippage if is_long else intent.target + cost.slippage
            r = ((exit_price - fill_price) if is_long else (fill_price - exit_price)) / risk
            return _result(fill_price, fill_time, exit_price, c.time_utc, r,
                           TradeOutcome.WIN, ExitReason.TAKE_PROFIT, mfe, mae,
                           note=f"target hit ({intent.context.get('risk_usd', 0):.2f} risk)")
        # Time stop: held long enough -> exit at this bar's close (adverse cost).
        if intent.max_hold_bars is not None and (i - fill_idx) >= intent.max_hold_bars:
            exit_price = c.close - cost.slippage if is_long else c.close + cost.slippage
            r = ((exit_price - fill_price) if is_long else (fill_price - exit_price)) / risk
            outcome = (TradeOutcome.WIN if r > 0 else
                       TradeOutcome.LOSS if r < 0 else TradeOutcome.BREAKEVEN)
            return _result(fill_price, fill_time, exit_price, c.time_utc, r,
                           outcome, ExitReason.TIME_EXIT, mfe, mae,
                           note=f"time exit after {intent.max_hold_bars} bars")

    # Ran out of data while open: mark to last close, label END_OF_DATA.
    last = candles[-1]
    exit_price = last.close
    r = ((exit_price - fill_price) if is_long else (fill_price - exit_price)) / risk
    outcome = TradeOutcome.WIN if r > 0 else (TradeOutcome.LOSS if r < 0 else TradeOutcome.BREAKEVEN)
    return _result(fill_price, fill_time, exit_price, last.time_utc, r,
                   outcome, ExitReason.END_OF_DATA, mfe, mae,
                   note="open at end of data")


def simulate(intents: Sequence[EntryIntent], candles: Sequence[Candle], cost: CostModel) -> List[TradeResult]:
    return [_simulate_intent(it, candles, cost) for it in intents]


def run_setup(
    setup: Setup,
    data: MarketData,
    *,
    base_cost: CostModel = CostModel(),
    cost_grid: Sequence[CostModel] = DEFAULT_COST_GRID,
    entry_filter: Optional[Callable[[Sequence[Candle], int], bool]] = None,
) -> ResearchResult:
    """Run a setup end-to-end: detect -> simulate -> metrics -> stress -> classify.

    `entry_filter(candles, arm_index) -> True` suppresses an intent (used to
    measure no-trade filters like Setup 5's post-spike chop avoidance).
    """
    # A setup may declare a non-M5 execution timeframe (e.g. H1 trend setups).
    exec_tf = getattr(setup, "exec_timeframe", Timeframe.M5)
    candles = data.tf(exec_tf)
    intents = setup.scan(data)
    if entry_filter is not None:
        intents = [it for it in intents if not entry_filter(candles, it.arm_index)]

    base_results = simulate(intents, candles, base_cost)
    base_metrics = compute_metrics(base_results)

    # Spread/slippage sensitivity grid.
    sensitivity: List[SensitivityRow] = []
    for cm in cost_grid:
        m = compute_metrics(simulate(intents, candles, cm))
        sensitivity.append(SensitivityRow(
            cost=cm, expectancy=m.expectancy, win_rate=m.win_rate,
            total_r=m.total_r, trades=m.trades,
        ))

    # Session breakdown (one session for setup 1, but kept general).
    by_session: Dict[str, Metrics] = {}
    sessions = sorted({r.session for r in base_results})
    for s in sessions:
        by_session[s] = compute_metrics([r for r in base_results if r.session == s])

    classification = classify(
        base_metrics,
        cost_stress_expectancy=[row.expectancy for row in sensitivity],
    )

    span = ""
    if candles:
        span = f"{candles[0].time_utc.isoformat()} -> {candles[-1].time_utc.isoformat()}"

    return ResearchResult(
        setup=setup.name,
        version=setup.version,
        rules=setup.rules(),
        base_cost=base_cost,
        metrics=base_metrics,
        classification=classification,
        results=base_results,
        sensitivity=sensitivity,
        by_session=by_session,
        data_span=span,
    )
