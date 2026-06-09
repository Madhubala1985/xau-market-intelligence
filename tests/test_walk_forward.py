"""Tests for P10-002 walk-forward validation (train/test split, no leakage)."""

from datetime import datetime, timedelta, timezone

from src.backtest import Backtester, BacktestConfig, WalkForwardValidator
from src.data.enums import DecisionStatus, Direction
from src.data.schemas import Candle, TradeDecision

UTC = timezone.utc
T0 = datetime(2026, 6, 9, 0, 0, tzinfo=UTC)


def candle(i: int) -> Candle:
    t = T0 + i * timedelta(hours=1)
    base = 100.0 + i
    return Candle(
        symbol="XAUUSD", timeframe="1H", broker_time=t, time_utc=t,
        open=base, high=base + 1, low=base - 1, close=base, tick_volume=100,
    )


def series(n: int) -> list[Candle]:
    return [candle(i) for i in range(n)]


def enter_long_once():
    def strategy(history):
        if len(history) == 1:
            last = history[-1]
            return TradeDecision(
                decision_id="D", time_utc=last.time_utc, symbol="XAUUSD",
                direction=Direction.LONG, status=DecisionStatus.PROPOSED, thesis="t",
                invalidation_price=last.close - 5, entry_price=last.close,
                stop_loss=last.close - 5, take_profits=(last.close + 10,),
            )
        return None
    return strategy


def validator() -> WalkForwardValidator:
    return WalkForwardValidator(Backtester(BacktestConfig(fixed_lot=0.1)))


# ---------------------------------------------------------------------------
# Train/test split
# ---------------------------------------------------------------------------

def test_rolling_split_shapes():
    folds = validator().split(series(10), train_size=4, test_size=2)
    assert len(folds) == 3
    assert folds[0].train_range == (0, 4) and folds[0].test_range == (4, 6)
    assert folds[1].train_range == (2, 6) and folds[1].test_range == (6, 8)
    assert folds[2].train_range == (4, 8) and folds[2].test_range == (8, 10)
    for f in folds:
        assert len(f.train) == 4
        assert len(f.test) == 2


def test_anchored_split_grows_train():
    folds = validator().split(series(10), train_size=4, test_size=2, anchored=True)
    assert [f.train_range for f in folds] == [(0, 4), (0, 6), (0, 8)]
    assert [len(f.train) for f in folds] == [4, 6, 8]
    assert [f.test_range for f in folds] == [(4, 6), (6, 8), (8, 10)]


def test_custom_step_overlapping_train():
    folds = validator().split(series(10), train_size=4, test_size=2, step=1)
    # step 1 -> test windows advance by 1.
    assert [f.test_range for f in folds] == [(4, 6), (5, 7), (6, 8), (7, 9), (8, 10)]


def test_split_validates_sizes():
    import pytest
    with pytest.raises(ValueError):
        validator().split(series(10), train_size=0, test_size=2)


# ---------------------------------------------------------------------------
# No leakage
# ---------------------------------------------------------------------------

def test_test_window_strictly_after_train():
    folds = validator().split(series(20), train_size=6, test_size=3)
    for f in folds:
        # contiguous and ordered: test starts exactly where train ends.
        assert f.test_range[0] == f.train_range[1]
        # every train candle is strictly earlier than every test candle.
        assert f.train[-1].time_utc < f.test[0].time_utc


def test_optimizer_sees_only_train_data():
    seen_ranges = []

    def optimizer(train_candles):
        seen_ranges.append((train_candles[0].time_utc, train_candles[-1].time_utc))
        return enter_long_once()  # ignore params; return a fixed strategy

    folds = validator().split(series(12), train_size=4, test_size=2)
    validator().run(
        series(12), enter_long_once(), train_size=4, test_size=2, optimizer=optimizer
    )
    # The optimizer was called once per fold, each time with train ending before
    # that fold's test window begins.
    assert len(seen_ranges) == len(folds)
    for (train_first, train_last), fold in zip(seen_ranges, folds):
        assert train_last < fold.test[0].time_utc


def test_fold_backtest_matches_standalone_on_test_window():
    bt = Backtester(BacktestConfig(fixed_lot=0.1))
    wf = WalkForwardValidator(bt)
    candles = series(12)
    wf_result = wf.run(candles, enter_long_once(), train_size=4, test_size=2)

    fold0 = wf.split(candles, train_size=4, test_size=2)[0]
    standalone = bt.run(fold0.test, enter_long_once())
    # The validator backtests only the test window -> identical to a standalone run.
    assert wf_result.folds[0].result.num_trades == standalone.num_trades
    assert wf_result.folds[0].result.total_pnl == standalone.total_pnl


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def test_run_aggregates_folds():
    result = validator().run(series(12), enter_long_once(), train_size=4, test_size=2)
    assert result.num_folds == 4
    # Each 2-bar test window enters once -> one trade per fold.
    assert result.total_trades == result.num_folds
    # All trades occur within test windows (>= first test bar of fold 0).
    first_test_time = validator().split(series(12), train_size=4, test_size=2)[0].test[0].time_utc
    for fr in result.folds:
        for trade in fr.result.trades:
            assert trade.opened_at_utc >= first_test_time


def test_no_folds_when_series_too_short():
    result = validator().run(series(3), enter_long_once(), train_size=4, test_size=2)
    assert result.num_folds == 0
    assert result.total_trades == 0
