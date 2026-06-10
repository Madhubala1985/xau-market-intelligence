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

from src.data.aggregation import AggregationError, aggregate
from src.data.enums import Direction, Timeframe
from src.data.schemas import BrokerState, Candle, TradeDecision
from src.data.session_levels import AsianRangeContext, AsianRangeEngine
from src.data.validation import DataValidator, ValidationStatus
from src.data.sessions import SessionEngine, SessionType
from src.liquidity.liquidity_map import LiquidityMapEngine, LiquiditySide
from src.liquidity.sweep import SweepEngine, SweepStatus
from src.orderflow.futures_confirmation import FuturesConfirmationEngine
from src.orderflow.macro_context import (
    FileMacroProvider,
    MacroContext,
    gold_pressure,
)
from src.orderflow.proxy import OrderFlowProxyEngine
from src.regime.chop_classifier import ChopAssessment, ChopClassifier
from src.regime.htf_bias import HtfBias, HtfBiasEngine
from src.regime.regime_engine import Regime, RegimeEngine, RegimeResult
from src.regime.volatility_classifier import (
    VolatilityAssessment,
    VolatilityClassifier,
)
from src.risk.adaptive_risk import (
    AdaptiveRiskDecision,
    AdaptiveRiskEngine,
    AdaptiveRiskInputs,
)
from src.risk.governor import RiskContext, RiskDecision, RiskGovernor
from src.risk.position_sizing import PositionSizer
from src.strategy.confluence import (
    ConfluenceEngine,
    ConfluenceReport,
    MtfAlignment,
    MtfAlignmentEngine,
)
from src.strategy.hypothesis import HypothesisInput, TradeHypothesisEngine
from src.strategy.m1_refinement import M1Refinement, M1RefinementEngine
from src.strategy.scoring import ComponentScores, ConfidenceEngine, ConfidenceResult
from src.structure.market_structure import (
    Bias,
    MarketStructureEngine,
    StructureEventType,
    StructureResult,
    SwingType,
)
from src.structure.premium_discount import PremiumDiscountEngine, PriceZone
from src.structure.zones import ZoneEngine
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
    # INTELLIGENCE-002: TRUE multi-timeframe candles fetched from MT5. When
    # absent the pipeline degrades honestly (M15/H1 aggregated from the exec
    # feed and labelled so; M1 simply unavailable).
    m15_candles: Optional[Sequence[Candle]] = None
    h1_candles: Optional[Sequence[Candle]] = None
    m1_candles: Optional[Sequence[Candle]] = None
    news_risk: bool = False
    risk_pct: float = 0.005
    daily_loss_pct: float = 0.0
    weekly_loss_pct: float = 0.0
    trades_today: int = 0
    consecutive_losses: int = 0
    open_symbols: frozenset = frozenset()
    news_caution: bool = False  # high-impact soon / medium active: reduce risk
    now: Optional[datetime] = None


@dataclass(frozen=True)
class PipelineContext:
    session: SessionType
    htf_bias: HtfBias
    regime: Regime
    structure_bias: Bias
    has_setup: bool
    # Graded intelligence (INTELLIGENCE-001) — optional so older callers and
    # tests that construct a bare context keep working.
    regime_reason: str = ""
    chop: Optional[ChopAssessment] = None
    mtf: Optional[MtfAlignment] = None
    confluence: Optional[ConfluenceReport] = None
    price_zone: Optional[PriceZone] = None
    displacement_ratio: float = 0.0
    setup_kind: str = ""  # "sweep_reclaim" | "bos_continuation" | ""
    volatility: Optional[VolatilityAssessment] = None
    asian: Optional[AsianRangeContext] = None
    m1: Optional[M1Refinement] = None
    macro_pressure: str = "UNAVAILABLE"


