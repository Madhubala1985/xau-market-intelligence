"""Walk-forward validation (Task P10-002).

Splits a candle series into ordered (train, test) folds and validates the strategy
on the UNSEEN test windows. References 07_TEST_POLICY.md (walk-forward validation)
and 06_DATA_POLICY.md (look-ahead ban).

No leakage:
- Every test window is strictly later than its train window (test_start ==
  train_end); train and test never overlap, and test never precedes train.
- The optimizer (if any) is given the train candles only; it never sees test data.
- The backtest runs only on the test window, where the Backtester remains strictly
  causal (history = test[:k+1]).

Rolling mode: the train window slides forward. Anchored mode: the train window
starts at 0 and grows. Either way the test window is the next unseen block.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from src.backtest.backtester import Backtester, BacktestResult, Strategy
from src.data.enums import TradeOutcome
from src.data.schemas import Candle

# Given the train candles, return the strategy to evaluate on the test window.
Optimizer = Callable[[Sequence[Candle]], Strategy]


@dataclass(frozen=True)
class Fold:
    index: int
    train: Tuple[Candle, ...]
    test: Tuple[Candle, ...]
    train_range: Tuple[int, int]  # [start, end) indices
    test_range: Tuple[int, int]


@dataclass(frozen=True)
class FoldResult:
    index: int
    train_range: Tuple[int, int]
    test_range: Tuple[int, int]
    result: BacktestResult


@dataclass(frozen=True)
class WalkForwardResult:
    folds: Tuple[FoldResult, ...]
    num_folds: int
    total_trades: int
    total_pnl: float
    wins: int
    losses: int
    win_rate: float


class WalkForwardValidator:
    """Builds ordered train/test folds and backtests the unseen test windows."""

    def __init__(self, backtester: Optional[Backtester] = None) -> None:
        self._backtester = backtester or Backtester()

    # -- splitting ---------------------------------------------------------
    def split(
        self,
        candles: Sequence[Candle],
        *,
        train_size: int,
        test_size: int,
        step: Optional[int] = None,
        anchored: bool = False,
    ) -> List[Fold]:
        """Return ordered folds; test always immediately follows train."""
        if train_size < 1 or test_size < 1:
            raise ValueError("train_size and test_size must be >= 1")
        step = test_size if step is None else step
        if step < 1:
            raise ValueError("step must be >= 1")

        n = len(candles)
        folds: List[Fold] = []
        start = 0
        index = 0
        while True:
            test_start = start + train_size
            test_end = test_start + test_size
            if test_end > n:
                break
            train_start = 0 if anchored else start
            folds.append(
                Fold(
                    index=index,
                    train=tuple(candles[train_start:test_start]),
                    test=tuple(candles[test_start:test_end]),
                    train_range=(train_start, test_start),
                    test_range=(test_start, test_end),
                )
            )
            start += step
            index += 1
        return folds

    # -- running -----------------------------------------------------------
    def run(
        self,
        candles: Sequence[Candle],
        strategy: Strategy,
        *,
        train_size: int,
        test_size: int,
        step: Optional[int] = None,
        anchored: bool = False,
        optimizer: Optional[Optimizer] = None,
    ) -> WalkForwardResult:
        """Validate the strategy fold-by-fold on the unseen test windows."""
        folds = self.split(
            candles, train_size=train_size, test_size=test_size,
            step=step, anchored=anchored,
        )

        fold_results: List[FoldResult] = []
        for fold in folds:
            # The optimizer only ever sees train data (no leakage).
            fold_strategy = optimizer(fold.train) if optimizer is not None else strategy
            result = self._backtester.run(fold.test, fold_strategy)
            fold_results.append(
                FoldResult(
                    index=fold.index,
                    train_range=fold.train_range,
                    test_range=fold.test_range,
                    result=result,
                )
            )

        return self._aggregate(tuple(fold_results))

    # -- aggregate ---------------------------------------------------------
    @staticmethod
    def _aggregate(fold_results: Tuple[FoldResult, ...]) -> WalkForwardResult:
        total_trades = sum(fr.result.num_trades for fr in fold_results)
        total_pnl = round(sum(fr.result.total_pnl for fr in fold_results), 8)
        wins = sum(
            1
            for fr in fold_results
            for r in fr.result.trades
            if r.outcome is TradeOutcome.WIN
        )
        losses = sum(
            1
            for fr in fold_results
            for r in fr.result.trades
            if r.outcome is TradeOutcome.LOSS
        )
        decided = wins + losses
        return WalkForwardResult(
            folds=fold_results,
            num_folds=len(fold_results),
            total_trades=total_trades,
            total_pnl=total_pnl,
            wins=wins,
            losses=losses,
            win_rate=wins / decided if decided else 0.0,
        )
