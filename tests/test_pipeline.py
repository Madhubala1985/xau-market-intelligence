"""Tests for the end-to-end DecisionPipeline integration.

Covers the gating paths with real engines and the full APPROVE path with small
injected stubs for the hard-to-craft analysis stages. The pipeline never executes
orders -- it returns a TradeDecision + RiskDecision only.
"""

from datetime import datetime, timedelta, timezone

from src.data.enums import BrokerConnectionStatus, Direction
from src.data.schemas import BrokerState, Candle
from src.liquidity.liquidity_map import (
    LiquidityKind,
    LiquidityLevel,
    LiquidityMap,
    LiquiditySide,
)
from src.liquidity.sweep import SweepEvent, SweepStatus
from src.regime.htf_bias import HtfBias
from src.regime.regime_engine import Regime
from src.risk import RiskAction
from src.strategy import (
    DecisionPipeline,
    PipelineEngines,
    PipelineInput,
    PipelineStage,
)
from src.structure.market_structure import Bias

UTC = timezone.utc
T0 = datetime(2026, 6, 9, 9, 0, tzinfo=UTC)  # 09:00 UTC Tuesday -> London (kill zone)


def candle(i: int, o: float, h: float, l: float, c: float) -> Candle:
    t = T0 + i * timedelta(hours=1)
    return Candle(
        symbol="XAUUSD", timeframe="1H", broker_time=t, time_utc=t,
        open=o, high=h, low=l, close=c, tick_volume=100,
    )


