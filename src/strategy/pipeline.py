"""End-to-end decision pipeline (integration).

Wires the analysis, scoring, risk, and trade-management engines into one flow:

    data validation
      -> session / HTF bias / regime / structure / liquidity / sweeps
      -> order-flow proxy + futures confirmation
      -> setup (thesis + invalidation from an aligned confirmed sweep)
      -> confidence/uncertainty scoring
      -> trade hypothesis (TradeDecision)
      -> stop placement + position sizing
      -> Risk Governor (final authority)

This orchestrator NEVER executes orders. It produces a TradeDecision and a
RiskDecision; sending is the (separately gated) ExecutionGateway's job. Real-money
trading remains forbidden.

Every engine is injected (constructor params default to the real engines), so each
stage is independently testable and swappable. No look-ahead: only the supplied
candles are used, and the analysis engines are themselves causal/prefix-stable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Sequence

from src.data.enums import Direction
from src.data.schemas import BrokerState, Candle, TradeDecision
from src.data.validation import DataValidator, ValidationStatus
from src.data.sessions import SessionEngine, SessionType
from src.liquidity.liquidity_map import LiquidityMapEngine, LiquiditySide
from src.liquidity.sweep import SweepEngine, SweepStatus
from src.orderflow.futures_confirmation import FuturesConfirmationEngine
from src.orderflow.proxy import OrderFlowProxyEngine
from src.regime.htf_bias import HtfBias, HtfBiasEngine
from src.regime.regime_engine import Regime, RegimeEngine
from src.risk.governor import RiskContext, RiskDecision, RiskGovernor
from src.risk.position_sizing import PositionSizer
from src.strategy.hypothesis import HypothesisInput, TradeHypothesisEngine
from src.strategy.scoring import ComponentScores, ConfidenceEngine, ConfidenceResult
from src.structure.market_structure import Bias, MarketStructureEngine
from src.trade_management.stop_placement import StopPlacementEngine

# Kill-zone sessions (favorable timing).
_KILL_ZONES = {SessionType.LONDON, SessionType.NEW_YORK, SessionType.LONDON_NY_OVERLAP}

_REGIME_SCORE = {
    Regime.TREND: 1.0,
    Regime.EXPANSION: 0.7,
    Regime.RANGE: 0.5,
    Regime.COMPRESSION: 0.3,
    Regime.CHOPPY: 0.0,
    Regime.NEWS_RISK: 0.0,
    Regime.NO_TRADE: 0.0,
}
_VOLATILITY_SCORE = {
    Regime.EXPANSION: 0.8,
    Regime.TREND: 0.7,
    Regime.RANGE: 0.5,
    Regime.COMPRESSION: 0.3,
    Regime.CHOPPY: 0.2,
    Regime.NEWS_RISK: 0.0,
    Regime.NO_TRADE: 0.0,
}


class PipelineStage(str, Enum):
    DATA_REJECTED = "DATA_REJECTED"
    HYPOTHESIS = "HYPOTHESIS"
    RISK_EVALUATED = "RISK_EVALUATED"


@dataclass(frozen=True)
class PipelineInput:
    symbol: str
    exec_candles: Sequence[Candle]
    daily_candles: Sequence[Candle]
    h4_candles: Sequence[Candle]
    broker: BrokerState
    current_spread: float = 0.0
    futures_candles: Optional[Sequence[Candle]] = None
    news_risk: bool = False
    risk_pct: float = 0.005
    daily_loss_pct: float = 0.0
    weekly_loss_pct: float = 0.0
    trades_today: int = 0
    consecutive_losses: int = 0
    open_symbols: frozenset = frozenset()
    now: Optional[datetime] = None


@dataclass(frozen=True)
class PipelineContext:
    session: SessionType
    htf_bias: HtfBias
    regime: Regime
    structure_bias: Bias
    has_setup: bool


@dataclass(frozen=True)
class _Setup:
    thesis: str
    invalidation_price: float
    target_price: Optional[float]


@dataclass(frozen=True)
class PipelineResult:
    stage: "PipelineStage"
    approved: bool
    reason: str
    decision: Optional[TradeDecision] = None
    confidence: Optional[ConfidenceResult] = None
    risk: Optional[RiskDecision] = None
    context: Optional[PipelineContext] = None
    lot_size: float = 0.0


@dataclass
class PipelineEngines:
    """Injectable engine set; defaults to the real engines."""

    validator: DataValidator = field(default_factory=DataValidator)
    session: SessionEngine = field(default_factory=SessionEngine)
    htf_bias: HtfBiasEngine = field(default_factory=HtfBiasEngine)
    regime: RegimeEngine = field(default_factory=RegimeEngine)
    structure: MarketStructureEngine = field(default_factory=MarketStructureEngine)
    liquidity: LiquidityMapEngine = field(default_factory=LiquidityMapEngine)
    sweep: SweepEngine = field(default_factory=SweepEngine)
    orderflow: OrderFlowProxyEngine = field(default_factory=OrderFlowProxyEngine)
    futures: FuturesConfirmationEngine = field(default_factory=FuturesConfirmationEngine)
    hypothesis: TradeHypothesisEngine = field(default_factory=TradeHypothesisEngine)
    confidence: ConfidenceEngine = field(default_factory=ConfidenceEngine)
    sizer: PositionSizer = field(default_factory=PositionSizer)
    stop: StopPlacementEngine = field(default_factory=StopPlacementEngine)
    governor: RiskGovernor = field(default_factory=RiskGovernor)


class DecisionPipeline:
    """Composes the engines into one decision flow. Never executes orders.

    `max_spread` sets the spread scale for execution-quality scoring and must
    use the SAME unit as PipelineInput.current_spread (points by default;
    price units for the live configuration — see make_live_pipeline).
    """

    def __init__(
        self,
        engines: Optional[PipelineEngines] = None,
        *,
        max_spread: float = 50.0,
    ) -> None:
        if max_spread <= 0:
            raise ValueError("max_spread must be > 0")
        self._e = engines or PipelineEngines()
        self._max_spread = max_spread

    def decide(self, inp: PipelineInput) -> PipelineResult:
        e = self._e

        # 1) Data quality gate.
        now = inp.now or (inp.exec_candles[-1].time_utc if inp.exec_candles else None)
        report = e.validator.validate_candles(inp.exec_candles, now=now)
        if report.status is not ValidationStatus.VALID:
            return PipelineResult(
                stage=PipelineStage.DATA_REJECTED, approved=False,
                reason=f"data rejected: {[i.code.value for i in report.blocking_issues]}",
            )

        last = inp.exec_candles[-1]
        entry = last.close
        time_utc = now

        # 2) Context.
        session = e.session.classify(time_utc)
        htf_bias = e.htf_bias.classify(inp.daily_candles, inp.h4_candles).bias
        regime = e.regime.classify(inp.exec_candles, news_risk=inp.news_risk).regime
        structure_bias = e.structure.analyze(inp.exec_candles).final_bias
        liquidity_map = e.liquidity.build(inp.exec_candles)
        sweeps = e.sweep.detect(inp.exec_candles, liquidity_map)
        orderflow = e.orderflow.analyze(inp.exec_candles, structural_bias=structure_bias)
        futures = e.futures.confirm(self._to_bias(htf_bias), inp.futures_candles)

        setup = self._find_setup(htf_bias, sweeps, liquidity_map, entry)
        context = PipelineContext(
            session=session, htf_bias=htf_bias, regime=regime,
            structure_bias=structure_bias, has_setup=setup is not None,
        )

        # 3) Scoring (confidence / uncertainty).
        components = self._score_components(
            htf_bias, structure_bias, regime, session, setup, inp.current_spread
        )
        confidence = e.confidence.score(components, orderflow, futures)

        # 4) Hypothesis.
        decision = e.hypothesis.generate(
            HypothesisInput(
                symbol=inp.symbol, time_utc=time_utc, current_price=entry,
                htf_bias=htf_bias, regime=regime,
                thesis_reason=setup.thesis if setup else None,
                invalidation_price=setup.invalidation_price if setup else None,
                entry_price=entry,
                target_price=setup.target_price if setup else None,
                confidence=confidence.confidence, uncertainty=confidence.uncertainty,
            )
        )

        if decision.direction not in (Direction.LONG, Direction.SHORT):
            return PipelineResult(
                stage=PipelineStage.HYPOTHESIS, approved=False,
                reason=decision.reason or "no actionable setup",
                decision=decision, confidence=confidence, context=context,
            )

        # 5) Stop placement (refine the stop beyond invalidation).
        atr = self._atr(inp.exec_candles)
        placement = e.stop.place(
            decision.direction, entry, decision.invalidation_price,
            atr=atr, spread=inp.current_spread,
            liquidity_levels=[lvl.price for lvl in liquidity_map.levels],
        )
        decision = self._with_stop(decision, placement.stop_price)

        # 6) Position sizing.
        balance = inp.broker.balance or 0.0
        sizing = e.sizer.size(
            decision, balance, inp.risk_pct, spread_price=inp.current_spread
        )
        lot = sizing.lot_size if sizing.approved else 0.0
        intended_risk = sizing.risk_pct if sizing.approved else inp.risk_pct

        # 7) Risk Governor (final authority).
        risk_context = RiskContext(
            broker=inp.broker,
            current_spread=inp.current_spread,
            lot_size=lot,
            intended_risk_pct=intended_risk,
            daily_loss_pct=inp.daily_loss_pct,
            weekly_loss_pct=inp.weekly_loss_pct,
            trades_today=inp.trades_today,
            consecutive_losses=inp.consecutive_losses,
            open_symbols=inp.open_symbols,
            size_factor_hint=confidence.size_factor,
        )
        verdict = e.governor.evaluate(decision, risk_context)

        return PipelineResult(
            stage=PipelineStage.RISK_EVALUATED,
            approved=verdict.approved,
            reason="; ".join(verdict.reasons),
            decision=decision, confidence=confidence, risk=verdict,
            context=context, lot_size=lot,
        )

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _to_bias(htf: HtfBias) -> Bias:
        if htf is HtfBias.BULLISH:
            return Bias.BULLISH
        if htf is HtfBias.BEARISH:
            return Bias.BEARISH
        return Bias.NEUTRAL

    def _find_setup(self, htf_bias, sweeps, liquidity_map, entry) -> Optional[_Setup]:
        target_bias = self._to_bias(htf_bias)
        if target_bias is Bias.NEUTRAL:
            return None
        aligned = [
            s for s in sweeps
            if s.status is SweepStatus.TRUE_SWEEP and s.rejection_bias is target_bias
        ]
        if not aligned:
            return None
        sweep = max(aligned, key=lambda s: s.sweep_index)
        invalidation = sweep.level.price
        target = self._find_target(target_bias, liquidity_map, entry)
        thesis = (
            f"{sweep.swept_side.value} sweep reclaimed with "
            f"{sweep.rejection_bias.value.lower()} rejection"
        )
        return _Setup(thesis=thesis, invalidation_price=invalidation, target_price=target)

    @staticmethod
    def _find_target(target_bias, liquidity_map, entry) -> Optional[float]:
        if target_bias is Bias.BULLISH:
            above = [l.price for l in liquidity_map.buy_side() if l.price > entry]
            return min(above) if above else None
        below = [l.price for l in liquidity_map.sell_side() if l.price < entry]
        return max(below) if below else None

    def _score_components(
        self, htf_bias, structure_bias, regime, session, setup, spread
    ) -> ComponentScores:
        target_bias = self._to_bias(htf_bias)
        if structure_bias is target_bias and target_bias is not Bias.NEUTRAL:
            structure_score = 1.0
        elif structure_bias is Bias.NEUTRAL:
            structure_score = 0.4
        else:
            structure_score = 0.1
        liquidity_score = 1.0 if setup is not None else 0.3
        regime_score = _REGIME_SCORE.get(regime, 0.0)
        volatility_score = _VOLATILITY_SCORE.get(regime, 0.5)
        if session in _KILL_ZONES:
            session_score = 1.0
        elif session is SessionType.ASIAN:
            session_score = 0.5
        else:
            session_score = 0.0
        # Execution quality degrades as spread approaches the configured max
        # (same unit as the spread fed into the pipeline).
        execution_quality = max(0.0, min(1.0, 1.0 - spread / self._max_spread))
        return ComponentScores(
            structure=structure_score, liquidity=liquidity_score, regime=regime_score,
            volatility=volatility_score, session=session_score,
            execution_quality=execution_quality,
        )

    @staticmethod
    def _atr(candles: Sequence[Candle], period: int = 14) -> float:
        window = list(candles[-period:])
        if not window:
            return 0.0
        return sum(c.high - c.low for c in window) / len(window)

    @staticmethod
    def _with_stop(decision: TradeDecision, stop_price: float) -> TradeDecision:
        data = decision.model_dump()
        data["stop_loss"] = stop_price
        return TradeDecision.model_validate(data)
