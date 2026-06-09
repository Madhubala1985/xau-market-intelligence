"""Backtesting engine (Task P10-001).

Event-driven, strictly causal backtester. References 07_TEST_POLICY.md (Backtest
Requirements) and 06_DATA_POLICY.md (look-ahead ban).

Causality / no future leakage:
- The strategy is called with history = candles[:t+1] only, so a decision at bar t
  can never see a future bar.
- A decision made at bar t fills at bar t+1's OPEN (next-bar fill), with spread and
  slippage applied adversely (realistic fills).
- Stops/take-profits are checked bar-by-bar; if both could trigger within one bar,
  the STOP is assumed hit first (conservative, no optimistic fills).

Realistic costs: entry pays (spread + slippage); exits pay slippage; optional
commission per lot. Lot sizing reuses the P7-002 PositionSizer unless a fixed lot
is configured. The backtester never places real orders.

Strategy contract:
    strategy(history: Sequence[Candle]) -> Optional[TradeDecision]
where history is candles[:t+1]. Return an actionable LONG/SHORT TradeDecision to
enter (flat only), or None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional, Sequence, Tuple

from src.data.enums import Direction, TradeOutcome
from src.data.schemas import Candle, TradeDecision, TradeRecord
from src.risk.governor import RiskLimits
from src.risk.position_sizing import PositionSizer

Strategy = Callable[[Sequence[Candle]], Optional[TradeDecision]]


@dataclass(frozen=True)
class BacktestConfig:
    spread: float = 0.0
    slippage: float = 0.0
    commission_per_lot: float = 0.0
    contract_size: float = 100.0
    starting_balance: float = 2000.0
    risk_pct: float = 0.005
    fixed_lot: Optional[float] = None  # if set, bypass PositionSizer


@dataclass(frozen=True)
class BacktestResult:
    trades: Tuple[TradeRecord, ...]
    starting_balance: float
    ending_balance: float
    total_pnl: float
    num_trades: int
    wins: int
    losses: int
    win_rate: float


@dataclass
class _OpenPosition:
    decision: TradeDecision
    entry_index: int
    entry_time: datetime
    entry_fill: float
    stop: float
    take_profit: Optional[float]
    lot: float


class Backtester:
    """Runs a strictly causal backtest of a strategy over a candle series."""

    def __init__(self, config: Optional[BacktestConfig] = None) -> None:
        self._cfg = config or BacktestConfig()
        self._sizer = PositionSizer(RiskLimits(), contract_size=self._cfg.contract_size)

    def run(self, candles: Sequence[Candle], strategy: Strategy) -> BacktestResult:
        cfg = self._cfg
        balance = cfg.starting_balance
        trades: List[TradeRecord] = []
        position: Optional[_OpenPosition] = None
        pending: Optional[TradeDecision] = None

        for t, candle in enumerate(candles):
            # 1) Fill a pending entry at THIS bar's open (next-bar fill).
            if pending is not None and position is None:
                position = self._open(pending, t, candle)
                pending = None

            # 2) Manage an open position using this bar's range.
            if position is not None:
                exit_info = self._check_exit(position, candle)
                if exit_info is not None:
                    exit_price, reason = exit_info
                    record, pnl = self._close(position, candle, exit_price, reason, balance)
                    balance += pnl
                    trades.append(record)
                    position = None

            # 3) When flat and nothing pending, ask the strategy (causal slice).
            if position is None and pending is None:
                decision = strategy(candles[: t + 1])
                if self._is_actionable(decision):
                    lot = self._size(decision)
                    if lot > 0:
                        pending = decision

        # Close any still-open position at the final close.
        if position is not None and candles:
            last = candles[-1]
            record, pnl = self._close(position, last, last.close, "END_OF_DATA", balance)
            balance += pnl
            trades.append(record)

        return self._summarize(tuple(trades), balance)

    # -- entry / sizing ----------------------------------------------------
    def _is_actionable(self, decision: Optional[TradeDecision]) -> bool:
        return (
            decision is not None
            and decision.direction in (Direction.LONG, Direction.SHORT)
            and decision.entry_price is not None
            and decision.stop_loss is not None
        )

    def _size(self, decision: TradeDecision) -> float:
        if self._cfg.fixed_lot is not None:
            return self._cfg.fixed_lot
        result = self._sizer.size(
            decision, self._cfg.starting_balance, self._cfg.risk_pct,
            spread_price=self._cfg.spread,
        )
        return result.lot_size if result.approved else 0.0

    def _open(self, decision: TradeDecision, index: int, candle: Candle) -> _OpenPosition:
        cost = self._cfg.spread + self._cfg.slippage
        if decision.direction is Direction.LONG:
            entry_fill = candle.open + cost
        else:
            entry_fill = candle.open - cost
        lot = self._size(decision)
        take_profit = decision.take_profits[0] if decision.take_profits else None
        return _OpenPosition(
            decision=decision,
            entry_index=index,
            entry_time=candle.time_utc,
            entry_fill=round(entry_fill, 8),
            stop=decision.stop_loss,
            take_profit=take_profit,
            lot=lot,
        )

    # -- exits -------------------------------------------------------------
    def _check_exit(
        self, position: _OpenPosition, candle: Candle
    ) -> Optional[Tuple[float, str]]:
        slip = self._cfg.slippage
        if position.decision.direction is Direction.LONG:
            stop_hit = candle.low <= position.stop
            tp_hit = position.take_profit is not None and candle.high >= position.take_profit
            if stop_hit:  # stop assumed first (conservative)
                return position.stop - slip, "STOP"
            if tp_hit:
                return position.take_profit - slip, "TARGET"
        else:  # SHORT
            stop_hit = candle.high >= position.stop
            tp_hit = position.take_profit is not None and candle.low <= position.take_profit
            if stop_hit:
                return position.stop + slip, "STOP"
            if tp_hit:
                return position.take_profit + slip, "TARGET"
        return None

    def _close(
        self,
        position: _OpenPosition,
        candle: Candle,
        exit_price: float,
        reason: str,
        balance: float,
    ) -> Tuple[TradeRecord, float]:
        cfg = self._cfg
        if position.decision.direction is Direction.LONG:
            points = exit_price - position.entry_fill
        else:
            points = position.entry_fill - exit_price
        pnl = points * position.lot * cfg.contract_size
        pnl -= cfg.commission_per_lot * position.lot
        pnl = round(pnl, 8)

        if pnl > 0:
            outcome = TradeOutcome.WIN
        elif pnl < 0:
            outcome = TradeOutcome.LOSS
        else:
            outcome = TradeOutcome.BREAKEVEN

        record = TradeRecord(
            record_id=f"{position.decision.decision_id}-{position.entry_index}",
            created_at_utc=candle.time_utc,
            symbol=position.decision.symbol,
            direction=position.decision.direction,
            outcome=outcome,
            decision_id=position.decision.decision_id,
            opened_at_utc=position.entry_time,
            closed_at_utc=candle.time_utc,
            entry_price=position.entry_fill,
            exit_price=round(exit_price, 8),
            stop_loss=position.stop,
            take_profit=position.take_profit,
            lot_size=position.lot,
            pnl=pnl,
            pnl_pct=pnl / cfg.starting_balance if cfg.starting_balance else None,
            thesis=position.decision.thesis,
            notes=f"exit={reason}",
        )
        return record, pnl

    # -- summary -----------------------------------------------------------
    def _summarize(self, trades: Tuple[TradeRecord, ...], balance: float) -> BacktestResult:
        wins = sum(1 for r in trades if r.outcome is TradeOutcome.WIN)
        losses = sum(1 for r in trades if r.outcome is TradeOutcome.LOSS)
        decided = wins + losses
        total_pnl = round(sum(r.pnl for r in trades if r.pnl is not None), 8)
        return BacktestResult(
            trades=trades,
            starting_balance=self._cfg.starting_balance,
            ending_balance=round(balance, 8),
            total_pnl=total_pnl,
            num_trades=len(trades),
            wins=wins,
            losses=losses,
            win_rate=wins / decided if decided else 0.0,
        )
