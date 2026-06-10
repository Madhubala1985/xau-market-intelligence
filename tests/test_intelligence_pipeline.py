"""Decision-level tests for the INTELLIGENCE-001 wiring.

Proves, through the REAL DecisionPipeline:
- CHOPPY is no longer a blind hard block: a tradeable subtype + strong
  confluence lets a bearish continuation/trap candidate through,
- DANGEROUS_CHOP still blocks regardless of confluence,
- weak confluence keeps tradeable chop blocked (graded, not loosened),
- NEWS_RISK can never be overridden,
- MTF alignment changes the decision (it can direct when the two-timeframe
  combination is neutral, and its absence yields WAIT),
- a sweepless BOS-continuation setup exists (displacement + confluence +
  swing invalidation) and carries a mandatory stop,
- the adaptive risk budget changes the actual position size with evidence.
"""

from datetime import timedelta

from src.data.enums import Direction
from src.liquidity.liquidity_map import (
    LiquidityKind,
    LiquidityLevel,
    LiquiditySide,
)
from src.liquidity.sweep import SweepEvent, SweepStatus
from src.regime.chop_classifier import ChopAssessment, ChopSubtype
from src.regime.htf_bias import HtfBias
from src.regime.regime_engine import Regime
from src.risk.adaptive_risk import POLICY_RISK_CAP
from src.strategy import DecisionPipeline, PipelineEngines, PipelineInput
from src.strategy.confluence import ConfluenceReport, MtfAlignment
from src.strategy.hypothesis import HypothesisInput, TradeHypothesisEngine
from src.structure.market_structure import (
    Bias,
    StructureEvent,
    StructureEventType,
    StructureResult,
    SwingPoint,
    SwingType,
)
from tests.test_pipeline import (
    T0,
    _StubHtf,
    _StubRegime,
    _StubStructure,
    base_input,
    big_broker,
    candle,
    rising,
)


def falling(n):
    return [candle(i, 100 - i, 101 - i, 99 - i, 99.5 - i) for i in range(n)]


def falling_with_displacement(n):
    candles = falling(n - 1)
    last = candles[-1].close
    candles.append(candle(n - 1, last, last + 0.1, last - 6.5, last - 6.3))
    return candles


class _StubSweepBear:
    """One aligned TRUE_SWEEP of buy-side liquidity (bearish rejection)."""

    def __init__(self, level_price):
        self._level_price = level_price

    def detect(self, candles, levels):
        level = LiquidityLevel(
            kind=LiquidityKind.PREV_DAY_HIGH, side=LiquiditySide.BUY_SIDE,
            price=self._level_price, time_utc=candles[0].time_utc,
        )
        return [SweepEvent(
            level=level, swept_side=LiquiditySide.BUY_SIDE,
            rejection_bias=Bias.BEARISH, sweep_index=len(candles) - 2,
            sweep_time=candles[-1].time_utc, status=SweepStatus.TRUE_SWEEP,
        )]


class _NoSweep:
    def detect(self, candles, levels):
        return []


class _StubChop:
    def __init__(self, subtype, tradeable):
        self._a = ChopAssessment(
            subtype=subtype, tradeable=tradeable, reason="stub",
            drift_ratio=0.4, displacement_ratio=2.0, wick_ratio=0.3,
        )

    def classify(self, candles, sweeps=(), *, spread_ratio=0.0):
        return self._a


class _StubMtf:
    def __init__(self, direction, score):
        self._direction = direction
        self._score = score

    def align(self, **kwargs):
        b = (Bias.BEARISH if self._direction is Direction.SHORT
             else Bias.BULLISH if self._direction is Direction.LONG else None)
        return MtfAlignment(d1=b, h4=b, h1=b, m15=b, m5=b,
                            direction=self._direction, score=self._score,
                            reason="stub")


class _StubConfluence:
    def __init__(self, score):
        self._score = score

    def assess(self, direction, **kwargs):
        return ConfluenceReport(
            direction=direction, score=self._score,
            components={}, missing=(), statuses={}, reason="stub",
        )