def rising(n: int) -> list[Candle]:
    return [candle(i, 100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(n)]


def flat(n: int) -> list[Candle]:
    return [candle(i, 100, 100.5, 99.5, 100) for i in range(n)]


def broker(**overrides) -> BrokerState:
    kwargs = dict(
        time_utc=T0, connection_status=BrokerConnectionStatus.CONNECTED,
        symbol="XAUUSD", balance=2000.0, equity=2000.0, open_positions=0,
        trade_allowed=True,
    )
    kwargs.update(overrides)
    return BrokerState(**kwargs)


def big_broker(**overrides) -> BrokerState:
    # Larger balance so a 0.5%-risk gold trade can be sized above the min lot
    # (a $2000 account legitimately cannot, which the risk engine enforces).
    kwargs = dict(balance=50000.0, equity=50000.0)
    kwargs.update(overrides)
    return broker(**kwargs)


def base_input(exec_candles, **overrides) -> PipelineInput:
    kwargs = dict(
        symbol="XAUUSD", exec_candles=exec_candles, daily_candles=rising(8),
        h4_candles=rising(8), broker=broker(), current_spread=2.0, risk_pct=0.005,
    )
    kwargs.update(overrides)
    return PipelineInput(**kwargs)


# ---------------------------------------------------------------------------
# Gating paths (real engines)
# ---------------------------------------------------------------------------

def test_data_rejected_short_circuits():
    # Duplicate timestamps -> validator NO_TRADE.
    dup = [candle(0, 100, 101, 99, 100), candle(0, 100, 101, 99, 100)]
    result = DecisionPipeline().decide(base_input(dup))
    assert result.stage is PipelineStage.DATA_REJECTED
    assert result.approved is False
    assert result.decision is None


def test_flat_market_yields_no_actionable_decision():
    result = DecisionPipeline().decide(base_input(flat(30)))
    # No HTF bias / no setup -> WAIT or NO_TRADE; never approved.
    assert result.approved is False
    assert result.decision is not None
    assert result.decision.direction in (Direction.WAIT, Direction.NO_TRADE)


# ---------------------------------------------------------------------------
# Stubs to drive the full approve path deterministically
# ---------------------------------------------------------------------------

class _StubHtf:
    def __init__(self, bias):
        self._bias = bias

    def classify(self, daily, h4):
        class _R:
            bias = self._bias
        return _R()


class _StubRegime:
    def __init__(self, regime):
        self._regime = regime

    def classify(self, candles, news_risk=False):
        class _R:
            regime = self._regime
        return _R()


class _StubStructure:
    def __init__(self, bias):
        self._bias = bias

    def analyze(self, candles):
        class _R:
            final_bias = self._bias
            events = ()
            swings = ()
        return _R()


class _StubSweep:
    """Returns one aligned TRUE_SWEEP of sell-side liquidity (bullish rejection)."""

    def __init__(self, level_price: float):
        self._level_price = level_price

    def detect(self, candles, levels):
        level = LiquidityLevel(
            kind=LiquidityKind.PREV_DAY_LOW, side=LiquiditySide.SELL_SIDE,
            price=self._level_price, time_utc=candles[0].time_utc,
        )
        return [
            SweepEvent(
                level=level, swept_side=LiquiditySide.SELL_SIDE,
                rejection_bias=Bias.BULLISH, sweep_index=len(candles) - 2,
                sweep_time=candles[-1].time_utc, status=SweepStatus.TRUE_SWEEP,
            )
        ]


def bullish_engines(level_price: float) -> PipelineEngines:
    e = PipelineEngines()
    e.htf_bias = _StubHtf(HtfBias.BULLISH)
    e.regime = _StubRegime(Regime.TREND)
    e.structure = _StubStructure(Bias.BULLISH)
    e.sweep = _StubSweep(level_price)
    return e


# ---------------------------------------------------------------------------
# Full approve path
# ---------------------------------------------------------------------------

def test_full_long_setup_is_approved():
    candles = rising(30)
    entry = candles[-1].close
    pipeline = DecisionPipeline(bullish_engines(level_price=entry - 5))
    result = pipeline.decide(base_input(candles, broker=big_broker()))

    assert result.stage is PipelineStage.RISK_EVALUATED
    assert result.decision is not None
    assert result.decision.direction is Direction.LONG
    assert result.confidence is not None
    assert result.risk is not None
    assert result.risk.action in (RiskAction.APPROVE, RiskAction.REDUCE)
    assert result.approved is True
    assert result.lot_size > 0
    # Stop sits below entry (refined beyond invalidation).
    assert result.decision.stop_loss < result.decision.entry_price


def test_disconnected_broker_blocks_even_with_setup():
    candles = rising(30)
    entry = candles[-1].close
    pipeline = DecisionPipeline(bullish_engines(level_price=entry - 5))
    result = pipeline.decide(
        base_input(candles, broker=big_broker(connection_status=BrokerConnectionStatus.UNKNOWN,
                                              trade_allowed=False))
    )
    assert result.stage is PipelineStage.RISK_EVALUATED
    assert result.approved is False
    assert result.risk.action is RiskAction.BLOCK


def test_news_risk_regime_blocks_setup():
    # Real regime engine with news_risk=True -> NEWS_RISK -> hypothesis NO_TRADE.
    e = PipelineEngines()
    e.htf_bias = _StubHtf(HtfBias.BULLISH)
    e.structure = _StubStructure(Bias.BULLISH)
    candles = rising(30)
    pipeline = DecisionPipeline(e)
    result = pipeline.decide(base_input(candles, news_risk=True))
    assert result.approved is False
    assert result.decision.direction in (Direction.WAIT, Direction.NO_TRADE)


def test_pipeline_never_executes_orders():
    # The pipeline has no execution/order method; it only decides.
    methods = dir(DecisionPipeline)
    for banned in ("execute", "order", "send", "buy", "sell", "place_order"):
        assert not any(banned in m.lower() for m in methods)


def test_high_risk_setup_blocked_by_governor():
    candles = rising(30)
    entry = candles[-1].close
    pipeline = DecisionPipeline(bullish_engines(level_price=entry - 5))
    # risk_pct above the governor's per-trade cap -> sizing blocks -> lot 0 -> governor blocks.
    result = pipeline.decide(base_input(candles, broker=big_broker(), risk_pct=0.05))
    assert result.approved is False
    assert result.risk.action is RiskAction.BLOCK
