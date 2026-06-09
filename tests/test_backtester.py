"""Tests for P10-001 backtesting engine (no future leakage, realistic fills)."""

from datetime import datetime, timedelta, timezone

from src.backtest import Backtester, BacktestConfig
from src.data.enums import DecisionStatus, Direction, TradeOutcome
from src.data.schemas import Candle, TradeDecision

UTC = timezone.utc
T0 = datetime(2026, 6, 9, 0, 0, tzinfo=UTC)


def candle(i: int, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(
        symbol="XAUUSD", timeframe="1H",
        broker_time=T0 + i * timedelta(hours=1), time_utc=T0 + i * timedelta(hours=1),
        open=o, high=h, low=l, close=c, tick_volume=100,
    )


def long_decision(entry: float, stop: float, tp: float, did: str = "D") -> TradeDecision:
    return TradeDecision(
        decision_id=did, time_utc=T0, symbol="XAUUSD", direction=Direction.LONG,
        status=DecisionStatus.PROPOSED, thesis="t", invalidation_price=stop,
        entry_price=entry, stop_loss=stop, take_profits=(tp,),
    )


def enter_long_at_first_bar():
    """Strategy: enter LONG only at the first bar; never again."""
    def strategy(history):
        if len(history) == 1:
            last = history[-1]
            return long_decision(last.close, last.close - 5, last.close + 10)
        return None
    return strategy


def cfg(**overrides) -> BacktestConfig:
    base = dict(spread=0.2, slippage=0.1, contract_size=100.0, fixed_lot=0.1)
    base.update(overrides)
    return BacktestConfig(**base)


# ---------------------------------------------------------------------------
# Realistic fills
# ---------------------------------------------------------------------------

def test_entry_fills_at_next_bar_open_with_costs():
    candles = [
        candle(0, 100, 101, 99, 100),    # decision bar (close 100)
        candle(1, 102, 103, 101, 102),   # entry fills here at open 102
        candle(2, 110, 111, 109, 110),   # target 110 hit
    ]
    result = Backtester(cfg()).run(candles, enter_long_at_first_bar())
    trade = result.trades[0]
    # entry = next bar open (102) + spread(0.2) + slippage(0.1) = 102.3 (not 100).
    assert trade.entry_price == 102.3
    assert trade.opened_at_utc == candles[1].time_utc


def test_target_exit_applies_slippage():
    candles = [
        candle(0, 100, 101, 99, 100),
        candle(1, 102, 103, 101, 102),
        candle(2, 110, 111, 105, 110),   # tp 110 hit -> exit 110 - slippage 0.1
    ]
    result = Backtester(cfg()).run(candles, enter_long_at_first_bar())
    trade = result.trades[0]
    assert trade.exit_price == 109.9
    assert "TARGET" in trade.notes
    assert trade.outcome is TradeOutcome.WIN


def test_stop_first_when_bar_hits_both():
    # A bar whose range spans both stop (95) and target (110): stop assumed first.
    candles = [
        candle(0, 100, 101, 99, 100),
        candle(1, 102, 103, 101, 102),
        candle(2, 105, 112, 94, 100),    # low 94 <= stop 95 and high 112 >= tp 110
    ]
    result = Backtester(cfg()).run(candles, enter_long_at_first_bar())
    trade = result.trades[0]
    assert "STOP" in trade.notes
    assert trade.outcome is TradeOutcome.LOSS


def test_pnl_uses_lot_and_contract_size():
    candles = [
        candle(0, 100, 101, 99, 100),
        candle(1, 100, 101, 99, 100),    # entry at 100 + 0.3 = 100.3
        candle(2, 110, 111, 109, 110),   # tp 110 -> exit 109.9
    ]
    result = Backtester(cfg()).run(candles, enter_long_at_first_bar())
    trade = result.trades[0]
    # points = 109.9 - 100.3 = 9.6; pnl = 9.6 * 0.1 * 100 = 96.0
    assert trade.pnl == 96.0
    assert result.ending_balance == result.starting_balance + 96.0


# ---------------------------------------------------------------------------
# No future leakage
# ---------------------------------------------------------------------------

def test_strategy_only_receives_past_history():
    seen = []

    def spy(history):
        seen.append((len(history), history[-1].time_utc))
        return None

    candles = [candle(i, 100, 101, 99, 100) for i in range(5)]
    Backtester(cfg()).run(candles, spy)
    # At call index k the strategy sees exactly k+1 candles ending at candle k.
    for k, (length, last_time) in enumerate(seen):
        assert length == k + 1
        assert last_time == candles[k].time_utc


def test_appending_future_bars_does_not_change_past_trades():
    candles = [
        candle(0, 100, 101, 99, 100),
        candle(1, 102, 103, 101, 102),
        candle(2, 110, 111, 109, 110),   # trade closes here
    ]
    base = Backtester(cfg()).run(candles, enter_long_at_first_bar())

    extended = candles + [candle(3, 120, 130, 119, 125), candle(4, 130, 140, 129, 135)]
    ext = Backtester(cfg()).run(extended, enter_long_at_first_bar())

    # The first trade (opened+closed within the original window) is identical.
    assert base.trades[0].entry_price == ext.trades[0].entry_price
    assert base.trades[0].exit_price == ext.trades[0].exit_price
    assert base.trades[0].pnl == ext.trades[0].pnl
    assert base.trades[0].closed_at_utc == ext.trades[0].closed_at_utc


# ---------------------------------------------------------------------------
# Lifecycle / edge cases
# ---------------------------------------------------------------------------

def test_open_position_closed_at_end_of_data():
    candles = [
        candle(0, 100, 101, 99, 100),
        candle(1, 102, 103, 101, 102),   # entry; never hits stop/tp
    ]
    result = Backtester(cfg()).run(candles, enter_long_at_first_bar())
    assert result.num_trades == 1
    assert "END_OF_DATA" in result.trades[0].notes


def test_no_trades_when_strategy_flat():
    candles = [candle(i, 100, 101, 99, 100) for i in range(4)]
    result = Backtester(cfg()).run(candles, lambda history: None)
    assert result.num_trades == 0
    assert result.ending_balance == result.starting_balance


def test_position_sizer_used_when_no_fixed_lot():
    # No fixed lot -> sizer computes lot from balance/risk/stop.
    candles = [
        candle(0, 100, 101, 99, 100),
        candle(1, 100, 101, 99, 100),
        candle(2, 110, 111, 109, 110),
    ]
    config = BacktestConfig(spread=0.0, slippage=0.0, contract_size=100.0,
                            starting_balance=2000.0, risk_pct=0.005, fixed_lot=None)
    result = Backtester(config).run(candles, enter_long_at_first_bar())
    # risk budget 10; stop distance 5 -> lot = 10/(5*100)=0.02.
    assert result.trades[0].lot_size == 0.02