class _StubStructureBearishBos:
    """Bearish BOS + a protective swing HIGH above price."""

    def __init__(self, entry):
        self._entry = entry

    def analyze(self, candles):
        swing = SwingPoint(swing_type=SwingType.HIGH, index=len(candles) - 8,
                           time_utc=candles[-8].time_utc,
                           price=self._entry + 4.0,
                           confirmed_index=len(candles) - 6)
        event = StructureEvent(event_type=StructureEventType.BOS,
                               bias=Bias.BEARISH, index=len(candles) - 2,
                               time_utc=candles[-2].time_utc,
                               price=self._entry + 1.0, broken_swing=swing)
        return StructureResult(swings=(swing,), events=(event,),
                               final_bias=Bias.BEARISH)


def bearish_engines(entry, *, regime=Regime.CHOPPY,
                    chop=None, confluence=0.80, mtf_score=0.90,
                    sweep=True):
    e = PipelineEngines()
    e.htf_bias = _StubHtf(HtfBias.BEARISH)
    e.regime = _StubRegime(regime)
    e.structure = _StubStructure(Bias.BEARISH)
    e.sweep = _StubSweepBear(entry + 5) if sweep else _NoSweep()
    if chop is not None:
        e.chop = chop
    e.mtf = _StubMtf(Direction.SHORT, mtf_score)
    e.confluence = _StubConfluence(confluence)
    return e


# ---------------------------------------------------------------------------
# Graded CHOPPY gate
# ---------------------------------------------------------------------------

def test_choppy_with_trap_and_high_confluence_trades_short():
    candles = falling(30)
    entry = candles[-1].close
    engines = bearish_engines(
        entry,
        chop=_StubChop(ChopSubtype.TRAP_REVERSAL_FROM_CHOP, tradeable=True),
        confluence=0.80,
    )
    result = DecisionPipeline(engines).decide(
        base_input(candles, broker=big_broker())
    )
    assert result.decision.direction is Direction.SHORT
    assert result.approved is True
    assert result.decision.stop_loss is not None          # stop stays mandatory
    assert result.decision.stop_loss > result.decision.entry_price
    assert result.adaptive_risk is not None
    assert result.adaptive_risk.risk_pct <= POLICY_RISK_CAP
    assert result.context.chop.subtype is ChopSubtype.TRAP_REVERSAL_FROM_CHOP


def test_dangerous_chop_still_blocks_despite_max_confluence():
    candles = falling(30)
    entry = candles[-1].close
    engines = bearish_engines(
        entry,
        chop=_StubChop(ChopSubtype.DANGEROUS_CHOP, tradeable=False),
        confluence=0.95,
    )
    result = DecisionPipeline(engines).decide(
        base_input(candles, broker=big_broker())
    )
    assert result.approved is False
    assert result.decision.direction is Direction.NO_TRADE
    assert "DANGEROUS_CHOP" in result.decision.reason


def test_tradeable_chop_with_weak_confluence_stays_blocked():
    candles = falling(30)
    entry = candles[-1].close
    engines = bearish_engines(
        entry,
        chop=_StubChop(ChopSubtype.CONTINUATION_AFTER_CHOP, tradeable=True),
        confluence=0.40,
    )
    result = DecisionPipeline(engines).decide(
        base_input(candles, broker=big_broker())
    )
    assert result.approved is False
    assert result.decision.direction is Direction.NO_TRADE
    assert "confluence" in result.decision.reason
    assert "CONTINUATION_AFTER_CHOP" in result.decision.reason


def test_news_risk_regime_can_never_be_overridden():
    engine = TradeHypothesisEngine()
    decision = engine.generate(HypothesisInput(
        symbol="XAUUSD", time_utc=T0, current_price=100.0,
        htf_bias=HtfBias.BEARISH, regime=Regime.NEWS_RISK,
        thesis_reason="anything", invalidation_price=105.0,
        regime_allows=True,  # even an (incorrect) override flag cannot pass
    ))
    assert decision.direction is Direction.NO_TRADE
    assert "NEWS_RISK" in decision.reason


