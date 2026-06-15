"""GoldAlpha — the single XAU/USD profit-maximisation engine (GOLD-ALPHA-001).

One model, one profile (`gold_alpha`), built from scratch around an explicit
EXPECTED-VALUE objective rather than a fixed gate chain or a fixed cadence.

Each cycle it reads the full multi-timeframe picture (reusing the proven SMC
analytics primitives), enumerates every setup actually present, scores each by
expected R, and trades the best one when its edge clears the bar — aggressively
when the edge is strong, flat when there is none. It places the stop on real
invalidation BEYOND the engineered liquidity (never where gold hunts the
obvious pool), targets the opposing draw on liquidity, trails to protect
winners, and exits fast when the thesis breaks. Every closed trade is
attributed (WHY it won/lost) and that evidence down-weights failing setups
before the next decision (src/strategy/trade_attribution.py).

decide(PipelineInput) -> PipelineResult is the same contract the chassis drives
(SupervisedDemoSession / TradingService / ExecutionGateway unchanged). This
module sends no orders and holds no credentials; the gateway is the only order
pathway and the RiskGovernor has final authority.
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
from src.strategy.trade_attribution import (
    LossReason,
    PerformanceStore,
    TradeContext,
    classify_outcome,
)
from src.structure.market_structure import (
    Bias,
    MarketStructureEngine,
    StructureEventType,
    StructureResult,
)
from src.structure.premium_discount import PremiumDiscountEngine, PriceZone
from src.structure.zones import Zone, ZoneEngine, ZoneKind

PROFILE_NAME = "gold_alpha"

# Stop geometry (local invalidation, never a wide HTF structural stop).
MIN_STOP_DISTANCE = 0.50
MAX_STOP_ABSOLUTE = 9.0
REJECTION_WICK_RATIO = 0.40
ANCHOR_DISPLACEMENT = 1.3
STRONG_DISPLACEMENT = 1.6
STALE_ANCHOR_ATR_MULT = 10.0
_RECENT_EVENT_WINDOW = 40
_ZONE_TOUCH_WINDOW = 3
_RECLAIM_HOLD = 1

# Objective thresholds (tuned ONLY by replay evidence, never live).
EV_BAR = 0.15          # minimum expected R to take a trade
EV_STRONG = 0.55       # >= this EV sizes up (STRONG tier)
P_WIN_MIN = 0.30       # never trade below this estimated hit-rate
TARGET_R_CAP = 5.0     # cap reward estimate (sanity)

# Risk TIER lots carried in setup_type (parsed by the planner -> equity risk%).
TIER_LOT_NORMAL = 0.05
TIER_LOT_STRONG = 0.10
SETUP_TYPE_TEMPLATE = "gold_{setup}[{grade},lot={lot:.2f}]"

# Exit model.
BE_TRIGGER_R = 1.0     # arm break-even at +1R
TRAIL_ATR_MULT = 1.5   # trail this many M5-ATR behind once running

CONSUMED_STOP_TTL = timedelta(minutes=30)

_KILL_ZONES = {
    SessionType.LONDON, SessionType.NEW_YORK, SessionType.LONDON_NY_OVERLAP,
}
_LOW_LIQUIDITY_SESSIONS = {
    SessionType.ROLLOVER, SessionType.LOW_LIQUIDITY, SessionType.CLOSED,
}


def make_gold_limits(expected_symbol: str) -> RiskLimits:
    """The single gold_alpha risk envelope (DEMO, growth-oriented): per-trade
    cap 6%, daily/weekly circuit-breakers OFF (1.0), no artificial trade/open
    caps (the EV bar governs cadence), spread <= 1.0. Structural safety
    (mandatory SL, no martingale, MT5 truth, kill switch) is enforced by the
    planner/gateway/governor, not here."""
    return RiskLimits(
        expected_symbol=expected_symbol,
        max_risk_per_trade=0.06,
        max_daily_loss=1.0,
        max_weekly_loss=1.0,
        max_trades_per_day=1000,
        max_open_trades=5,
        max_spread=1.0,
    )


@dataclass
class GoldEngines:
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
        default_factory=PremiumDiscountEngine)
    volatility: VolatilityClassifier = field(default_factory=VolatilityClassifier)
    chop: ChopClassifier = field(default_factory=ChopClassifier)
    orderflow: OrderFlowProxyEngine = field(default_factory=OrderFlowProxyEngine)


@dataclass(frozen=True)
class Candidate:
    setup: str            # SWEEP_RECLAIM / TREND_CONTINUATION / RANGE_FADE / BOS_RETEST
    direction: Direction
    entry: float
    stop: float
    stop_distance: float
    stop_source: str
    stop_beyond_pool: bool
    target: float
    anchor_level: Optional[float]
    trigger: str
    confirmation: float   # 0..1
    detail: str


class GoldAlphaEngine:
    """Expected-value, evidence-scored XAU/USD engine. decide() contract."""

    def __init__(
        self,
        limits: RiskLimits,
        *,
        max_spread: float = 1.0,
        ev_bar: float = EV_BAR,
        engines: Optional[GoldEngines] = None,
    ) -> None:
        if max_spread <= 0:
            raise ValueError("max_spread must be > 0")
        self._limits = limits
        self._governor = RiskGovernor(limits)
        self._max_spread = max_spread
        self._ev_bar = ev_bar
        self._e = engines or GoldEngines()
        self.threshold_profile = PROFILE_NAME
        self._last_m5_time = None
        self._last_m1_time = None
        self._perf = PerformanceStore()
        # entry context per direction, for close-time attribution + exit logic.
        self._open_ctx: dict = {}
        self._consumed: dict = {}  # direction -> (level, time)

    # -- learning hooks (called by the session / replay on close) -----------
    def note_stop_loss(self, direction, stop_price, time_utc) -> None:
        """An SL was hit: attribute WHY and feed the performance store so the
        next decision for this setup/regime is down-weighted."""
        if direction is None:
            return
        if stop_price is not None:
            self._consumed[direction] = (float(stop_price), time_utc)
        ctx: Optional[TradeContext] = self._open_ctx.pop(direction, None)
        if ctx is None:
            return
        reason = classify_outcome(ctx, won=False, r_multiple=-1.0)
        self._perf.record(ctx, won=False, r_multiple=-1.0, reason=reason)

    def note_trade_closed(self, direction, r_multiple: float) -> None:
        """A non-SL close (TP / manual / trail). Record the realised R so wins
        and partial outcomes also inform the store."""
        if direction is None:
            return
        ctx: Optional[TradeContext] = self._open_ctx.pop(direction, None)
        if ctx is None:
            return
        won = r_multiple > 0
        reason = classify_outcome(ctx, won=won, r_multiple=r_multiple)
        self._perf.record(ctx, won=won, r_multiple=r_multiple, reason=reason)

    # -- main decision ------------------------------------------------------
    def decide(self, inp: PipelineInput) -> PipelineResult:  # noqa: C901
        e = self._e
        now = inp.now or (
            inp.exec_candles[-1].time_utc if inp.exec_candles else None)
        report = e.validator.validate_candles(inp.exec_candles, now=now)
        if report.status is not ValidationStatus.VALID:
            return PipelineResult(
                stage=PipelineStage.DATA_REJECTED, approved=False,
                reason="data rejected: "
                       f"{[i.code.value for i in report.blocking_issues]}")

        m5 = list(inp.exec_candles)
        m15 = list(inp.m15_candles) if inp.m15_candles else self._agg(m5, Timeframe.M15)
        h1 = list(inp.h1_candles) if inp.h1_candles else self._agg(m5, Timeframe.H1)
        m1 = list(inp.m1_candles) if inp.m1_candles else []
        last = m5[-1]
        entry = last.close
        session = e.session.classify(now)
        in_killzone = session in _KILL_ZONES
        spread = max(inp.current_spread, 0.0)
        spread_ratio = spread / self._max_spread if self._max_spread else 0.0
        equity = inp.broker.equity or inp.broker.balance or 0.0
        atr5 = self._atr(m5)

        structure = e.structure.analyze(m5)
        liq = e.liquidity.build(m5)
        sweeps = e.sweep.detect(m5, liq)
        zones = e.zones.build(m5)
        asian = e.asian.analyze(m5, now)
        dealing = e.premium_discount.range_from_candles(m5)
        price_zone = e.premium_discount.classify(dealing, entry) if dealing else None
        flow = e.orderflow.analyze(m5, structure.final_bias)
        disp, disp_dir = self._displacement(m5)
        htf_bias = self._htf_bias(inp.daily_candles, inp.h4_candles)
        mtf = e.mtf.align(daily=inp.daily_candles, h4=inp.h4_candles, h1=h1,
                          m15=m15, m5_bias=(structure.final_bias
                          if structure.final_bias is not Bias.NEUTRAL else None),
                          m1_state=self._m1_state(m1))

        environment = m5[:-1] if len(m5) > 1 else m5
        vol = e.volatility.classify(environment, spread_ratio=spread_ratio)
        chop = e.chop.classify(environment, sweeps, spread_ratio=spread_ratio,
                               directional_score=mtf.score)
        regime = self._regime(mtf, chop, disp, disp_dir)

        ch = self._base_output(session, in_killzone, mtf, htf_bias, structure,
                               zones, liq, sweeps, price_zone, flow, disp,
                               regime, vol, chop, entry)
        ch["new_candle_detected"] = self._new_candle(m5, m1)
        context = self._context(session, htf_bias, structure.final_bias,
                                price_zone, disp, regime, ch)

        # -- hard environment gates -----------------------------------------
        if spread > self._max_spread:
            return self._wait(context, ch,
                              f"spread too high ({spread:.3f} > "
                              f"{self._max_spread:.3f})", "SPREAD")
        if equity <= 0:
            return self._wait(context, ch, "account equity unknown", "ACCOUNTING")
        if inp.news_risk:
            return self._wait(context, ch,
                              "NEWS_RISK: high-impact window — no new entries",
                              "NEWS")
        if vol.dangerous:
            return self._wait(context, ch,
                              f"VOLATILITY_BLOCK: {vol.state.value} — {vol.reason}",
                              "SWEEP")
        if chop.subtype in (ChopSubtype.DANGEROUS_CHOP,
                            ChopSubtype.LOW_QUALITY_CHOP):
            return self._wait(context, ch,
                              f"CHOP_BLOCK: {chop.subtype.value} — structureless",
                              "SWEEP")

        # -- enumerate + score every candidate present ----------------------
        candidates = self._candidates(
            m5, m1, atr5, spread, structure, sweeps, zones, liq, mtf, disp,
            disp_dir, asian, price_zone, in_killzone, regime)
        scored = []
        for c in candidates:
            p_win, target_r, ev, why = self._score(
                c, mtf, regime, disp, flow, price_zone, in_killzone,
                spread_ratio, inp, equity)
            scored.append((ev, p_win, target_r, c, why))
        scored.sort(key=lambda s: s[0], reverse=True)
        ch["candidates"] = ", ".join(
            f"{c.setup}/{c.direction.value} ev={ev:+.2f}"
            for ev, _, _, c, _ in scored) or "none"

        if not scored:
            waiting, plan = self._rearm(mtf, zones)
            return self._wait(context, ch,
                              f"no setup present in {regime} — {ch['narrative']}",
                              waiting, plan)

        ev, p_win, target_r, best, why = scored[0]
        ch.update(direction=best.direction.value, setup=best.setup,
                  entry_trigger=best.trigger,
                  ev=f"{ev:+.2f} (bar {self._ev_bar:+.2f})",
                  p_win=f"{p_win:.0%}", target_r=f"{target_r:.1f}R",
                  score_detail=why,
                  perf=self._perf.summary(best.setup, regime))

        if ev < self._ev_bar or p_win < P_WIN_MIN:
            waiting, plan = self._rearm(mtf, zones)
            return self._wait(
                context, ch,
                f"EDGE_TOO_THIN: best {best.setup}/{best.direction.value} "
                f"ev={ev:+.2f} (<{self._ev_bar:+.2f}) p_win={p_win:.0%} — "
                f"{why}", waiting, plan)

        # stale-anchor guard
        if (best.anchor_level is not None and atr5 > 0
                and abs(entry - best.anchor_level) > STALE_ANCHOR_ATR_MULT * atr5):
            waiting, plan = self._rearm(mtf, zones)
            return self._wait(context, ch,
                              f"SMC_ANCHOR_STALE: {best.setup} level too far "
                              f"from price", waiting, plan)

        # consumed-zone guard (don't re-fade a just-swept stop)
        cblock = self._consumed_block(best.direction, best.stop, atr5, now)
        if cblock:
            return self._wait(context, ch, cblock, "LOCAL_SWING",
                              "wait for fresh structure beyond the consumed level")

        grade = "STRONG" if ev >= EV_STRONG else "NORMAL"
        tier = TIER_LOT_STRONG if grade == "STRONG" else TIER_LOT_NORMAL
        if grade == "STRONG" and session in _LOW_LIQUIDITY_SESSIONS:
            tier = TIER_LOT_NORMAL
        ch["grade"] = grade
        risk_pct = min(0.06 if tier == TIER_LOT_STRONG else 0.04,
                       self._limits.max_risk_per_trade)
        eff = best.stop_distance + spread
        est_lot = max(int(equity * risk_pct / (100.0 * eff) / 0.01) * 0.01, 0.01)
        ch["lot_decision"] = f"~{est_lot:.2f} ({risk_pct:.0%} equity risk)"
        risk_usd = min(equity * risk_pct, est_lot * 100.0 * eff)
        ch["risk_if_sl_hit"] = round(risk_usd, 2)
        self._fill_stop_output(ch, best)

        decision = self._build_decision(inp.symbol, now, best, grade, tier, ev)
        confidence = ConfidenceResult(
            confidence=min(0.5 + ev, 0.95), uncertainty=max(0.5 - ev, 0.05),
            recommendation=ScoreRecommendation.ALLOW, size_factor=1.0,
            reason=f"gold_alpha {best.setup} ev={ev:+.2f}")
        ch["reason"] = (
            f"{best.setup}/{best.direction.value} ev={ev:+.2f} p_win={p_win:.0%} "
            f"target {target_r:.1f}R; {best.detail}; stop {best.stop_source}@"
            f"{best.stop:.2f} (beyond_pool={best.stop_beyond_pool}); {why}")

        # remember context for close-time attribution + exit management.
        self._open_ctx[best.direction] = TradeContext(
            setup_type=best.setup, regime=regime,
            direction=best.direction.value, entry=best.entry, stop=best.stop,
            target=best.target, score=ev, p_win=p_win, displacement=disp,
            spread_ratio=spread_ratio, confirmation=best.confirmation,
            stop_beyond_pool=best.stop_beyond_pool,
            extended=disp >= STRONG_DISPLACEMENT and abs(entry - (best.anchor_level or entry)) > 3 * atr5)

        verdict = self._governor.evaluate(decision, RiskContext(
            broker=inp.broker, current_spread=spread, lot_size=tier,
            intended_risk_pct=risk_usd / equity if equity else 0.0,
            daily_loss_pct=inp.daily_loss_pct, weekly_loss_pct=inp.weekly_loss_pct,
            trades_today=inp.trades_today, consecutive_losses=inp.consecutive_losses,
            open_symbols=inp.open_symbols, size_factor_hint=1.0,
            protected_addon=inp.broker.open_positions > 0))
        return PipelineResult(
            stage=PipelineStage.RISK_EVALUATED, approved=verdict.approved,
            reason="; ".join(verdict.reasons), decision=decision,
            confidence=confidence, risk=verdict, context=context, lot_size=tier)

    # -- exit model (called by the session for open positions) --------------
    def manage_stop(self, direction: Direction, entry_price: float,
                    current_stop: Optional[float], current_price: float,
                    m5: Sequence[Candle]) -> Optional[float]:
        """Return a TIGHTEN-ONLY new stop, or None. Implements break-even at
        +1R, an ATR/structure trail, and a fast thesis-failure exit (tighten to
        just beyond price when structure flips against the position). Never
        widens a stop; the gateway/session enforce that too."""
        if entry_price is None or current_price is None or not m5:
            return None
        long = direction is Direction.LONG
        ctx = self._open_ctx.get(direction)
        r_dist = abs(entry_price - ctx.stop) if ctx else None
        atr = self._atr(list(m5))
        proposals: List[float] = []

        # break-even once +1R in profit
        if r_dist and r_dist > 0:
            in_profit_r = ((current_price - entry_price) if long
                           else (entry_price - current_price)) / r_dist
            if in_profit_r >= BE_TRIGGER_R:
                proposals.append(entry_price)
                # ATR trail beyond break-even
                trail = (current_price - TRAIL_ATR_MULT * atr if long
                         else current_price + TRAIL_ATR_MULT * atr)
                proposals.append(trail)

        # fast thesis-failure exit: structure flip against the position
        structure = self._e.structure.analyze(list(m5))
        against = Bias.BEARISH if long else Bias.BULLISH
        recent = [ev for ev in structure.events
                  if ev.event_type is StructureEventType.CHOCH
                  and ev.bias is against
                  and ev.index >= len(m5) - 3]
        if recent:
            # tighten to just past current price -> exits on the next adverse tick
            buf = max(0.2 * atr, 0.30)
            proposals.append(current_price - buf if long else current_price + buf)

        if not proposals:
            return None
        # tighten-only: a long's stop may only rise; a short's may only fall.
        if long:
            target = max(proposals)
            if current_stop is not None and target <= current_stop:
                return None
            return round(target, 2)
        target = min(proposals)
        if current_stop is not None and target >= current_stop:
            return None
        return round(target, 2)

    # -- candidate enumeration ----------------------------------------------
    def _candidates(self, m5, m1, atr5, spread, structure, sweeps, zones, liq,
                    mtf, disp, disp_dir, asian, price_zone, in_killzone,
                    regime) -> List[Candidate]:
        out: List[Candidate] = []
        entry = m5[-1].close
        htf_dir = mtf.direction
        for want, d in ((Bias.BULLISH, Direction.LONG),
                        (Bias.BEARISH, Direction.SHORT)):
            # A) sweep + reclaim reversal
            sw = self._reclaimed_sweep(want, m5, sweeps)
            if sw is not None:
                ext = (m5[sw.sweep_index].high if d is Direction.SHORT
                       else m5[sw.sweep_index].low)
                st = self._protect_stop(d, entry, ext, atr5, spread, liq)
                if st:
                    stop, dist, beyond = st
                    tgt = self._target(d, entry, stop, liq)
                    out.append(Candidate(
                        "SWEEP_RECLAIM", d, entry, stop, dist,
                        "rejection_extreme", beyond, tgt, sw.level.price,
                        "RECLAIM_HOLD", 0.85,
                        f"{sw.swept_side.value} swept @{sw.level.price:.2f} "
                        f"reclaimed"))
            # B) trend continuation pullback (only with HTF direction)
            if htf_dir is d:
                for kind, label in ((ZoneKind.FAIR_VALUE_GAP, "FVG"),
                                    (ZoneKind.ORDER_BLOCK, "OB")):
                    z = self._retested_zone(d, m5, zones, kind)
                    if z is None or not self._dir_close(m5[-1], d):
                        continue
                    base = z.top if d is Direction.SHORT else z.bottom
                    st = self._protect_stop(d, entry, base, atr5, spread, liq)
                    if not st:
                        continue
                    stop, dist, beyond = st
                    tgt = self._target(d, entry, stop, liq)
                    out.append(Candidate(
                        "TREND_CONTINUATION", d, entry, stop, dist,
                        f"{label}_boundary", beyond, tgt,
                        (z.top + z.bottom) / 2, "MITIGATION", 0.7,
                        f"{kind.value} {z.bottom:.2f}-{z.top:.2f} mitigated"))
                    break
            # C) range fade at premium/discount extreme after a boundary sweep
            if regime == "RANGE_DAY" and price_zone is not None:
                want_fade = (Direction.LONG if price_zone is PriceZone.DISCOUNT
                             else Direction.SHORT if price_zone is PriceZone.PREMIUM
                             else None)
                if want_fade is d and self._dir_close(m5[-1], d):
                    piv = self._pivot(m5, short=(d is Direction.SHORT), beyond=entry)
                    if piv is not None:
                        st = self._protect_stop(d, entry, piv, atr5, spread, liq)
                        if st:
                            stop, dist, beyond = st
                            tgt = self._target(d, entry, stop, liq, range_fade=True)
                            out.append(Candidate(
                                "RANGE_FADE", d, entry, stop, dist,
                                "rejection_extreme", beyond, tgt, piv,
                                "BOUNDARY_REJECTION", 0.6,
                                f"fade {price_zone.value} extreme {piv:.2f}"))
            # D) BOS + retest / displacement continuation
            lvl = self._break_retest(d, m5, structure, atr5)
            if lvl is not None and self._dir_close(m5[-1], d) and disp_dir is d \
                    and disp >= ANCHOR_DISPLACEMENT:
                piv = self._pivot(m5, short=(d is Direction.SHORT), beyond=entry)
                base = piv if piv is not None else lvl
                st = self._protect_stop(d, entry, base, atr5, spread, liq)
                if st:
                    stop, dist, beyond = st
                    tgt = self._target(d, entry, stop, liq)
                    out.append(Candidate(
                        "BOS_RETEST", d, entry, stop, dist, "local_swing",
                        beyond, tgt, lvl, "BREAK_RETEST", 0.65,
                        f"BOS {lvl:.2f} retest, disp {disp:.1f}x"))
        return out

    # -- the EV objective ---------------------------------------------------
    def _score(self, c: Candidate, mtf, regime, disp, flow, price_zone,
               in_killzone, spread_ratio, inp, equity) -> Tuple[float, float, float, str]:
        want = Bias.BULLISH if c.direction is Direction.LONG else Bias.BEARISH
        parts = []
        p = 0.30  # base hit-rate prior
        # probability of move: MTF alignment in the trade direction
        aligned = mtf.direction is c.direction
        mtf_term = (mtf.score * 0.18) if aligned else (-mtf.score * 0.10)
        p += mtf_term; parts.append(f"mtf{mtf_term:+.2f}")
        # regime fit
        fit = {
            ("SWEEP_RECLAIM", "TRAP_REVERSAL"): 0.12,
            ("SWEEP_RECLAIM", "RANGE_DAY"): 0.06,
            ("TREND_CONTINUATION", "TREND_DAY"): 0.14,
            ("BOS_RETEST", "TREND_DAY"): 0.10,
            ("RANGE_FADE", "RANGE_DAY"): 0.10,
        }.get((c.setup, regime), -0.04)
        p += fit; parts.append(f"regime{fit:+.2f}")
        # confirmation strength
        conf_term = (c.confirmation - 0.6) * 0.20
        p += conf_term; parts.append(f"conf{conf_term:+.2f}")
        # premium/discount fit
        pd_term = 0.0
        if price_zone is PriceZone.DISCOUNT and c.direction is Direction.LONG:
            pd_term = 0.05
        elif price_zone is PriceZone.PREMIUM and c.direction is Direction.SHORT:
            pd_term = 0.05
        elif price_zone is PriceZone.PREMIUM and c.direction is Direction.LONG:
            pd_term = -0.05
        elif price_zone is PriceZone.DISCOUNT and c.direction is Direction.SHORT:
            pd_term = -0.05
        p += pd_term; parts.append(f"pd{pd_term:+.2f}")
        # displacement footprint
        disp_term = 0.05 if disp >= STRONG_DISPLACEMENT else 0.0
        p += disp_term
        # orderflow agreement
        flow_term = 0.04 if ((flow.pressure is ProxyPressure.BULLISH) == (want is Bias.BULLISH)
                             and flow.pressure is not ProxyPressure.NEUTRAL) else 0.0
        p += flow_term
        # session timing
        sess_term = 0.05 if in_killzone else -0.03
        p += sess_term; parts.append(f"sess{sess_term:+.2f}")
        # stop quality (beyond engineered liquidity)
        if not c.stop_beyond_pool:
            p -= 0.06; parts.append("stop-0.06")
        # spread / volatility penalty
        if spread_ratio >= 0.8:
            p -= 0.05
        # account state: defensive when bleeding
        if inp.consecutive_losses >= 2:
            p -= 0.04; parts.append("acct-0.04")
        eq = inp.broker.equity or 0.0
        bal = inp.broker.balance or 0.0
        if bal and eq and eq < bal * 0.97:
            p -= 0.03
        # recent realised performance (the learning loop)
        perf_adj = self._perf.p_win_adjustment(c.setup, regime)
        if perf_adj:
            p += perf_adj; parts.append(f"perf{perf_adj:+.2f}")

        p_win = max(0.05, min(p, 0.85))
        target_r = min(c.target_r() if False else
                       (abs(c.target - c.entry) / c.stop_distance
                        if c.stop_distance > 0 else 0.0), TARGET_R_CAP)
        ev = p_win * target_r - (1.0 - p_win) * 1.0
        return ev, p_win, target_r, " ".join(parts)

    # -- stop / target helpers ----------------------------------------------
    def _protect_stop(self, d, entry, base, atr5, spread, liq
                      ) -> Optional[Tuple[float, float, bool]]:
        short = d is Direction.SHORT
        buf = max(0.25 * atr5, 2.0 * spread, 0.30)
        if short and base <= entry:
            return None
        if not short and base >= entry:
            return None
        stop = base + buf if short else base - buf
        beyond_pool = True
        pools = liq.buy_side() if short else liq.sell_side()
        for lvl in pools:
            ppx = lvl.price
            if short and entry < ppx <= stop + buf:
                stop = max(stop, ppx + buf); beyond_pool = True
            elif not short and stop - buf <= ppx < entry:
                stop = min(stop, ppx - buf); beyond_pool = True
        dist = (stop - entry) if short else (entry - stop)
        if dist < MIN_STOP_DISTANCE:
            dist = MIN_STOP_DISTANCE
            stop = entry + dist if short else entry - dist
        max_d = min(MAX_STOP_ABSOLUTE, max(3.0, 3.0 * atr5))
        if dist > max_d:
            return None
        return round(stop, 2), round(dist, 2), beyond_pool

    def _target(self, d, entry, stop, liq, range_fade=False) -> float:
        """Draw on liquidity: nearest opposing pool in the trade direction; if
        none, a default R multiple."""
        dist = abs(entry - stop)
        if d is Direction.LONG:
            ahead = sorted(l.price for l in liq.buy_side() if l.price > entry + dist)
            if ahead:
                return ahead[0]
            return entry + (1.5 if range_fade else 2.5) * dist
        ahead = sorted((l.price for l in liq.sell_side() if l.price < entry - dist),
                       reverse=True)
        if ahead:
            return ahead[0]
        return entry - (1.5 if range_fade else 2.5) * dist

    # -- regime --------------------------------------------------------------
    @staticmethod
    def _regime(mtf, chop, disp, disp_dir) -> str:
        if chop.subtype is ChopSubtype.TRAP_REVERSAL_FROM_CHOP:
            return "TRAP_REVERSAL"
        if chop.subtype in (ChopSubtype.LIQUIDITY_CHOP_WITH_SWEEP,):
            return "RANGE_DAY"
        unanimous = all(b is Bias.BULLISH for b in (mtf.h1, mtf.m15, mtf.m5)) or \
            all(b is Bias.BEARISH for b in (mtf.h1, mtf.m15, mtf.m5))
        if unanimous and disp >= ANCHOR_DISPLACEMENT:
            return "TREND_DAY"
        if disp >= STRONG_DISPLACEMENT:
            return "POST_SPIKE_CHOP"
        return "RANGE_DAY"

    # -- structure helpers (reused patterns) --------------------------------
    def _reclaimed_sweep(self, want, m5, sweeps):
        aligned = [s for s in sweeps if s.status is SweepStatus.TRUE_SWEEP
                   and s.rejection_bias is want and 0 <= s.sweep_index < len(m5)
                   and s.sweep_index >= len(m5) - _RECENT_EVENT_WINDOW]
        for s in sorted(aligned, key=lambda x: x.sweep_index, reverse=True):
            level = s.level.price
            after = m5[s.sweep_index + 1:] or m5[s.sweep_index:]
            if not after:
                continue
            held = all((c.close > level if want is Bias.BULLISH else c.close < level)
                       for c in after[-_RECLAIM_HOLD:])
            if held:
                return s
        return None

    @staticmethod
    def _retested_zone(d, m5, zones, kind) -> Optional[Zone]:
        want = Bias.BULLISH if d is Direction.LONG else Bias.BEARISH
        last = m5[-1]
        recent = list(m5[-_ZONE_TOUCH_WINDOW:])
        cands = [z for z in zones if z.kind is kind and z.bias is want
                 and any(c.low <= z.top and c.high >= z.bottom for c in recent)]
        for z in sorted(cands, key=lambda z: z.created_index, reverse=True):
            if d is Direction.LONG and last.close > z.top:
                return z
            if d is Direction.SHORT and last.close < z.bottom:
                return z
        return None

    @staticmethod
    def _break_retest(d, m5, structure, atr5) -> Optional[float]:
        want = Bias.BULLISH if d is Direction.LONG else Bias.BEARISH
        tol = max(0.30, 0.25 * atr5)
        last = m5[-1]
        for ev in reversed(structure.events):
            if ev.bias is not want or ev.event_type is not StructureEventType.BOS:
                continue
            if ev.index < len(m5) - _RECENT_EVENT_WINDOW:
                break
            after = m5[ev.index + 1:]
            if not after:
                continue
            if d is Direction.LONG and any(c.low <= ev.price + tol for c in after) \
                    and last.close > ev.price:
                return ev.price
            if d is Direction.SHORT and any(c.high >= ev.price - tol for c in after) \
                    and last.close < ev.price:
                return ev.price
        return None

    @staticmethod
    def _pivot(candles, *, short, beyond, k=2, lookback=40) -> Optional[float]:
        cs = list(candles)[-lookback:]
        for i in range(len(cs) - k - 1, k - 1, -1):
            window = cs[i - k:i + k + 1]
            if short:
                lv = cs[i].high
                if lv >= max(c.high for c in window) and lv > beyond:
                    return lv
            else:
                lv = cs[i].low
                if lv <= min(c.low for c in window) and lv < beyond:
                    return lv
        return None

    @staticmethod
    def _dir_close(candle, d) -> bool:
        return (candle.close > candle.open if d is Direction.LONG
                else candle.close < candle.open)

    def _consumed_block(self, d, stop, atr5, now) -> str:
        rec = self._consumed.get(d)
        if rec is None:
            return ""
        level, when = rec
        try:
            if when is None or now is None or (now - when) > CONSUMED_STOP_TTL:
                self._consumed.pop(d, None); return ""
        except TypeError:
            self._consumed.pop(d, None); return ""
        if abs(stop - level) > MAX_STOP_ABSOLUTE:
            return ""
        clear = max(1.0, min(atr5, 6.0))
        cleared = (stop > level + clear if d is Direction.SHORT else stop < level - clear)
        return "" if cleared else (
            f"ZONE_CONSUMED: a {d.value} stop at {level:.2f} was just swept; "
            f"new stop {stop:.2f} does not clear it")

    # -- assembly ------------------------------------------------------------
    def _build_decision(self, symbol, now, c: Candidate, grade, tier, ev
                        ) -> TradeDecision:
        return TradeDecision(
            decision_id=f"gold-{now.strftime('%Y%m%dT%H%M%S')}Z",
            time_utc=now, symbol=symbol, direction=c.direction,
            status=DecisionStatus.PROPOSED,
            setup_type=SETUP_TYPE_TEMPLATE.format(
                setup=c.setup.lower(), grade=grade, lot=tier),
            thesis=(f"gold_alpha {c.setup} {c.direction.value}: {c.detail}; "
                    f"trigger {c.trigger}; ev {ev:+.2f}; protected invalidation"),
            invalidation_price=c.stop, entry_price=c.entry, stop_loss=c.stop,
            take_profits=(round(c.target, 2),),
            confidence=min(0.5 + ev, 0.95), uncertainty=max(0.5 - ev, 0.05),
            reason=f"{c.setup} via {c.trigger} ev={ev:+.2f}")

    def _fill_stop_output(self, ch, c: Candidate) -> None:
        ch.update(
            tactical_stop_price=round(c.stop, 2),
            tactical_stop_distance=round(c.stop_distance, 2),
            tactical_stop_source=c.stop_source,
            stop_logic=(f"beyond {c.stop_source} (beyond_pool="
                        f"{c.stop_beyond_pool}; SL not at the hunted pool)"),
            invalidation_reason=(f"{c.direction.value} thesis invalid beyond "
                                 f"{c.stop:.2f}"),
            tp_trail=(f"target {c.target:.2f} (draw on liquidity); BE at +1R "
                      "then ATR trail; fast exit on CHOCH-against"))

    def _base_output(self, session, in_killzone, mtf, htf_bias, structure,
                     zones, liq, sweeps, price_zone, flow, disp, regime, vol,
                     chop, entry) -> dict:
        fvg = sum(1 for z in zones if z.kind is ZoneKind.FAIR_VALUE_GAP and not z.mitigated)
        ob = sum(1 for z in zones if z.kind is ZoneKind.ORDER_BLOCK and not z.mitigated)
        tw = [s for s in sweeps if s.status is SweepStatus.TRUE_SWEEP]
        return {
            "mode": PROFILE_NAME, "profile": PROFILE_NAME,
            "fresh_entry_scan": "ACTIVE", "new_candle_detected": "no",
            "regime": regime,
            "narrative": f"{regime}: mtf={mtf.score:.2f} "
                         f"dir={mtf.direction.value if mtf.direction else '-'} "
                         f"pd={price_zone.value if price_zone else '?'} disp={disp:.1f}x",
            "htf_context": f"d1={self._b(mtf.d1)} h4={self._b(mtf.h4)} "
                           f"h1={self._b(mtf.h1)} m15={self._b(mtf.m15)} "
                           f"m5={self._b(mtf.m5)} mtf_score={mtf.score:.2f} "
                           f"htf_bias={htf_bias.value}",
            "killzone": (session.value if in_killzone
                         else f"LOW_LIQUIDITY({session.value})"
                         if session in _LOW_LIQUIDITY_SESSIONS else session.value),
            "liquidity_map": f"buy_side={len(liq.buy_side())} "
                             f"sell_side={len(liq.sell_side())}",
            "sweep_status": f"true_sweeps={len(tw)}"
                            + (f" last={tw[-1].swept_side.value}@{tw[-1].level.price:.2f}"
                               if tw else ""),
            "structure_state": f"bias={structure.final_bias.value} "
                               f"last={structure.events[-1].event_type.value if structure.events else 'NONE'}",
            "fvg_ob_status": f"fvg_open={fvg} ob_open={ob}",
            "orderflow": f"{flow.pressure.value}/{flow.volume_state.value} "
                         f"vol_ratio={flow.volume_ratio:.2f}",
            "premium_discount": price_zone.value if price_zone else "UNKNOWN",
            "volatility": f"{vol.state.value} chop={chop.subtype.value}",
            "candidates": "none", "direction": "NONE", "setup": "NONE",
            "grade": "NONE", "ev": "-", "p_win": "-", "target_r": "-",
            "score_detail": "", "perf": "", "entry_trigger": "NONE",
            "tactical_stop_price": None, "tactical_stop_distance": None,
            "tactical_stop_source": "none", "stop_logic": "",
            "invalidation_reason": "", "tp_trail": "", "risk_if_sl_hit": None,
            "lot_decision": "NONE", "displacement": round(disp, 2),
            "reentry_plan": "", "waiting_for": "", "reason": "",
        }

    def _context(self, session, htf_bias, structure_bias, price_zone, disp,
                 regime, ch) -> PipelineContext:
        return PipelineContext(
            session=session, htf_bias=htf_bias,
            regime=Regime.TREND if regime == "TREND_DAY" else Regime.RANGE,
            structure_bias=structure_bias, has_setup=ch.get("setup") != "NONE",
            regime_reason=f"gold_alpha {regime}", price_zone=price_zone,
            displacement_ratio=disp, challenge=ch)

    def _wait(self, context, ch, reason, waiting="", plan="") -> PipelineResult:
        ch["reason"] = reason
        ch["waiting_for"] = waiting
        ch["reentry_plan"] = plan or ch.get("reentry_plan", "")
        return PipelineResult(stage=PipelineStage.HYPOTHESIS, approved=False,
                              reason=reason, context=context)

    @staticmethod
    def _rearm(mtf, zones) -> Tuple[str, str]:
        d = mtf.direction
        if d is None:
            return "HTF_DIRECTION", "wait for a higher-timeframe direction"
        want = Bias.BULLISH if d is Direction.LONG else Bias.BEARISH
        fvg = [z for z in zones if z.kind is ZoneKind.FAIR_VALUE_GAP
               and z.bias is want and not z.mitigated]
        if fvg:
            return "FVG_RETEST", f"wait for mitigation of the {want.value.lower()} FVG"
        return "SWEEP", f"wait for a sweep+reclaim or BOS in the {d.value} direction"

    # -- shared math ---------------------------------------------------------
    def _htf_bias(self, daily, h4) -> HtfBias:
        try:
            return self._e.htf.classify(daily, h4).bias
        except Exception:  # noqa: BLE001
            return HtfBias.NEUTRAL

    @staticmethod
    def _b(bias) -> str:
        return bias.value if bias is not None else "-"

    @staticmethod
    def _m1_state(m1) -> Optional[str]:
        if not m1 or len(m1) < 3:
            return None
        last = list(m1)[-3:]
        net = last[-1].close - last[0].open
        thr = 0.1 * sum(c.high - c.low for c in last) / 3
        return "BULLISH" if net > thr else "BEARISH" if net < -thr else "FLAT"

    @staticmethod
    def _displacement(candles, body_window=8, range_window=20):
        recent = list(candles[-range_window:])
        if len(recent) < 5:
            return 0.0, None
        ranges = sorted(c.high - c.low for c in recent)
        median = ranges[len(ranges) // 2]
        if median <= 0:
            return 0.0, None
        biggest = max(list(candles[-body_window:]), key=lambda c: abs(c.close - c.open))
        ratio = abs(biggest.close - biggest.open) / median
        d = (Direction.LONG if biggest.close > biggest.open
             else Direction.SHORT if biggest.close < biggest.open else None)
        return ratio, d

    def _new_candle(self, m5, m1) -> str:
        t5 = m5[-1].time_utc if m5 else None
        t1 = m1[-1].time_utc if m1 else None
        fresh = (t5 != self._last_m5_time) or (t1 != self._last_m1_time)
        first = self._last_m5_time is None and self._last_m1_time is None
        self._last_m5_time, self._last_m1_time = t5, t1
        return "first_cycle" if first else ("yes" if fresh else "no")

    @staticmethod
    def _agg(m5, target) -> List[Candle]:
        try:
            return list(aggregate(m5, target))
        except (AggregationError, ValueError):
            return []

    @staticmethod
    def _atr(candles, period=14) -> float:
        w = list(candles[-period:])
        return sum(c.high - c.low for c in w) / len(w) if w else 0.0


def make_gold_alpha_pipeline(
    canonical_symbol: str, *, max_spread_price: float = 1.0,
    ev_bar: float = EV_BAR, max_staleness: Optional[timedelta] = None,
) -> GoldAlphaEngine:
    """Build the single gold_alpha engine for LIVE XAUUSDm."""
    canonical = canonical_symbol.strip().upper()
    engines = GoldEngines(validator=DataValidator(ValidationConfig(
        expected_symbol=canonical, detect_gaps=False,
        max_staleness=max_staleness or timedelta(minutes=30))))
    return GoldAlphaEngine(make_gold_limits(canonical),
                           max_spread=max_spread_price, ev_bar=ev_bar,
                           engines=engines)
