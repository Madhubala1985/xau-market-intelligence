"""Liquidity Intelligence decision engine (Task LIQUIDITY-INTEL-001). DEMO ONLY.

The single autonomous XAU/USD decision engine. It replaces every prior
decision profile (demo_challenge / smc_challenge / smc_v2) and is the ONLY
brain wired into the trading service. Written from scratch around a market
POSTURE model rather than a fixed per-candle gate chain: each cycle the engine
reads the full multi-timeframe picture, classifies what the market is doing,
and decides for itself whether to engage, wait, or stay flat — and, when a
position is open, whether to hold/trail or protect the exit.

Postures (the autonomy):

    TREND              — HTF + LTF aligned with displacement: take continuation
                         pullbacks into an aligned FVG/OB WITH the trend; runner
                         target (3R) + trailing.
    LIQUIDITY_REVERSAL — an engineered liquidity pool was swept and RECLAIMED:
                         fade the swept side after the reclaim holds; stop sits
                         BEYOND the rejection extreme (past the hunted pool),
                         scalp-to-structure target (2R).
    RANGE_SCALP        — tradeable range: fade a premium/discount extreme only
                         after a boundary sweep; tight target (1.5R).
    WAIT               — no qualified posture yet: every WAIT prints an explicit
                         re-arm condition and rescans next candle (never a
                         silent permanent block).
    FLAT               — dangerous volatility / structureless chop / news risk:
                         no entries, explicit re-arm condition.

Stop-loss doctrine (non-negotiable): the stop is placed on REAL invalidation —
beyond the engineered-liquidity extreme / protected structure — never at the
naked pool where the market hunts stops. `_protect_stop_from_pool` pushes a
stop that would sit at/inside a resting liquidity pool out beyond it. If the
protected stop is wider than the budget allows, the engine reduces size (risk
tier) or, failing that, WAITs / SKIPs — risk is never widened into the trap.

Exit / reverse mechanics: the execution chassis exposes exactly one order
pathway (open) plus stop modification — there is NO market-close order path,
by design (one execution path, stops never widen). Protective exits are
therefore expressed through the proven trailing/break-even protection engine
and the mandatory SL/TP; a REVERSE is a fresh opposite entry once the position
is flat. The engine surfaces its MANAGE / EXIT / REVERSE intent in the cycle
output for transparency; the chassis executes it with proven mechanics.

This module sends no orders and holds no credentials. The ExecutionGateway
(kill switch + flags + governor) remains the only order pathway and the
RiskGovernor has final authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Optional, Sequence, Tuple

from src.data.aggregation import AggregationError, aggregate
from src.data.enums import DecisionStatus, Direction, Timeframe
from src.data.schemas import Candle, TradeDecision
from src.data.session_levels import AsianRangeContext, AsianRangeEngine
from src.data.sessions import SessionEngine, SessionType
from src.data.validation import DataValidator, ValidationConfig, ValidationStatus
from src.liquidity.liquidity_map import (
    LiquidityKind,
    LiquidityMap,
    LiquidityMapEngine,
)
from src.liquidity.sweep import SweepEngine, SweepStatus
from src.orderflow.proxy import OrderFlowProxyEngine, ProxyPressure
from src.regime.chop_classifier import ChopClassifier, ChopSubtype
from src.regime.htf_bias import HtfBias, HtfBiasEngine
from src.regime.regime_engine import Regime
from src.regime.volatility_classifier import VolatilityClassifier
from src.risk.governor import RiskContext, RiskGovernor, RiskLimits
from src.strategy.confluence import MtfAlignment, MtfAlignmentEngine
from src.strategy.pipeline import (
    PipelineContext,
    PipelineInput,
    PipelineResult,
    PipelineStage,
)
from src.strategy.scoring import ConfidenceResult, ScoreRecommendation
from src.structure.market_structure import (
    Bias,
    MarketStructureEngine,
    StructureEventType,
    StructureResult,
)
from src.structure.premium_discount import PremiumDiscountEngine, PriceZone
from src.structure.zones import Zone, ZoneEngine, ZoneKind

# Profile / mode identity (single profile; no version names).
PROFILE_NAME = "liquidity_intel"

# Risk TIER lots carried in setup_type (parsed by IntelTradePlanner): they
# select the EQUITY RISK PERCENTAGE, not a fixed broker lot — the planner
# derives the actual lot from equity and the protected stop so size compounds.
#   0.10 -> STRONG -> 1.5% equity risk;  0.05 -> NORMAL -> 1.0% equity risk.
TIER_LOT_NORMAL = 0.05
TIER_LOT_STRONG = 0.10
SETUP_TYPE_TEMPLATE = "liqint_{posture}[{grade},lot={lot:.2f}]"

# Tactical stop geometry (hard bounds — the stop is local invalidation, never
# a wide HTF structural stop).
MIN_STOP_DISTANCE = 0.50
MAX_STOP_ABSOLUTE = 8.0
REJECTION_WICK_RATIO = 0.40

# Displacement thresholds (impulse size vs the recent median candle range).
ANCHOR_DISPLACEMENT = 1.3   # a real institutional impulse, not drift
STRONG_DISPLACEMENT = 1.6   # STRONG-grade footprint
CONFLICT_DISPLACEMENT = 1.3  # required to fade a unanimous LTF consensus

# An anchor whose level sits further than this many M5-ATRs from price is no
# longer live structure (do not anchor a trade to stale levels).
STALE_ANCHOR_ATR_MULT = 10.0

_RECENT_EVENT_WINDOW = 40   # candles: how fresh a BOS/CHOCH must be
_ZONE_TOUCH_WINDOW = 3      # candles allowed between a zone touch and trigger
_RECLAIM_HOLD = 1           # candles the reclaim must hold past the swept level

# H8 zone consumption: a stop the market just traded through is "consumed";
# re-fading the same level minutes later pays twice for one piece of info.
CONSUMED_STOP_TTL = timedelta(minutes=30)
CONSUMED_STOP_PROXIMITY = MAX_STOP_ABSOLUTE
CONSUMED_STOP_CLEARANCE_CAP = 6.0

# Quality bar defaults (tuned ONLY by replay evidence, never live).
DEFAULT_QUALITY_BAR = 0.62
DEFAULT_STRONG_BAR = 0.78

_KILL_ZONES = {
    SessionType.LONDON, SessionType.NEW_YORK, SessionType.LONDON_NY_OVERLAP,
}
_LOW_LIQUIDITY_SESSIONS = {
    SessionType.ROLLOVER, SessionType.LOW_LIQUIDITY, SessionType.CLOSED,
}


class Posture:
    TREND = "TREND"
    LIQUIDITY_REVERSAL = "LIQUIDITY_REVERSAL"
    RANGE_SCALP = "RANGE_SCALP"
    WAIT = "WAIT"
    FLAT = "FLAT"


class Grade:
    STRONG = "STRONG"
    NORMAL = "NORMAL"


def make_intel_limits(expected_symbol: str) -> RiskLimits:
    """The single liquidity_intel risk envelope (demo-only, anchors absolute).

    Identical survival bounds to the proven campaign envelope — these are the
    owner's standing anchors and are never weakened: 3%/trade survival cap,
    daily 5% net pause, weekly 10% net stop, max 3 open, a 25/day survival
    CEILING (the engine's quality bar governs the real cadence, not a hard
    artificial per-day cap), spread <= 1.0.
    """
    return RiskLimits(
        expected_symbol=expected_symbol,
        max_risk_per_trade=0.030,
        max_daily_loss=0.05,
        max_weekly_loss=0.10,
        max_trades_per_day=25,
        max_open_trades=3,
        max_spread=1.0,
    )


@dataclass
class IntelEngines:
    """Injectable analytics primitives (defaults are the real reused ones)."""

    validator: DataValidator = field(default_factory=DataValidator)
    session: SessionEngine = field(default_factory=SessionEngine)
    htf: HtfBiasEngine = field(default_factory=HtfBiasEngine)
    mtf: MtfAlignmentEngine = field(default_factory=MtfAlignmentEngine)
    structure: MarketStructureEngine = field(default_factory=MarketStructureEngine)
    liquidity: LiquidityMapEngine = field(default_factory=LiquidityMapEngine)
    sweep: SweepEngine = field(default_factory=SweepEngine)
    zones: ZoneEngine = field(default_factory=ZoneEngine)
    asian: AsianRangeEngine = field(default_factory=AsianRangeEngine)
    premium_discount: PremiumDiscountEngine = field(
        default_factory=PremiumDiscountEngine
    )
    volatility: VolatilityClassifier = field(default_factory=VolatilityClassifier)
    chop: ChopClassifier = field(default_factory=ChopClassifier)
    orderflow: OrderFlowProxyEngine = field(default_factory=OrderFlowProxyEngine)


@dataclass(frozen=True)
class _Setup:
    """A fully-resolved entry candidate for the active posture."""

    posture: str
    direction: Direction
    anchor_label: str
    anchor_detail: str
    anchor_level: Optional[float]
    trigger: str
    stop_price: float
    stop_distance: float
    stop_source: str
    stop_logic: str
    target_r: float


class LiquidityIntelEngine:
    """Posture-driven autonomous SMC engine. Same decide() interface as the
    legacy pipeline so SupervisedDemoSession / TradingService drive it
    unchanged (gateway, journal, reconciliation, trailing all reused)."""

    def __init__(
        self,
        limits: RiskLimits,
        *,
        max_spread: float = 1.0,
        quality_bar: float = DEFAULT_QUALITY_BAR,
        strong_bar: float = DEFAULT_STRONG_BAR,
        engines: Optional[IntelEngines] = None,
    ) -> None:
        if max_spread <= 0:
            raise ValueError("max_spread must be > 0")
        if not (0.0 < quality_bar <= strong_bar <= 1.0):
            raise ValueError("require 0 < quality_bar <= strong_bar <= 1")
        self._limits = limits
        self._governor = RiskGovernor(limits)
        self._max_spread = max_spread
        self._quality_bar = quality_bar
        self._strong_bar = strong_bar
        self._e = engines or IntelEngines()
        self.threshold_profile = PROFILE_NAME
        self._last_m5_time = None
        self._last_m1_time = None
        self._last_stop_price: Optional[float] = None
        # H8: Direction -> (violated stop level, loss time). In-memory only.
        self._consumed_stops: dict = {}

    # -- H8 hook (called by the session on CLOSE_DETECTED reason=SL) ----------
    def note_stop_loss(self, direction, stop_price, time_utc) -> None:
        if direction is None or stop_price is None:
            return
        self._consumed_stops[direction] = (float(stop_price), time_utc)

    # -- public --------------------------------------------------------------
    def decide(self, inp: PipelineInput) -> PipelineResult:  # noqa: C901
        e = self._e
        now = inp.now or (
            inp.exec_candles[-1].time_utc if inp.exec_candles else None
        )
        report = e.validator.validate_candles(inp.exec_candles, now=now)
        if report.status is not ValidationStatus.VALID:
            return PipelineResult(
                stage=PipelineStage.DATA_REJECTED, approved=False,
                reason="data rejected: "
                       f"{[i.code.value for i in report.blocking_issues]}",
            )

        m5 = list(inp.exec_candles)
        m15 = list(inp.m15_candles) if inp.m15_candles else self._aggregate(
            m5, Timeframe.M15)
        h1 = list(inp.h1_candles) if inp.h1_candles else self._aggregate(
            m5, Timeframe.H1)
        m1 = list(inp.m1_candles) if inp.m1_candles else []
        last = m5[-1]
        entry = last.close
        session = e.session.classify(now)
        in_killzone = session in _KILL_ZONES
        spread = max(inp.current_spread, 0.0)
        equity = inp.broker.equity or inp.broker.balance or 0.0
        atr5 = self._atr(m5)

        # -- full institutional context (every TF, every cycle) -------------
        structure = e.structure.analyze(m5)
        liquidity_map = e.liquidity.build(m5)
        sweeps = e.sweep.detect(m5, liquidity_map)
        zones = e.zones.build(m5)
        asian = e.asian.analyze(m5, now)
        dealing_range = e.premium_discount.range_from_candles(m5)
        price_zone = (
            e.premium_discount.classify(dealing_range, entry)
            if dealing_range is not None else None
        )
        orderflow = e.orderflow.analyze(m5, structure.final_bias)
        displacement, disp_direction = self._displacement(m5)
        htf_bias = self._htf_bias(inp.daily_candles, inp.h4_candles)
        mtf = e.mtf.align(
            daily=inp.daily_candles, h4=inp.h4_candles, h1=h1, m15=m15,
            m5_bias=(structure.final_bias
                     if structure.final_bias is not Bias.NEUTRAL else None),
            m1_state=self._m1_state(m1),
        )
        candidate = mtf.direction or self._htf_direction(htf_bias)

        # Seed the cycle's full terminal output (every required field).
        ch = self._base_output(
            session, in_killzone, candidate, displacement, structure,
            zones, liquidity_map, sweeps, price_zone, orderflow, entry,
        )
        new_candle = self._detect_new_candle(m5, m1)
        ch["new_candle_detected"] = new_candle
        ch["htf_context"] = (
            f"d1={self._b(mtf.d1)} h4={self._b(mtf.h4)} h1={self._b(mtf.h1)} "
            f"m15={self._b(mtf.m15)} m5={self._b(mtf.m5)} "
            f"mtf_score={mtf.score:.2f} htf_bias={htf_bias.value}"
        )
        context = self._context(session, htf_bias, structure.final_bias,
                                 candidate, price_zone, displacement, ch)

        # -- environment / safety gates --------------------------------------
        if spread > self._max_spread:
            return self._flat(context, ch,
                              f"spread too high ({spread:.3f} > "
                              f"{self._max_spread:.3f})", waiting="SPREAD")
        if equity <= 0:
            return self._flat(context, ch, "account equity unknown",
                              waiting="ACCOUNTING")
        if inp.news_risk:
            return self._flat(context, ch,
                              "NEWS_RISK: active high-impact window — no new "
                              "entries until it clears", waiting="NEWS")

        # Market-state gate on the environment (current impulse never flags
        # itself): dangerous volatility / structureless chop are not traded.
        environment = m5[:-1] if len(m5) > 1 else m5
        spread_ratio = spread / self._max_spread if self._max_spread else 0.0
        vol = e.volatility.classify(environment, spread_ratio=spread_ratio)
        chop = e.chop.classify(environment, sweeps, spread_ratio=spread_ratio,
                               directional_score=mtf.score)
        ch["market_state"] = f"vol={vol.state.value} chop={chop.subtype.value}"
        if vol.dangerous:
            return self._flat(
                context, ch,
                f"VOLATILITY_BLOCK: {vol.state.value} — {vol.reason}; "
                "dangerous conditions are not traded",
                waiting="SWEEP",
                plan="wait for volatility to normalize, then re-qualify")
        if chop.subtype in (ChopSubtype.DANGEROUS_CHOP,
                            ChopSubtype.LOW_QUALITY_CHOP):
            return self._flat(
                context, ch,
                f"CHOP_BLOCK: {chop.subtype.value} — {chop.reason}; "
                "consolidation is not traded",
                waiting="SWEEP",
                plan="wait for a sweep/displacement out of the range")

        # -- posture classification (the autonomy) ---------------------------
        posture, reversal_dir, range_dir = self._classify_posture(
            candidate, mtf, displacement, disp_direction, m5, sweeps,
            chop, price_zone,
        )
        ch["posture"] = posture
        ch["narrative"] = self._narrative(posture, candidate, mtf, price_zone)

        if posture == Posture.WAIT:
            waiting, plan = self._reentry_plan(candidate, zones)
            return self._wait(
                context, ch,
                f"WAIT: no qualified posture for {self._dirlabel(candidate)} "
                f"({ch['narrative']}) — institutional setup not yet present",
                waiting=waiting, plan=plan)

        # Resolve the posture into a concrete, executable setup.
        if posture == Posture.LIQUIDITY_REVERSAL:
            trade_dir = reversal_dir
        elif posture == Posture.RANGE_SCALP:
            trade_dir = range_dir
        else:
            trade_dir = candidate
        if trade_dir is None:
            waiting, plan = self._reentry_plan(candidate, zones)
            return self._wait(context, ch,
                              "waiting for a directional bias to form",
                              waiting="HTF_DIRECTION")
        ch["direction"] = trade_dir.value

        # Session/liquidity context must be institutional (kill zone or a real
        # liquidity event) — never trade dead, eventless tape.
        liquidity_context = self._liquidity_context(
            trade_dir, asian, sweeps, liquidity_map, entry)
        ch["liquidity_context"] = liquidity_context
        if not in_killzone and liquidity_context == "NONE":
            return self._wait(
                context, ch,
                f"outside kill zones ({session.value}) with no liquidity "
                "event — institutional context missing",
                waiting="SWEEP",
                plan="wait for London/NY or an Asian/session liquidity sweep")

        setup = self._resolve_setup(
            posture, trade_dir, entry, m5, m1, atr5, spread, structure,
            sweeps, zones, liquidity_map, displacement, disp_direction,
        )
        if setup is None:
            waiting, plan = self._reentry_plan(trade_dir, zones)
            return self._wait(
                context, ch,
                f"{posture}: anchor/trigger or a protected tactical stop not "
                "yet available — re-entry plan armed, rescanning next candle",
                waiting=waiting, plan=plan)

        ch["smc_anchor"] = setup.anchor_label
        ch["entry_trigger"] = setup.trigger

        # Stale-anchor guard: the anchor must be live near price.
        if (setup.anchor_level is not None and atr5 > 0
                and abs(entry - setup.anchor_level)
                > STALE_ANCHOR_ATR_MULT * atr5):
            waiting, plan = self._reentry_plan(trade_dir, zones)
            return self._wait(
                context, ch,
                f"SMC_ANCHOR_STALE: {setup.anchor_label} level "
                f"{setup.anchor_level:.2f} is "
                f"{abs(entry - setup.anchor_level):.2f} from price "
                f"(> {STALE_ANCHOR_ATR_MULT:.0f}x ATR {atr5:.2f})",
                waiting=waiting, plan=plan)

        # Counter-trend stand-down: fading a UNANIMOUS H1/M15/M5 consensus
        # requires the candidate's own displacement footprint.
        opposing = Bias.BULLISH if trade_dir is Direction.SHORT else Bias.BEARISH
        if all(b is opposing for b in (mtf.h1, mtf.m15, mtf.m5)):
            own_footprint = (disp_direction is trade_dir
                             and displacement >= CONFLICT_DISPLACEMENT)
            if not own_footprint and posture != Posture.LIQUIDITY_REVERSAL:
                return self._wait(
                    context, ch,
                    f"COUNTER_TREND_NO_DISPLACEMENT: H1/M15/M5 all "
                    f"{opposing.value} and the {trade_dir.value} thesis shows "
                    f"no displacement footprint (disp {displacement:.1f}x) — "
                    "fading a unanimous consensus needs a fresh impulse",
                    waiting="SWEEP",
                    plan="wait for a sweep+rejection impulse in the candidate "
                         "direction or for HTF/LTF realignment")

        stop_price = setup.stop_price
        self._fill_stop_output(ch, setup, trade_dir)

        # H8 zone-consumption guard.
        consumed_block = self._consumed_stop_block(
            trade_dir, stop_price, atr5, now)
        if consumed_block:
            return self._wait(context, ch, consumed_block,
                              waiting="LOCAL_SWING",
                              plan="wait for structure beyond the consumed "
                                   "level or for it to go stale (30 min)")

        # -- quality score + grade ------------------------------------------
        quality, quality_detail = self._quality_score(
            posture, trade_dir, in_killzone, setup, displacement, mtf,
            orderflow, liquidity_context)
        ch["quality"] = f"{quality:.2f} (bar {self._quality_bar:.2f})"
        if quality < self._quality_bar:
            waiting, plan = self._reentry_plan(trade_dir, zones)
            return self._wait(
                context, ch,
                f"QUALITY_BELOW_BAR: score {quality:.2f} < "
                f"{self._quality_bar:.2f} — {quality_detail}; "
                "waiting for a higher-quality alignment",
                waiting=waiting, plan=plan)
        grade = Grade.STRONG if quality >= self._strong_bar else Grade.NORMAL
        ch["grade"] = grade

        tier_lot = TIER_LOT_STRONG if grade == Grade.STRONG else TIER_LOT_NORMAL
        if grade == Grade.STRONG and session in _LOW_LIQUIDITY_SESSIONS:
            tier_lot = TIER_LOT_NORMAL  # low-liquidity demotes the risk tier
        risk_pct = 0.015 if tier_lot == TIER_LOT_STRONG else 0.010
        budget_usd = equity * risk_pct
        eff_stop = setup.stop_distance + spread
        est_lot = max(int(budget_usd / (100.0 * eff_stop) / 0.01) * 0.01, 0.01)
        ch["lot_decision"] = (
            f"~{est_lot:.2f} (tier {tier_lot:.2f} = {risk_pct:.1%} equity risk)")
        risk_usd = min(budget_usd, est_lot * 100.0 * eff_stop)
        ch["risk_if_sl_hit"] = round(risk_usd, 2)

        decision = self._build_decision(
            inp.symbol, now, trade_dir, entry, setup, grade, tier_lot,
            posture, liquidity_context)
        confidence = self._confidence(grade, setup)
        ch["reason"] = (
            f"{posture}/{grade} {trade_dir.value}: anchor={setup.anchor_label} "
            f"({setup.anchor_detail}); trigger={setup.trigger}; "
            f"liquidity={liquidity_context}; stop={setup.stop_source}@"
            f"{stop_price:.2f} ({setup.stop_distance:.2f}); target "
            f"{setup.target_r:.1f}R; quality {quality:.2f}")

        verdict = self._governor.evaluate(decision, RiskContext(
            broker=inp.broker,
            current_spread=spread,
            lot_size=tier_lot,
            intended_risk_pct=risk_usd / equity if equity else 0.0,
            daily_loss_pct=inp.daily_loss_pct,
            weekly_loss_pct=inp.weekly_loss_pct,
            trades_today=inp.trades_today,
            consecutive_losses=inp.consecutive_losses,
            open_symbols=inp.open_symbols,
            size_factor_hint=1.0,
            protected_addon=inp.broker.open_positions > 0,
        ))
        return PipelineResult(
            stage=PipelineStage.RISK_EVALUATED,
            approved=verdict.approved,
            reason="; ".join(verdict.reasons),
            decision=decision,
            confidence=confidence,
            risk=verdict,
            context=context,
            lot_size=tier_lot,
        )

    # -- posture classification ------------------------------------------------
    def _classify_posture(
        self, candidate, mtf, displacement, disp_direction, m5, sweeps,
        chop, price_zone,
    ) -> Tuple[str, Optional[Direction], Optional[Direction]]:
        """Returns (posture, reversal_direction, range_direction)."""
        last = m5[-1]

        # 1) LIQUIDITY_REVERSAL: an aligned fresh TRUE_SWEEP that has been
        #    RECLAIMED (price closed back on the favorable side of the swept
        #    level and held). This is the highest-quality SMC entry.
        for want, rdir in ((Bias.BULLISH, Direction.LONG),
                            (Bias.BEARISH, Direction.SHORT)):
            sweep = self._fresh_reclaimed_sweep(want, m5, sweeps)
            if sweep is not None:
                return Posture.LIQUIDITY_REVERSAL, rdir, None

        # 2) TREND: HTF+LTF aligned with a real impulse footprint -> trade
        #    continuation pullbacks WITH the trend.
        if candidate is not None:
            want = Bias.BULLISH if candidate is Direction.LONG else Bias.BEARISH
            unanimous = all(b is want for b in (mtf.h1, mtf.m15, mtf.m5))
            strong_score = (mtf.score >= 0.60 and disp_direction is candidate
                            and displacement >= ANCHOR_DISPLACEMENT)
            if unanimous or strong_score:
                return Posture.TREND, None, None

        # 3) RANGE_SCALP: a tradeable range (chop subtype that carries a
        #    sweep) AND price parked at a premium/discount extreme -> fade the
        #    extreme back toward equilibrium.
        tradeable_range = chop.subtype in (
            ChopSubtype.LIQUIDITY_CHOP_WITH_SWEEP,
            ChopSubtype.TRAP_REVERSAL_FROM_CHOP,
        )
        if tradeable_range and price_zone is not None:
            if price_zone is PriceZone.DISCOUNT:
                return Posture.RANGE_SCALP, None, Direction.LONG
            if price_zone is PriceZone.PREMIUM:
                return Posture.RANGE_SCALP, None, Direction.SHORT

        return Posture.WAIT, None, None

    def _fresh_reclaimed_sweep(self, want: Bias, m5, sweeps):
        """The most recent aligned TRUE_SWEEP whose reclaim held: price closed
        back beyond the swept level on the favorable side for _RECLAIM_HOLD
        candles. Returns the sweep event or None."""
        aligned = [s for s in sweeps
                   if s.status is SweepStatus.TRUE_SWEEP
                   and s.rejection_bias is want
                   and 0 <= s.sweep_index < len(m5)
                   and s.sweep_index >= len(m5) - _RECENT_EVENT_WINDOW]
        for s in sorted(aligned, key=lambda x: x.sweep_index, reverse=True):
            level = s.level.price
            after = m5[s.sweep_index + 1:]
            if len(after) < _RECLAIM_HOLD:
                # the sweep candle itself rejected; require its close reclaimed
                after = m5[s.sweep_index:]
            held = all(
                (c.close > level if want is Bias.BULLISH else c.close < level)
                for c in after[-_RECLAIM_HOLD:]
            ) if after else False
            if held:
                return s
        return None

    # -- setup resolution ------------------------------------------------------
    def _resolve_setup(
        self, posture, trade_dir, entry, m5, m1, atr5, spread, structure,
        sweeps, zones, liquidity_map, displacement, disp_direction,
    ) -> Optional[_Setup]:
        short = trade_dir is Direction.SHORT
        want = Bias.BULLISH if trade_dir is Direction.LONG else Bias.BEARISH

        if posture == Posture.LIQUIDITY_REVERSAL:
            sweep = self._fresh_reclaimed_sweep(want, m5, sweeps)
            if sweep is None:
                return None
            extreme = (m5[sweep.sweep_index].high if short
                       else m5[sweep.sweep_index].low)
            stop = self._protect_stop_from_pool(
                trade_dir, entry, extreme, atr5, spread, liquidity_map)
            if stop is None:
                return None
            stop_price, stop_distance = stop
            return _Setup(
                posture=posture, direction=trade_dir,
                anchor_label="SWEEP_RECLAIM", anchor_level=sweep.level.price,
                anchor_detail=f"{sweep.swept_side.value} swept @"
                              f"{sweep.level.price:.2f} reclaimed @{extreme:.2f}",
                trigger="RECLAIM_HOLD",
                stop_price=stop_price, stop_distance=stop_distance,
                stop_source="rejection_extreme",
                stop_logic=f"beyond the swept rejection extreme {extreme:.2f} "
                           "(past the hunted pool)",
                target_r=2.0)

        if posture == Posture.TREND:
            # continuation pullback into an aligned FVG / OB.
            for kind, label in ((ZoneKind.FAIR_VALUE_GAP, "FVG_RETEST"),
                                (ZoneKind.ORDER_BLOCK, "OB_RETEST")):
                zone = self._retested_zone(trade_dir, m5, zones, kind)
                if zone is None:
                    continue
                if not self._directional_close(m5[-1], trade_dir):
                    continue
                base = zone.top if short else zone.bottom
                stop = self._protect_stop_from_pool(
                    trade_dir, entry, base, atr5, spread, liquidity_map)
                if stop is None:
                    continue
                stop_price, stop_distance = stop
                return _Setup(
                    posture=posture, direction=trade_dir,
                    anchor_label=label, anchor_level=(zone.top + zone.bottom) / 2,
                    anchor_detail=f"{kind.value} {zone.bottom:.2f}-{zone.top:.2f} "
                                  "mitigated with the trend",
                    trigger="MITIGATION_REJECTION",
                    stop_price=stop_price, stop_distance=stop_distance,
                    stop_source=("FVG_boundary" if kind is
                                 ZoneKind.FAIR_VALUE_GAP else "OB_boundary"),
                    stop_logic=f"beyond the {kind.value} far boundary "
                               f"{base:.2f}",
                    target_r=3.0)
            # break & retest continuation.
            level = self._break_retest_level(trade_dir, m5, structure, atr5)
            if level is not None and self._directional_close(m5[-1], trade_dir):
                pivot = self._latest_pivot(m5, short=short, beyond=entry)
                base = pivot if pivot is not None else level
                stop = self._protect_stop_from_pool(
                    trade_dir, entry, base, atr5, spread, liquidity_map)
                if stop is not None:
                    stop_price, stop_distance = stop
                    return _Setup(
                        posture=posture, direction=trade_dir,
                        anchor_label="BREAK_RETEST", anchor_level=level,
                        anchor_detail=f"broken level {level:.2f} retested",
                        trigger="BREAK_RETEST",
                        stop_price=stop_price, stop_distance=stop_distance,
                        stop_source="local_swing",
                        stop_logic=f"beyond the local swing {base:.2f}",
                        target_r=3.0)
            return None

        if posture == Posture.RANGE_SCALP:
            # fade the extreme only after a boundary sweep rejected.
            sweep = self._fresh_reclaimed_sweep(want, m5, sweeps)
            base_extreme = None
            if sweep is not None:
                base_extreme = (m5[sweep.sweep_index].high if short
                                else m5[sweep.sweep_index].low)
            else:
                pivot = self._latest_pivot(m5, short=short, beyond=entry)
                base_extreme = pivot
            if base_extreme is None:
                return None
            if not self._directional_close(m5[-1], trade_dir):
                return None
            stop = self._protect_stop_from_pool(
                trade_dir, entry, base_extreme, atr5, spread, liquidity_map)
            if stop is None:
                return None
            stop_price, stop_distance = stop
            return _Setup(
                posture=posture, direction=trade_dir,
                anchor_label="RANGE_FADE", anchor_level=base_extreme,
                anchor_detail=f"range extreme {base_extreme:.2f} rejected",
                trigger="BOUNDARY_REJECTION",
                stop_price=stop_price, stop_distance=stop_distance,
                stop_source="rejection_extreme",
                stop_logic=f"beyond the range extreme {base_extreme:.2f}",
                target_r=1.5)
        return None

    # -- the protected-stop doctrine ------------------------------------------
    def _protect_stop_from_pool(
        self, trade_dir, entry, base_level, atr5, spread, liquidity_map,
    ) -> Optional[Tuple[float, float]]:
        """Place the stop BEYOND `base_level` plus a buffer, then push it past
        any resting liquidity pool it would otherwise sit at/inside — the
        market hunts those pools. Returns (stop_price, distance) within the
        hard stop bounds, or None if no protected stop fits (caller WAITs)."""
        short = trade_dir is Direction.SHORT
        buffer = max(0.25 * atr5, 2.0 * spread, 0.30)
        # base must be a real invalidation on the correct side of entry.
        if short and base_level <= entry:
            return None
        if not short and base_level >= entry:
            return None
        stop = base_level + buffer if short else base_level - buffer

        # Pool guard: a resting pool between entry and the stop (or just past
        # the base) is exactly where stops get swept — clear it.
        pools = liquidity_map.buy_side() if short else liquidity_map.sell_side()
        for lvl in pools:
            p = lvl.price
            if short and entry < p <= stop + buffer:
                stop = max(stop, p + buffer)
            elif not short and stop - buffer <= p < entry:
                stop = min(stop, p - buffer)

        distance = (stop - entry) if short else (entry - stop)
        if distance < MIN_STOP_DISTANCE:
            distance = MIN_STOP_DISTANCE
            stop = entry + distance if short else entry - distance
        max_distance = min(MAX_STOP_ABSOLUTE, max(3.0, 3.0 * atr5))
        if distance > max_distance:
            return None  # too wide to protect within budget -> caller WAITs
        return round(stop, 2), round(distance, 2)

    # -- zone / structure helpers ---------------------------------------------
    @staticmethod
    def _retested_zone(trade_dir, m5, zones, kind) -> Optional[Zone]:
        want = Bias.BULLISH if trade_dir is Direction.LONG else Bias.BEARISH
        last = m5[-1]
        recent = list(m5[-_ZONE_TOUCH_WINDOW:])
        candidates = [
            z for z in zones
            if z.kind is kind and z.bias is want
            and any(c.low <= z.top and c.high >= z.bottom for c in recent)
        ]
        for zone in sorted(candidates, key=lambda z: z.created_index,
                           reverse=True):
            if trade_dir is Direction.LONG and last.close > zone.top:
                return zone
            if trade_dir is Direction.SHORT and last.close < zone.bottom:
                return zone
        return None

    @staticmethod
    def _break_retest_level(trade_dir, m5, structure, atr5) -> Optional[float]:
        want = Bias.BULLISH if trade_dir is Direction.LONG else Bias.BEARISH
        tolerance = max(0.30, 0.25 * atr5)
        last = m5[-1]
        for ev in reversed(structure.events):
            if ev.bias is not want or ev.event_type is not StructureEventType.BOS:
                continue
            if ev.index < len(m5) - _RECENT_EVENT_WINDOW:
                break
            after = m5[ev.index + 1:]
            if not after:
                continue
            level = ev.price
            if trade_dir is Direction.LONG:
                if any(c.low <= level + tolerance for c in after) \
                        and last.close > level:
                    return level
            else:
                if any(c.high >= level - tolerance for c in after) \
                        and last.close < level:
                    return level
        return None

    @staticmethod
    def _latest_pivot(candles, *, short, beyond, k=2, lookback=40) -> Optional[float]:
        cs = list(candles)[-lookback:]
        for i in range(len(cs) - k - 1, k - 1, -1):
            window = cs[i - k:i + k + 1]
            if short:
                level = cs[i].high
                if level >= max(c.high for c in window) and level > beyond:
                    return level
            else:
                level = cs[i].low
                if level <= min(c.low for c in window) and level < beyond:
                    return level
        return None

    @staticmethod
    def _directional_close(candle: Candle, trade_dir: Direction) -> bool:
        return (candle.close > candle.open if trade_dir is Direction.LONG
                else candle.close < candle.open)

    # -- quality scoring -------------------------------------------------------
    def _quality_score(
        self, posture, trade_dir, in_killzone, setup, displacement, mtf,
        orderflow, liquidity_context,
    ) -> Tuple[float, str]:
        """Fixed-weight quality score in [0, 1]. Components: narrative/posture
        quality, liquidity-event quality, structure freshness, stop quality
        (beyond an engineered extreme), session timing, orderflow agreement."""
        want = Bias.BULLISH if trade_dir is Direction.LONG else Bias.BEARISH
        gaps: List[str] = []

        posture_w = {Posture.TREND: 0.24, Posture.LIQUIDITY_REVERSAL: 0.24,
                     Posture.RANGE_SCALP: 0.14}.get(posture, 0.0)

        # liquidity-event quality
        liq = 0.0
        if liquidity_context in ("ASIAN_LOW_SWEEP", "ASIAN_HIGH_SWEEP",
                                 "SESSION_LIQUIDITY"):
            liq = 0.20
        elif liquidity_context == "LIQUIDITY_TARGET_AHEAD":
            liq = 0.10
        else:
            gaps.append("no fresh liquidity event")

        # structure freshness / stop quality (engineered-extreme stops score)
        stop_q = 0.20 if setup.stop_source in (
            "rejection_extreme", "FVG_boundary", "OB_boundary") else 0.12

        # session timing
        timing = 0.16 if in_killzone else 0.04
        if not in_killzone:
            gaps.append("outside a kill zone")

        # MTF alignment magnitude
        mtf_q = min(max(mtf.score, 0.0), 1.0) * 0.10

        # orderflow agreement (proxy only — small weight, never a trigger)
        flow_q = 0.0
        if (orderflow.pressure is ProxyPressure.BULLISH and want is Bias.BULLISH) \
                or (orderflow.pressure is ProxyPressure.BEARISH
                    and want is Bias.BEARISH):
            flow_q = 0.06

        score = posture_w + liq + stop_q + timing + mtf_q + flow_q
        score = round(min(score, 1.0), 3)
        detail = (f"posture={posture_w:.2f} liq={liq:.2f} stop={stop_q:.2f} "
                  f"timing={timing:.2f} mtf={mtf_q:.2f} flow={flow_q:.2f}"
                  + ("; missing: " + ", ".join(gaps) if gaps else ""))
        return score, detail

    # -- liquidity / session context ------------------------------------------
    @staticmethod
    def _liquidity_context(trade_dir, asian, sweeps, liquidity_map, entry) -> str:
        if asian.known and asian.swept in ("LOW", "BOTH"):
            return "ASIAN_LOW_SWEEP"
        if asian.known and asian.swept == "HIGH":
            return "ASIAN_HIGH_SWEEP"
        if any(s.status is SweepStatus.TRUE_SWEEP for s in sweeps):
            return "SESSION_LIQUIDITY"
        try:
            if trade_dir is Direction.LONG:
                ahead = [l.price for l in liquidity_map.buy_side()
                         if l.price > entry]
            else:
                ahead = [l.price for l in liquidity_map.sell_side()
                         if l.price < entry]
            if ahead:
                return "LIQUIDITY_TARGET_AHEAD"
        except Exception:  # noqa: BLE001 - context labels never crash a cycle
            pass
        return "NONE"

    # -- re-entry planning (anti-freeze) ---------------------------------------
    @staticmethod
    def _reentry_plan(trade_dir, zones, anchor_label: str = "") -> Tuple[str, str]:
        if trade_dir is None:
            return "HTF_DIRECTION", "wait for a higher-timeframe direction"
        want = Bias.BULLISH if trade_dir is Direction.LONG else Bias.BEARISH
        aligned_fvg = [z for z in zones if z.kind is ZoneKind.FAIR_VALUE_GAP
                       and z.bias is want and not z.mitigated]
        aligned_ob = [z for z in zones if z.kind is ZoneKind.ORDER_BLOCK
                      and z.bias is want and not z.mitigated]
        if aligned_fvg:
            z = aligned_fvg[-1]
            return "FVG_RETEST", (
                f"wait for mitigation of the {want.value.lower()} FVG "
                f"{z.bottom:.2f}-{z.top:.2f}")
        if aligned_ob:
            z = aligned_ob[-1]
            return "OB_RETEST", (
                f"wait for a retest of the {want.value.lower()} order block "
                f"{z.bottom:.2f}-{z.top:.2f}")
        return "SWEEP", (
            "wait for a liquidity sweep + reclaim or a fresh BOS/CHOCH in the "
            f"{trade_dir.value} direction")

    # -- H8 consumed-stop guard ------------------------------------------------
    def _consumed_stop_block(self, trade_dir, stop_price, atr5, now) -> str:
        consumed = self._consumed_stops.get(trade_dir)
        if consumed is None:
            return ""
        level, when = consumed
        try:
            expired = (when is None or now is None
                       or (now - when) > CONSUMED_STOP_TTL)
        except TypeError:
            expired = True
        if expired:
            self._consumed_stops.pop(trade_dir, None)
            return ""
        if abs(stop_price - level) > CONSUMED_STOP_PROXIMITY:
            return ""
        clearance = max(1.0, min(atr5, CONSUMED_STOP_CLEARANCE_CAP))
        cleared = (stop_price > level + clearance if trade_dir is Direction.SHORT
                   else stop_price < level - clearance)
        if cleared:
            return ""
        need = (level + clearance if trade_dir is Direction.SHORT
                else level - clearance)
        minutes = int(CONSUMED_STOP_TTL.total_seconds() // 60)
        return (f"ZONE_CONSUMED: a {trade_dir.value} stop at {level:.2f} was "
                f"swept within the last {minutes} min and the new stop "
                f"{stop_price:.2f} does not clear it (need beyond {need:.2f})")

    # -- decision assembly -----------------------------------------------------
    def _build_decision(self, symbol, now, trade_dir, entry, setup, grade,
                        tier_lot, posture, liquidity_context) -> TradeDecision:
        target = (entry - setup.target_r * setup.stop_distance
                  if trade_dir is Direction.SHORT
                  else entry + setup.target_r * setup.stop_distance)
        return TradeDecision(
            decision_id=f"liqint-{now.strftime('%Y%m%dT%H%M%S')}Z",
            time_utc=now,
            symbol=symbol,
            direction=trade_dir,
            status=DecisionStatus.PROPOSED,
            setup_type=SETUP_TYPE_TEMPLATE.format(
                posture=posture.lower(), grade=grade, lot=tier_lot),
            thesis=(f"liquidity_intel {posture}/{grade} {trade_dir.value}: "
                    f"{setup.anchor_label} ({setup.anchor_detail}); trigger "
                    f"{setup.trigger}; liquidity {liquidity_context}; "
                    "protected tactical invalidation"),
            invalidation_price=setup.stop_price,
            entry_price=entry,
            stop_loss=setup.stop_price,
            take_profits=(round(target, 2),),
            confidence=0.80 if grade == Grade.STRONG else 0.65,
            uncertainty=0.20 if grade == Grade.STRONG else 0.30,
            reason=f"{posture}/{grade} {setup.anchor_label} via {setup.trigger}")

    @staticmethod
    def _confidence(grade, setup) -> ConfidenceResult:
        strong = grade == Grade.STRONG
        return ConfidenceResult(
            confidence=0.80 if strong else 0.65,
            uncertainty=0.20 if strong else 0.30,
            recommendation=ScoreRecommendation.ALLOW,
            size_factor=1.0,
            reason=f"liquidity_intel {grade}: {setup.anchor_label} via "
                   f"{setup.trigger}")

    # -- terminal output assembly ----------------------------------------------
    def _base_output(self, session, in_killzone, candidate, displacement,
                     structure, zones, liquidity_map, sweeps, price_zone,
                     orderflow, entry) -> dict:
        bos_choch = [ev for ev in structure.events
                     if ev.index >= len(structure.events) - _RECENT_EVENT_WINDOW]
        last_event = (structure.events[-1].event_type.value
                      if structure.events else "NONE")
        fvg = sum(1 for z in zones
                  if z.kind is ZoneKind.FAIR_VALUE_GAP and not z.mitigated)
        ob = sum(1 for z in zones
                 if z.kind is ZoneKind.ORDER_BLOCK and not z.mitigated)
        true_sweeps = [s for s in sweeps if s.status is SweepStatus.TRUE_SWEEP]
        buy_pools = len(liquidity_map.buy_side())
        sell_pools = len(liquidity_map.sell_side())
        equal = sum(1 for l in (liquidity_map.buy_side()
                                + liquidity_map.sell_side())
                    if l.kind in (LiquidityKind.EQUAL_HIGHS,
                                  LiquidityKind.EQUAL_LOWS))
        return {
            "mode": PROFILE_NAME,
            "profile": PROFILE_NAME,
            "fresh_entry_scan": "ACTIVE",
            "new_candle_detected": "no",
            "local_structure_updated": "no",
            "direction": candidate.value if candidate else "NONE",
            "posture": Posture.WAIT,
            "narrative": "",
            "grade": "NONE",
            "quality": "-",
            "htf_context": "",
            "killzone": (session.value if in_killzone
                         else f"LOW_LIQUIDITY({session.value})"
                         if session in _LOW_LIQUIDITY_SESSIONS
                         else session.value),
            "liquidity_context": "NONE",
            "liquidity_map": (f"buy_side={buy_pools} sell_side={sell_pools} "
                              f"equal_hl={equal}"),
            "sweep_status": (f"true_sweeps={len(true_sweeps)}"
                             + (f" last={true_sweeps[-1].swept_side.value}"
                                f"@{true_sweeps[-1].level.price:.2f}"
                                if true_sweeps else "")),
            "structure_state": f"bias={structure.final_bias.value} "
                               f"last_event={last_event}",
            "fvg_ob_status": f"fvg_open={fvg} ob_open={ob}",
            "orderflow": (f"{orderflow.pressure.value}/"
                          f"{orderflow.volume_state.value} "
                          f"vol_ratio={orderflow.volume_ratio:.2f}"),
            "premium_discount": price_zone.value if price_zone else "UNKNOWN",
            "smc_anchor": "NONE",
            "entry_trigger": "NONE",
            "tactical_stop_price": None,
            "tactical_stop_distance": None,
            "tactical_stop_source": "none",
            "stop_logic": "",
            "invalidation_reason": "",
            "risk_if_sl_hit": None,
            "sl_tp_trail": "",
            "lot_decision": "NONE",
            "displacement": round(displacement, 2),
            "reentry_plan": "",
            "waiting_for": "",
            "reason": "",
        }

    def _fill_stop_output(self, ch: dict, setup: _Setup, trade_dir) -> None:
        if self._last_stop_price != setup.stop_price:
            ch["local_structure_updated"] = "yes"
            self._last_stop_price = setup.stop_price
        target = (setup.stop_price)  # placeholder; real TP in decision
        ch.update(
            tactical_stop_price=round(setup.stop_price, 2),
            tactical_stop_distance=round(setup.stop_distance, 2),
            tactical_stop_source=setup.stop_source,
            stop_logic=f"{setup.stop_logic} (protected: SL sits beyond the "
                       "engineered liquidity, not at the pool)",
            invalidation_reason=(
                f"{trade_dir.value} thesis invalid beyond "
                f"{setup.stop_price:.2f} ({setup.stop_source}: "
                f"{setup.anchor_label} setup broken)"),
            sl_tp_trail=(f"SL {setup.stop_price:.2f} / target {setup.target_r:.1f}R"
                         " / trail to break-even at +1R then ATR-trail"),
        )

    @staticmethod
    def _narrative(posture, candidate, mtf, price_zone) -> str:
        d = candidate.value if candidate else "no-direction"
        pz = price_zone.value if price_zone else "?"
        return (f"{posture}: bias={d} mtf={mtf.score:.2f} zone={pz}")

    # -- context / wait / flat -------------------------------------------------
    def _context(self, session, htf_bias, structure_bias, candidate,
                 price_zone, displacement, ch) -> PipelineContext:
        return PipelineContext(
            session=session,
            htf_bias=htf_bias,
            regime=Regime.TREND if candidate is not None else Regime.RANGE,
            structure_bias=structure_bias,
            has_setup=candidate is not None,
            regime_reason="liquidity_intel posture evaluation",
            price_zone=price_zone,
            displacement_ratio=displacement,
            challenge=ch)

    def _wait(self, context, ch, reason, *, waiting="", plan="") -> PipelineResult:
        ch["reason"] = reason
        ch["waiting_for"] = waiting
        ch["reentry_plan"] = plan or ch.get("reentry_plan", "")
        return PipelineResult(stage=PipelineStage.HYPOTHESIS, approved=False,
                              reason=reason, context=context)

    def _flat(self, context, ch, reason, *, waiting="", plan="") -> PipelineResult:
        ch["posture"] = Posture.FLAT
        return self._wait(context, ch, reason, waiting=waiting, plan=plan)

    # -- shared math -----------------------------------------------------------
    def _htf_bias(self, daily, h4) -> HtfBias:
        try:
            return self._e.htf.classify(daily, h4).bias
        except Exception:  # noqa: BLE001 - missing HTF data reads NEUTRAL
            return HtfBias.NEUTRAL

    @staticmethod
    def _htf_direction(htf: HtfBias) -> Optional[Direction]:
        if htf is HtfBias.BULLISH:
            return Direction.LONG
        if htf is HtfBias.BEARISH:
            return Direction.SHORT
        return None

    @staticmethod
    def _b(bias) -> str:
        return bias.value if bias is not None else "-"

    @staticmethod
    def _dirlabel(candidate) -> str:
        return candidate.value if candidate else "NONE"

    @staticmethod
    def _m1_state(m1) -> Optional[str]:
        if not m1 or len(m1) < 3:
            return None
        last = list(m1)[-3:]
        net = last[-1].close - last[0].open
        threshold = 0.1 * sum(c.high - c.low for c in last) / 3
        if net > threshold:
            return "BULLISH"
        if net < -threshold:
            return "BEARISH"
        return "FLAT"

    @staticmethod
    def _displacement(candles, body_window=8, range_window=20):
        recent = list(candles[-range_window:])
        if len(recent) < 5:
            return 0.0, None
        ranges = sorted(c.high - c.low for c in recent)
        median = ranges[len(ranges) // 2]
        if median <= 0:
            return 0.0, None
        bodies = list(candles[-body_window:])
        biggest = max(bodies, key=lambda c: abs(c.close - c.open))
        ratio = abs(biggest.close - biggest.open) / median
        direction = (Direction.LONG if biggest.close > biggest.open
                     else Direction.SHORT if biggest.close < biggest.open
                     else None)
        return ratio, direction

    def _detect_new_candle(self, m5, m1) -> str:
        m5_time = m5[-1].time_utc if m5 else None
        m1_time = m1[-1].time_utc if m1 else None
        fresh = ((m5_time is not None and m5_time != self._last_m5_time)
                 or (m1_time is not None and m1_time != self._last_m1_time))
        first = self._last_m5_time is None and self._last_m1_time is None
        self._last_m5_time = m5_time
        self._last_m1_time = m1_time
        if first:
            return "first_cycle"
        return "yes" if fresh else "no"

    @staticmethod
    def _aggregate(m5, target) -> List[Candle]:
        try:
            return list(aggregate(m5, target))
        except (AggregationError, ValueError):
            return []

    @staticmethod
    def _atr(candles, period=14) -> float:
        window = list(candles[-period:])
        if not window:
            return 0.0
        return sum(c.high - c.low for c in window) / len(window)


def make_liquidity_intel_pipeline(
    canonical_symbol: str,
    *,
    max_spread_price: float = 1.0,
    quality_bar: float = DEFAULT_QUALITY_BAR,
    strong_bar: float = DEFAULT_STRONG_BAR,
    max_staleness: timedelta = timedelta(minutes=30),
) -> LiquidityIntelEngine:
    """Build the single liquidity_intel decision engine for LIVE XAUUSDm."""
    canonical = canonical_symbol.strip().upper()
    engines = IntelEngines(
        validator=DataValidator(ValidationConfig(
            expected_symbol=canonical,
            detect_gaps=False,
            max_staleness=max_staleness,
        )),
    )
    return LiquidityIntelEngine(
        make_intel_limits(canonical),
        max_spread=max_spread_price,
        quality_bar=quality_bar,
        strong_bar=strong_bar,
        engines=engines,
    )