@dataclass(frozen=True)
class _Setup:
    thesis: str
    invalidation_price: float
    target_price: Optional[float]
    kind: str = "sweep_reclaim"


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
    adaptive_risk: Optional[AdaptiveRiskDecision] = None


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
    # INTELLIGENCE-001: previously implemented-but-unwired gold intelligence,
    # now first-class pipeline engines.
    zones: ZoneEngine = field(default_factory=ZoneEngine)
    premium_discount: PremiumDiscountEngine = field(
        default_factory=PremiumDiscountEngine
    )
    chop: ChopClassifier = field(default_factory=ChopClassifier)
    mtf: MtfAlignmentEngine = field(default_factory=MtfAlignmentEngine)
    confluence: ConfluenceEngine = field(default_factory=ConfluenceEngine)
    adaptive_risk: AdaptiveRiskEngine = field(default_factory=AdaptiveRiskEngine)
    # INTELLIGENCE-002: gold session levels + volatility safety layer.
    asian: AsianRangeEngine = field(default_factory=AsianRangeEngine)
    volatility: VolatilityClassifier = field(default_factory=VolatilityClassifier)
    # FINAL-INTELLIGENCE: macro/futures confirmation (operator file until a
    # real feed exists — stale/missing reads UNAVAILABLE) + M1 refinement.
    macro_provider: object = field(
        default_factory=lambda: FileMacroProvider("configs/macro_context.json")
    )
    m1_refine: M1RefinementEngine = field(default_factory=M1RefinementEngine)


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
        regime_window: int = 60,
        chop_override_confluence: float = 0.65,
        continuation_confluence: float = 0.60,
        continuation_displacement: float = 1.5,
    ) -> None:
        if max_spread <= 0:
            raise ValueError("max_spread must be > 0")
        self._e = engines or PipelineEngines()
        self._max_spread = max_spread
        # Regime is classified on a RECENT window. Live evidence (INTELLIGENCE
        # audit): counting structure flips over the whole 300-candle (25h M5)
        # window made CHOPPY near-permanent and blocked entire sessions.
        if regime_window < 6:
            raise ValueError("regime_window must be >= 6")
        self._regime_window = regime_window
        self._chop_override_confluence = chop_override_confluence
        self._continuation_confluence = continuation_confluence
        self._continuation_displacement = continuation_displacement

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

        # 2) Context — every implemented gold-intelligence engine, wired.
        session = e.session.classify(time_utc)
        htf_bias = e.htf_bias.classify(inp.daily_candles, inp.h4_candles).bias
        # Regime over the RECENT window only (a 25h window is regime soup).
        regime_result: RegimeResult = e.regime.classify(
            inp.exec_candles[-self._regime_window:], news_risk=inp.news_risk
        )
        regime = regime_result.regime
        structure = e.structure.analyze(inp.exec_candles)
        structure_bias = structure.final_bias
        liquidity_map = e.liquidity.build(inp.exec_candles)
        sweeps = e.sweep.detect(inp.exec_candles, liquidity_map)
        orderflow = e.orderflow.analyze(inp.exec_candles, structural_bias=structure_bias)
        futures = e.futures.confirm(self._to_bias(htf_bias), inp.futures_candles)
        zones = e.zones.build(inp.exec_candles)
        dealing_range = e.premium_discount.range_from_candles(inp.exec_candles)
        price_zone = (
            e.premium_discount.classify(dealing_range, entry)
            if dealing_range is not None else None
        )
        displacement_ratio = self._displacement_ratio(inp.exec_candles)
        spread_ratio = max(0.0, inp.current_spread / self._max_spread)

        # Volatility safety layer (INTELLIGENCE-002): dangerous states block.
        volatility = e.volatility.classify(
            inp.exec_candles, spread_ratio=spread_ratio
        )
        # Asian range / London-NY expansion context (honest: unknown when the
        # feed lacks today's Asian session).
        asian = e.asian.analyze(inp.exec_candles, time_utc)

        # Multi-timeframe alignment (INTELLIGENCE-002): TRUE MT5 candles per
        # timeframe when supplied; otherwise honest aggregation of the exec
        # feed, labelled as such in `sources` — never pretended to be native.
        m15, h1, mtf_sources = self._mtf_frames(inp)
        mtf = e.mtf.align(
            daily=inp.daily_candles, h4=inp.h4_candles, h1=h1, m15=m15,
            m5_bias=None if structure_bias is Bias.NEUTRAL else structure_bias,
            m1_state=self._m1_state(inp.m1_candles),
            sources=mtf_sources,
        )

        # Chop decomposition + graded confluence for the candidate direction.
        chop = (
            e.chop.classify(inp.exec_candles, sweeps, spread_ratio=spread_ratio)
            if regime is Regime.CHOPPY else None
        )
        candidate = mtf.direction or self._htf_direction(htf_bias)
        macro_ctx: MacroContext = e.macro_provider.assess(time_utc)
        macro_press, _ = gold_pressure(macro_ctx)
        confluence = e.confluence.assess(
            candidate,
            mtf=mtf,
            sweeps=sweeps,
            structure=structure,
            zones=zones,
            price_zone=price_zone,
            displacement_ratio=displacement_ratio,
            session=session,
            spread_ratio=spread_ratio,
            orderflow=orderflow,
            total_candles=len(inp.exec_candles),
            asian=asian,
            macro=macro_ctx,
        )

        # Graded regime gate: CHOPPY may be overridden ONLY by a tradeable
        # chop subtype with strong confluence; danger states never pass.
        regime_allows, regime_detail = self._regime_gate(chop, confluence)

        setup = self._find_setup(candidate, sweeps, liquidity_map, entry)
        if setup is None and candidate is not None:
            setup = self._find_continuation_setup(
                candidate, structure, confluence, displacement_ratio, entry,
                liquidity_map,
            )

        # M1 refinement (FINAL-INTELLIGENCE): only consulted when a setup
        # ALREADY exists; a veto can only delay this cycle's entry — it can
        # never create one or override the higher-timeframe stack.
        m1 = e.m1_refine.assess(
            inp.m1_candles, candidate if setup is not None else None
        )
        m1_veto = setup is not None and m1.vetoes_entry
        if m1_veto:
            setup = None

        context = PipelineContext(
            session=session, htf_bias=htf_bias, regime=regime,
            structure_bias=structure_bias, has_setup=setup is not None,
            regime_reason=getattr(regime_result, "reason", ""),
            chop=chop, mtf=mtf, confluence=confluence, price_zone=price_zone,
            displacement_ratio=displacement_ratio,
            setup_kind=setup.kind if setup else "",
            volatility=volatility, asian=asian,
            m1=m1, macro_pressure=macro_press,
        )

        # Hard volatility gate: dangerous states refuse new entries outright.
        # EXPANSION never blocks by itself (03_RISK_POLICY volatility rule).
        if volatility.dangerous:
            return PipelineResult(
                stage=PipelineStage.HYPOTHESIS, approved=False,
                reason=(
                    f"dangerous volatility {volatility.state.value}: "
                    f"{volatility.reason}"
                ),
                context=context,
            )

        # M1 veto: a qualified setup is DELAYED this cycle (never re-routed).
        if m1_veto:
            return PipelineResult(
                stage=PipelineStage.HYPOTHESIS, approved=False,
                reason=f"entry delayed by M1 refinement: {m1.reason}",
                context=context,
            )

        # 3) Scoring (confidence / uncertainty), graded by chop/confluence.
        components = self._score_components(
            htf_bias, structure_bias, regime, session, setup,
            inp.current_spread, chop=chop, confluence=confluence,
        )
        confidence = e.confidence.score(components, orderflow, futures)

        # 4) Hypothesis (thesis + invalidation invariants unchanged).
        decision = e.hypothesis.generate(
            HypothesisInput(
                symbol=inp.symbol, time_utc=time_utc, current_price=entry,
                htf_bias=self._candidate_htf(htf_bias, candidate), regime=regime,
                thesis_reason=setup.thesis if setup else None,
                invalidation_price=setup.invalidation_price if setup else None,
                entry_price=entry,
                target_price=setup.target_price if setup else None,
                setup_type=setup.kind if setup else None,
                confidence=confidence.confidence, uncertainty=confidence.uncertainty,
                regime_allows=regime_allows,
                regime_detail=regime_detail,
            )
        )

        # 5) Adaptive risk budget (INTELLIGENCE-001): evidence decides the
        # budget; inp.risk_pct acts as the POLICY CAP, never the default.
        balance = inp.broker.balance or 0.0
        adaptive = e.adaptive_risk.decide(AdaptiveRiskInputs(
            equity=balance,
            confluence_score=confluence.score,
            mtf_score=mtf.score,
            confidence=confidence.confidence,
            uncertainty=confidence.uncertainty,
            regime_tradeable=(
                regime is not Regime.CHOPPY or bool(regime_allows)
            ),
            spread_ratio=spread_ratio,
            news_clear=not inp.news_risk,
            consecutive_losses=inp.consecutive_losses,
            daily_loss_pct=inp.daily_loss_pct,
            weekly_loss_pct=inp.weekly_loss_pct,
            open_positions=inp.broker.open_positions,
            news_caution=inp.news_caution,
            macro_conflict=confluence.components.get("macro", 0.5) == 0.0,
        ))

        if decision.direction not in (Direction.LONG, Direction.SHORT):
            return PipelineResult(
                stage=PipelineStage.HYPOTHESIS, approved=False,
                reason=decision.reason or "no actionable setup",
                decision=decision, confidence=confidence, context=context,
                adaptive_risk=adaptive,
            )

        # 6) Stop placement (refine the stop beyond invalidation).
        atr = self._atr(inp.exec_candles)
        placement = e.stop.place(
            decision.direction, entry, decision.invalidation_price,
            atr=atr, spread=inp.current_spread,
            liquidity_levels=[lvl.price for lvl in liquidity_map.levels],
        )
        decision = self._with_stop(decision, placement.stop_price)

        # 7) Position sizing from the ADAPTIVE budget, capped by policy.
        risk_budget = min(adaptive.risk_pct, inp.risk_pct)
        sizing = e.sizer.size(
            decision, balance, risk_budget, spread_price=inp.current_spread
        )
        lot = sizing.lot_size if sizing.approved else 0.0
        intended_risk = sizing.risk_pct if sizing.approved else risk_budget

        # 8) Risk Governor (final authority).
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
            context=context, lot_size=lot, adaptive_risk=adaptive,
        )

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _to_bias(htf: HtfBias) -> Bias:
        if htf is HtfBias.BULLISH:
            return Bias.BULLISH
        if htf is HtfBias.BEARISH:
            return Bias.BEARISH
        return Bias.NEUTRAL

    @staticmethod
    def _htf_direction(htf: HtfBias) -> Optional[Direction]:
        if htf is HtfBias.BULLISH:
            return Direction.LONG
        if htf is HtfBias.BEARISH:
            return Direction.SHORT
        return None

    @staticmethod
    def _candidate_htf(htf_bias: HtfBias, candidate: Optional[Direction]) -> HtfBias:
        """The directional bias handed to the hypothesis engine.

        MTF alignment (D1/H4/H1/M15/M5, D1-weighted) may support a direction
        even when the older two-timeframe combination reads NEUTRAL; the
        NO_TRADE safety state (insufficient daily data) is never upgraded.
        """
        if htf_bias is HtfBias.NO_TRADE or candidate is None:
            return htf_bias
        return (
            HtfBias.BULLISH if candidate is Direction.LONG else HtfBias.BEARISH
        )

    def _regime_gate(
        self,
        chop: Optional[ChopAssessment],
        confluence: ConfluenceReport,
    ) -> tuple[Optional[bool], str]:
        """Graded CHOPPY gate: tradeable subtype + strong confluence required."""
        if chop is None:
            return None, ""
        if not chop.tradeable:
            return False, f"{chop.subtype.value}: {chop.reason}"
        if confluence.score >= self._chop_override_confluence:
            return True, (
                f"{chop.subtype.value} override: confluence "
                f"{confluence.score:.2f} >= {self._chop_override_confluence}"
            )
        return False, (
            f"{chop.subtype.value} tradeable but confluence "
            f"{confluence.score:.2f} < {self._chop_override_confluence}"
        )

    @staticmethod
    def _mtf_frames(inp: PipelineInput) -> tuple[list, list, dict]:
        """M15/H1 series + an honest per-timeframe source map.

        Preference order per timeframe: TRUE MT5 candles supplied by the
        caller -> aggregation of the exec feed (labelled) -> missing.
        D1/H4 are always caller-supplied MT5 fetches in the live path.
        """
        sources = {"d1": "MT5", "h4": "MT5"}

        def frame(native, target: Timeframe, key: str) -> list:
            if native:
                sources[key] = "MT5"
                return list(native)
            try:
                out = aggregate(inp.exec_candles, target)
            except (AggregationError, ValueError):
                out = []
            sources[key] = "aggregated(M5)" if out else "missing"
            return out

        m15 = frame(inp.m15_candles, Timeframe.M15, "m15")
        h1 = frame(inp.h1_candles, Timeframe.H1, "h1")
        sources["m5"] = "MT5"
        sources["m1"] = "MT5" if inp.m1_candles else "missing"
        return m15, h1, sources

    @staticmethod
    def _m1_state(m1_candles: Optional[Sequence[Candle]]) -> Optional[str]:
        """M1 trigger state (display/refinement only; carries no weight)."""
        if not m1_candles or len(m1_candles) < 3:
            return None
        last = list(m1_candles)[-3:]
        net = last[-1].close - last[0].open
        threshold = 0.1 * sum(c.high - c.low for c in last) / 3
        if net > threshold:
            return "BULLISH"
        if net < -threshold:
            return "BEARISH"
        return "FLAT"

    @staticmethod
    def _displacement_ratio(candles: Sequence[Candle], window: int = 20) -> float:
        recent = list(candles[-window:])
        if not recent:
            return 0.0
        ranges = sorted(c.high - c.low for c in recent)
        median = ranges[len(ranges) // 2]
        if median <= 0:
            return 0.0
        return max(abs(c.close - c.open) for c in recent) / median

    def _find_setup(
        self, candidate: Optional[Direction], sweeps, liquidity_map, entry
    ) -> Optional[_Setup]:
        if candidate is None:
            return None
        target_bias = (
            Bias.BULLISH if candidate is Direction.LONG else Bias.BEARISH
        )
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
        return _Setup(
            thesis=thesis, invalidation_price=invalidation,
            target_price=target, kind="sweep_reclaim",
        )

    def _find_continuation_setup(
        self,
        candidate: Direction,
        structure: StructureResult,
        confluence: ConfluenceReport,
        displacement_ratio: float,
        entry: float,
        liquidity_map,
    ) -> Optional[_Setup]:
        """Sweepless continuation: BOS + displacement + strong confluence.

        Live evidence showed clean directional continuation (impulse legs,
        pullbacks, continuation breakdowns) with no fresh sweep-reclaim; the
        old single-setup rule made the model structurally passive. This setup
        still demands an aligned structural BREAK, real displacement, graded
        confluence, AND a swing-based invalidation — never a naked breakout.
        """
        if confluence.score < self._continuation_confluence:
            return None
        if displacement_ratio < self._continuation_displacement:
            return None
        events = list(structure.events)
        if not events:
            return None
        want = Bias.BULLISH if candidate is Direction.LONG else Bias.BEARISH
        last = events[-1]
        if last.event_type is not StructureEventType.BOS or last.bias is not want:
            return None
        invalidation = self._swing_invalidation(candidate, structure, entry)
        if invalidation is None:
            return None
        target = self._find_target(want, liquidity_map, entry)
        thesis = (
            f"{want.value.lower()} BOS continuation with displacement "
            f"{displacement_ratio:.1f}x (confluence {confluence.score:.2f})"
        )
        return _Setup(
            thesis=thesis, invalidation_price=invalidation,
            target_price=target, kind="bos_continuation",
        )

    @staticmethod
    def _swing_invalidation(
        candidate: Direction, structure: StructureResult, entry: float
    ) -> Optional[float]:
        """Most recent protective swing against the trade direction."""
        if candidate is Direction.LONG:
            lows = [
                s.price for s in structure.swings
                if s.swing_type is SwingType.LOW and s.price < entry
            ]
            return lows[-1] if lows else None
        highs = [
            s.price for s in structure.swings
            if s.swing_type is SwingType.HIGH and s.price > entry
        ]
        return highs[-1] if highs else None

    @staticmethod
    def _find_target(target_bias, liquidity_map, entry) -> Optional[float]:
        if target_bias is Bias.BULLISH:
            above = [l.price for l in liquidity_map.buy_side() if l.price > entry]
            return min(above) if above else None
        below = [l.price for l in liquidity_map.sell_side() if l.price < entry]
        return max(below) if below else None

    def _score_components(
        self, htf_bias, structure_bias, regime, session, setup, spread,
        *, chop: Optional[ChopAssessment] = None,
        confluence: Optional[ConfluenceReport] = None,
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
        # Graded chop (INTELLIGENCE-001): a tradeable subtype is not a zero —
        # it scores with the confluence behind it (capped well below TREND).
        if (
            regime is Regime.CHOPPY
            and chop is not None and chop.tradeable
            and confluence is not None
        ):
            regime_score = min(0.75, 0.25 + 0.5 * confluence.score)
            volatility_score = max(volatility_score, 0.4)
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
