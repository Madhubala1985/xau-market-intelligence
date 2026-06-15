"""Shared test fixtures for the single liquidity_intel path (LIQUIDITY-INTEL-001).

Ported from the retired demo_challenge test module so the accounting and
broker-execution tests keep exercising the proven chassis through the one
remaining planner/limits.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.data.enums import BrokerConnectionStatus, Direction
from src.data.schemas import BrokerState, Candle, TradeDecision
from src.strategy.pipeline import PipelineInput

SYMBOL = "XAUUSDM"
BROKER_SYMBOL = "XAUUSDm"  # exact Exness case
START = datetime(2026, 6, 15, 13, 0, tzinfo=timezone.utc)


def make_candles(closes, *, timeframe="M5", start=START, minutes=5, wick=0.25):
    """Build a candle series from a list of closes (open = prior close)."""
    candles, t, prev = [], start, closes[0]
    for close in closes:
        candles.append(Candle(
            symbol=SYMBOL, timeframe=timeframe, broker_time=t, time_utc=t,
            open=prev, high=max(prev, close) + wick,
            low=min(prev, close) - wick, close=close, tick_volume=100,
        ))
        t += timedelta(minutes=minutes)
        prev = close
    return candles


def broker_state(now, *, balance=2000.0, open_positions=0) -> BrokerState:
    return BrokerState(
        time_utc=now, connection_status=BrokerConnectionStatus.CONNECTED,
        symbol=SYMBOL, balance=balance, equity=balance, free_margin=balance,
        leverage=200, open_positions=open_positions, trade_allowed=True,
    )


def pipeline_input(m5, *, m15=None, m1=None, balance=2000.0, spread=0.2,
                   open_positions=0, **kwargs):
    now = m5[-1].time_utc
    return PipelineInput(
        symbol=SYMBOL, exec_candles=m5, daily_candles=[], h4_candles=[],
        broker=broker_state(now, balance=balance,
                            open_positions=open_positions),
        current_spread=spread, m15_candles=m15, m1_candles=m1,
        risk_pct=0.030, now=now, **kwargs,
    )


def intel_decision(direction=Direction.SHORT, *, lot=0.05,
                   entry=3350.0, stop=None) -> TradeDecision:
    """A liquidity_intel TradeDecision. lot= encodes the equity RISK TIER
    (0.05 -> 1.0%, 0.10 -> 1.5%), parsed by IntelTradePlanner."""
    stop = stop if stop is not None else (
        entry + 2.5 if direction is Direction.SHORT else entry - 2.5
    )
    target = entry - 5.0 if direction is Direction.SHORT else entry + 5.0
    return TradeDecision(
        decision_id="liqint-test", time_utc=START, symbol=SYMBOL,
        direction=direction,
        setup_type=f"liqint_trend[STRONG,lot={lot:.2f}]",
        thesis="test liquidity_intel setup", invalidation_price=stop,
        entry_price=entry, stop_loss=stop, take_profits=(target,),
        confidence=0.8, uncertainty=0.2,
    )