# ---------------------------------------------------------------------------
# MTF alignment effects
# ---------------------------------------------------------------------------

def test_mtf_alignment_directs_when_two_timeframe_bias_is_neutral():
    candles = falling(30)
    entry = candles[-1].close
    engines = bearish_engines(entry, regime=Regime.TREND)
    engines.htf_bias = _StubHtf(HtfBias.NEUTRAL)  # old D1+H4 combo: neutral
    result = DecisionPipeline(engines).decide(
        base_input(candles, broker=big_broker())
    )
    assert result.decision.direction is Direction.SHORT
    assert result.context.mtf.direction is Direction.SHORT


def test_without_mtf_direction_the_model_waits():
    candles = falling(30)
    entry = candles[-1].close
    engines = bearish_engines(entry, regime=Regime.TREND, sweep=False)
    engines.htf_bias = _StubHtf(HtfBias.NEUTRAL)
    engines.mtf = _StubMtf(None, 0.3)
    result = DecisionPipeline(engines).decide(
        base_input(candles, broker=big_broker())
    )
    assert result.approved is False
    assert result.decision.direction in (Direction.WAIT, Direction.NO_TRADE)


# ---------------------------------------------------------------------------
# BOS continuation setup (sweepless)
# ---------------------------------------------------------------------------

def test_bos_continuation_setup_trades_without_a_sweep():
    candles = falling_with_displacement(30)
    entry = candles[-1].close
    engines = bearish_engines(entry, regime=Regime.TREND, sweep=False,
                              confluence=0.70)
    engines.structure = _StubStructureBearishBos(entry)
    result = DecisionPipeline(engines).decide(
        base_input(candles, broker=big_broker())
    )
    assert result.decision.direction is Direction.SHORT
    assert result.approved is True
    assert result.context.setup_kind == "bos_continuation"
    assert result.decision.stop_loss is not None
    assert result.decision.stop_loss > result.decision.entry_price


def test_continuation_requires_confluence_and_displacement():
    # same structure but weak confluence -> no setup -> no trade
    candles = falling_with_displacement(30)
    entry = candles[-1].close
    engines = bearish_engines(entry, regime=Regime.TREND, sweep=False,
                              confluence=0.30)
    engines.structure = _StubStructureBearishBos(entry)
    result = DecisionPipeline(engines).decide(
        base_input(candles, broker=big_broker())
    )
    assert result.approved is False
    # and without displacement (clean falling series) it also refuses
    flat_candles = falling(30)
    engines2 = bearish_engines(flat_candles[-1].close, regime=Regime.TREND,
                               sweep=False, confluence=0.90)
    engines2.structure = _StubStructureBearishBos(flat_candles[-1].close)
    result2 = DecisionPipeline(engines2).decide(
        base_input(flat_candles, broker=big_broker())
    )
    assert result2.approved is False


# ---------------------------------------------------------------------------
# Adaptive risk drives the actual size
# ---------------------------------------------------------------------------

def test_adaptive_risk_changes_position_size_with_evidence():
    candles = falling(30)
    entry = candles[-1].close
    weak_engines = bearish_engines(entry, regime=Regime.TREND,
                                   confluence=0.45, mtf_score=0.30)
    strong_engines = bearish_engines(entry, regime=Regime.TREND,
                                     confluence=0.90, mtf_score=0.90)
    weak = DecisionPipeline(weak_engines).decide(
        base_input(candles, broker=big_broker())
    )
    strong = DecisionPipeline(strong_engines).decide(
        base_input(candles, broker=big_broker())
    )
    assert weak.lot_size > 0 and strong.lot_size > 0
    assert strong.lot_size > weak.lot_size          # evidence sized it up...
    assert strong.adaptive_risk.risk_pct <= POLICY_RISK_CAP  # ...inside policy
    assert weak.adaptive_risk.risk_pct < strong.adaptive_risk.risk_pct
