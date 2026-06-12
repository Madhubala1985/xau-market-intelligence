"""Institutional SMC execution pipeline (Task SMC-EXECUTION-001). DEMO ONLY.

Replaces the retail momentum behavior of demo_challenge (live evidence
2026-06-11: trades fired from M5/M1 momentum + rejection wicks alone). The
owner's goal was never a retail momentum bot — it is the institutional
SMC/liquidity model WITH active execution: not silent, not frozen on stale
structural stops, but never trading without an institutional setup.

A trade requires ALL FOUR gates, re-evaluated on EVERY new candle:

    A. Higher-timeframe context  — D1/H4/H1/M15 alignment (MtfAlignmentEngine,
       D1-weighted) or D1/H4 bias (HtfBiasEngine): a directional candidate.
    B. Session/liquidity context — London/NY/overlap kill zone, OR an Asian
       high/low sweep, OR buy-/sell-side liquidity taken (TRUE_SWEEP), OR a
       clear liquidity target ahead.
    C. SMC structure anchor      — liquidity sweep + displacement, FVG
       retest/mitigation, order-block retest, break & retest, or BOS/CHOCH
       in the trade direction.
    D. Executable local trigger  — M5/M1 mitigation/pullback rejection,
       break-retest continuation, or displacement after pullback — plus a
       structurally justified TACTICAL stop (local swing / OB boundary /
       FVG boundary / sweep extreme + ATR/spread buffer, hard 8 USD ceiling).

M1/M5 momentum alone is NOT enough (gate C blocks it). A rejection wick
alone is NOT enough. When a gate fails, the pipeline prints exactly what it
is waiting for (reentry_plan / waiting_for) and rescans on the next candle —
the STOP_TOO_WIDE-for-570-cycles freeze and the warmstart prison are both
structurally impossible here.

Unchanged safety: fixed lots 0.05/0.10 (survival-cap demotion, 0.01 only on
margin refusal — enforced by ChallengeTradePlanner), RiskGovernor final
authority, gateway-only sending, kill switch, no martingale/grid/averaging/
hedging. This module never sends orders and holds no credentials.
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
from src.liquidity.liquidity_map import LiquidityMapEngine
from src.liquidity.sweep import SweepEngine, SweepStatus
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
from src.structure.zones import Zone, ZoneEngine, ZoneKind

# Fixed challenge lots (unchanged from DEMO-CHALLENGE-001; 0.01 exists only
# as the planner's margin-refusal fallback).
LOT_NORMAL = 0.05
LOT_STRONG = 0.10

# setup_type carries the lot to ChallengeTradePlanner (same lot= grammar).
SETUP_TYPE_TEMPLATE = "smc_{anchor}[{grade},lot={lot:.2f}]"

# Tactical stop geometry (unchanged hard bounds).
MIN_STOP_DISTANCE = 0.50
MAX_STOP_ABSOLUTE = 8.0
REJECTION_WICK_RATIO = 0.40

STRONG_DISPLACEMENT = 1.6
# D2 guards (decision 2026-06-12-01): an anchor whose level sits further
# than this many M5-ATRs from price is no longer live structure; and a
# counter-trend candidate facing unanimous H1/M15/M5 opposition with at
# least this displacement may only trade a fresh sweep-reclaim.
STALE_ANCHOR_ATR_MULT = 10.0
CONFLICT_DISPLACEMENT = 1.3
ANCHOR_DISPLACEMENT = 1.3  # sweep needs real displacement behind it

_KILL_ZONES = {
    SessionType.LONDON, SessionType.NEW_YORK, SessionType.LONDON_NY_OVERLAP,
}
_LOW_LIQUIDITY_SESSIONS = {
    SessionType.ROLLOVER, SessionType.LOW_LIQUIDITY, SessionType.CLOSED,
}

_RECENT_EVENT_WINDOW = 40  # candles: how fresh a BOS/CHOCH anchor must be
_ZONE_TOUCH_WINDOW = 3     # candles allowed between zone touch and trigger


class SetupGrade:
    STRONG = "STRONG"
    NORMAL = "NORMAL"


def make_challenge_limits(expected_symbol: str) -> RiskLimits:
    """RiskLimits of the demo_challenge/smc_challenge envelope (owner
    decision 2026-06-11-01; numbers pinned to session_profiles by test)."""
    return RiskLimits(
        expected_symbol=expected_symbol,
        max_risk_per_trade=0.030,
        max_daily_loss=0.05,
        max_weekly_loss=0.10,
        max_trades_per_day=15,  # owner amendment 2026-06-12-05 (was 10)
        max_open_trades=3,
        max_spread=1.0,
    )


@dataclass
class SmcEngines:
    """Injectable institutional engines (defaults are the real ones)."""

    validator: DataValidator = field(default_factory=DataValidator)
    session: SessionEngine = field(default_factory=SessionEngine)
    htf: HtfBiasEngine = field(default_factory=HtfBiasEngine)
    mtf: MtfAlignmentEngine = field(default_factory=MtfAlignmentEngine)
    structure: MarketStructureEngine = field(default_factory=MarketStructureEngine)
    liquidity: LiquidityMapEngine = field(default_factory=LiquidityMapEngine)
    sweep: SweepEngine = field(default_factory=SweepEngine)
    zones: ZoneEngine = field(default_factory=ZoneEngine)
    asian: AsianRangeEngine = field(default_factory=AsianRangeEngine)
    # D6 (decision 2026-06-12-04): market-state gate — consolidation and
    # dangerous volatility are not traded.
    volatility: VolatilityClassifier = field(default_factory=VolatilityClassifier)
    chop: ChopClassifier = field(default_factory=ChopClassifier)


@dataclass(frozen=True)
class _Anchor:
    label: str            # SWEEP_DISPLACEMENT/FVG_RETEST/OB_RETEST/BREAK_RETEST/CHOCH/BOS
    zone: Optional[Zone] = None
    level: Optional[float] = None
    detail: str = ""


class SmcExecutionPipeline:
    """A+B+C+D gated SMC decision engine; same decide() interface as
    DecisionPipeline so SupervisedDemoSession/TradingService drive it
    unchanged (gateway, journal, reconciliation, trailing all reused)."""

    def __init__(
        self,
        limits: RiskLimits,
        *,
        max_spread: float = 1.0,
        engines: Optional[SmcEngines] = None,
    ) -> None:
        if max_spread <= 0:
            raise ValueError("max_spread must be > 0")
        self._limits = limits
        self._governor = RiskGovernor(limits)
        self._max_spread = max_spread
        self._e = engines or SmcEngines()
        self.threshold_profile = "smc_challenge"
        # Fresh-entry scan state: every new candle re-arms the search.
        self._last_m5_time = None
        self._last_m1_time = None
        self._last_stop_price: Optional[float] = None

    # -- public ------------------------------------------------------------
    def decide(self, inp: PipelineInput) -> PipelineResult:
        e = self._e
        now = inp.now or (
            inp.exec_candles[-1].time_utc if inp.exec_candles else None
        )
        report = e.validator.validate_candles(inp.exec_candles, now=now)
        if report.status is not ValidationStatus.VALID:
            return PipelineResult(
                stage=PipelineStage.DATA_REJECTED, approved=False,
                reason=(
                    "data rejected: "
                    f"{[i.code.value for i in report.blocking_issues]}"
                ),
            )

        m5 = list(inp.exec_candles)
        m15 = list(inp.m15_candles) if inp.m15_candles else self._aggregate(
            m5, Timeframe.M15
        )
        h1 = list(inp.h1_candles) if inp.h1_candles else self._aggregate(
            m5, Timeframe.H1
        )
        m1 = list(inp.m1_candles) if inp.m1_candles else []
        last = m5[-1]
        entry = last.close
        session = e.session.classify(now)
        spread = max(inp.current_spread, 0.0)
        equity = inp.broker.equity or inp.broker.balance or 0.0
        atr5 = self._atr(m5)
        new_candle = self._detect_new_candle(m5, m1)

        # -- institutional context (all engines, every cycle) ---------------
        structure = e.structure.analyze(m5)
        liquidity_map = e.liquidity.build(m5)
        sweeps = e.sweep.detect(m5, liquidity_map)
        zones = e.zones.build(m5)
        asian = e.asian.analyze(m5, now)
        displacement, disp_direction = self._displacement(m5)
        htf_bias = self._htf_bias(inp.daily_candles, inp.h4_candles)
        mtf = e.mtf.align(
            daily=inp.daily_candles, h4=inp.h4_candles, h1=h1, m15=m15,
            m5_bias=(
                structure.final_bias
                if structure.final_bias is not Bias.NEUTRAL else None
            ),
            m1_state=self._m1_state(m1),
        )

        killzone = session.value
        in_killzone = session in _KILL_ZONES

        # -- Gate A: higher-timeframe context --------------------------------
        candidate = mtf.direction or self._htf_direction(htf_bias)
        # D3 (decision 2026-06-12-02): a CONFIRMED intraday trend overrides
        # a stale higher-timeframe veto — the constructive twin of the
        # LTF_CONSENSUS_CONFLICT stand-down. Live evidence 2026-06-11: four
        # counter-trend shorts (net -60) and zero longs on a +145 USD
        # institutional buying day because D1+H4 weights (0.55) vetoed the
        # unanimous bullish H1/M15/M5 stack all day. When H1+M15+M5 are
        # unanimous AND displacement >= CONFLICT_DISPLACEMENT confirms
        # them, the consensus direction becomes the candidate; every other
        # gate (kill zone/liquidity, fresh anchor, trigger, tactical stop)
        # still applies unchanged.
        trend_override = ""
        for cons_bias, cons_dir in (
            (Bias.BULLISH, Direction.LONG),
            (Bias.BEARISH, Direction.SHORT),
        ):
            if (
                all(b is cons_bias for b in (mtf.h1, mtf.m15, mtf.m5))
                and disp_direction is cons_dir
                and displacement >= CONFLICT_DISPLACEMENT
                and candidate is not cons_dir
            ):
                candidate = cons_dir
                trend_override = (
                    f" TREND_DAY_OVERRIDE->{cons_dir.value} "
                    f"(H1/M15/M5 unanimous {cons_bias.value}, "
                    f"disp {displacement:.1f}x)"
                )
                break
        htf_context = (
            f"d1={self._b(mtf.d1)} h4={self._b(mtf.h4)} h1={self._b(mtf.h1)} "
            f"m15={self._b(mtf.m15)} m5={self._b(mtf.m5)} "
            f"mtf_score={mtf.score:.2f} htf_bias={htf_bias.value}"
            f"{trend_override}"
        )

        smc = {
            "mode": "smc",
            "profile": "smc_challenge",
            "fresh_entry_scan": "ACTIVE",
            "new_candle_detected": new_candle,
            "local_structure_updated": "no",
            "direction": candidate.value if candidate else "NONE",
            "grade": "NONE",
            "htf_context": htf_context,
            "killzone": (
                killzone if in_killzone
                else f"LOW_LIQUIDITY({killzone})" if session in
                _LOW_LIQUIDITY_SESSIONS else killzone
            ),
            "liquidity_context": "NONE",
            "smc_anchor": "NONE",
            "entry_trigger": "NONE",
            "tactical_stop_price": None,
            "tactical_stop_distance": None,
            "tactical_stop_source": "none",
            "stop_logic": "",
            "invalidation_reason": "",
            "risk_if_sl_hit": None,
            "lot_decision": "NONE",
            "displacement": round(displacement, 2),
            "reentry_plan": "",
            "waiting_for": "",
            "reason": "",
        }
        context = self._context(session, htf_bias, structure.final_bias,
                                candidate, smc)

        if spread > self._max_spread:
            return self._wait(
                context, smc,
                f"spread too high ({spread:.3f} > {self._max_spread:.3f})",
            )
        if equity <= 0:
            return self._wait(context, smc, "account equity unknown")

        # -- D6 market-state gate (decision 2026-06-12-04) -------------------
        # Live evidence 2026-06-11/12: 7 of 9 losses were probes into the
        # post-spike whipsaw. The ENVIRONMENT (m5[:-1], so the current
        # signal impulse never flags itself) must be tradeable: dangerous
        # volatility and structureless chop are not traded.
        environment = m5[:-1] if len(m5) > 1 else m5
        spread_ratio = spread / self._max_spread if self._max_spread else 0.0
        vol = e.volatility.classify(environment, spread_ratio=spread_ratio)
        chop = e.chop.classify(
            environment, sweeps, spread_ratio=spread_ratio,
            directional_score=mtf.score,
        )
        smc["market_state"] = f"vol={vol.state.value} chop={chop.subtype.value}"
        if vol.dangerous:
            return self._wait(
                context, smc,
                f"VOLATILITY_BLOCK: {vol.state.value} — {vol.reason}; "
                "dangerous conditions are not traded",
                waiting="SWEEP",
                plan="wait for volatility to normalize, then re-qualify",
            )
        if chop.subtype in (ChopSubtype.DANGEROUS_CHOP,
                            ChopSubtype.LOW_QUALITY_CHOP):
            return self._wait(
                context, smc,
                f"CHOP_BLOCK: {chop.subtype.value} — {chop.reason}; "
                "consolidation is not traded — waiting for displacement "
                "or a confirmed liquidity event",
                waiting="SWEEP",
                plan="wait for a sweep/displacement out of the range",
            )

        if candidate is None:
            return self._wait(
                context, smc,
                f"waiting for higher-timeframe direction ({htf_context})",
                waiting="HTF_DIRECTION",
            )

        # -- Gate B: session / liquidity context ------------------------------
        liquidity_context = self._liquidity_context(
            candidate, asian, sweeps, liquidity_map, entry
        )
        smc["liquidity_context"] = liquidity_context
        if not in_killzone and liquidity_context == "NONE":
            return self._wait(
                context, smc,
                f"outside kill zones ({killzone}) with no liquidity event — "
                "institutional context missing",
                waiting="SWEEP",
                plan="wait for London/NY or an Asian/session liquidity sweep",
            )

        # -- Gate C: SMC structure anchor -------------------------------------
        anchor = self._find_anchor(
            candidate, m5, structure, sweeps, zones, displacement,
            disp_direction, atr5,
        )
        if anchor is None:
            waiting, plan = self._reentry_plan(candidate, zones)
            return self._wait(
                context, smc,
                f"SMC_ANCHOR_MISSING: no aligned sweep+displacement, "
                f"FVG/OB retest, break-retest, or BOS/CHOCH for "
                f"{candidate.value}; M1/M5 momentum alone does not trade",
                waiting=waiting, plan=plan,
            )
        smc["smc_anchor"] = anchor.label

        # -- D2 guards (decision 2026-06-12-01, live evidence 2026-06-11:
        # two SL losses shorting a vertical up-day on stale structure) ------
        # (1) the anchor must be structurally LIVE near price.
        if (
            anchor.level is not None and atr5 > 0
            and abs(entry - anchor.level) > STALE_ANCHOR_ATR_MULT * atr5
        ):
            waiting, plan = self._reentry_plan(candidate, zones)
            return self._wait(
                context, smc,
                f"SMC_ANCHOR_STALE: {anchor.label} level "
                f"{anchor.level:.2f} is {abs(entry - anchor.level):.2f} "
                f"from price (> {STALE_ANCHOR_ATR_MULT:.0f}x ATR "
                f"{atr5:.2f}) — that structure is no longer live",
                waiting=waiting, plan=plan,
            )
        # (2) counter-trend stand-down (D5, decision 2026-06-12-03):
        # fading a UNANIMOUS H1/M15/M5 consensus requires the candidate's
        # OWN displacement footprint (>= CONFLICT_DISPLACEMENT in the
        # candidate direction — institutional sellers/buyers leave
        # footprints; a drift rejection is not one). Sweep-reclaim anchors
        # satisfy this by construction (ANCHOR_DISPLACEMENT).
        opposing_bias = (
            Bias.BULLISH if candidate is Direction.SHORT else Bias.BEARISH
        )
        if all(b is opposing_bias for b in (mtf.h1, mtf.m15, mtf.m5)):
            own_footprint = (
                disp_direction is candidate
                and displacement >= CONFLICT_DISPLACEMENT
            )
            if not own_footprint:
                return self._wait(
                    context, smc,
                    f"COUNTER_TREND_NO_DISPLACEMENT: H1/M15/M5 all "
                    f"{opposing_bias.value} and the {candidate.value} "
                    f"thesis shows no displacement footprint of its own "
                    f"(disp {displacement:.1f}x"
                    f"{' ' + disp_direction.value if disp_direction else ''}"
                    ") — fading a unanimous intraday consensus requires a "
                    f"fresh {candidate.value}-side impulse (e.g. a sweep "
                    "rejection)",
                    waiting="SWEEP",
                    plan=(
                        "wait for a liquidity sweep + rejection impulse in "
                        "the candidate direction or for HTF/LTF realignment"
                    ),
                )

        # -- Gate D: executable local trigger ---------------------------------
        trigger = self._entry_trigger(
            candidate, anchor, m5, displacement, disp_direction
        )
        if trigger is None:
            waiting, plan = self._reentry_plan(candidate, zones, anchor)
            return self._wait(
                context, smc,
                f"anchor {anchor.label} present but no executable local "
                "trigger yet — waiting for break/retest or mitigation "
                "rejection",
                waiting=waiting, plan=plan,
            )
        smc["entry_trigger"] = trigger

        # -- tactical stop (structurally justified, never structural-HTF) -----
        stop = self._tactical_stop(candidate, entry, m5, m1, atr5, spread,
                                   anchor, sweeps)
        if stop is None:
            waiting, plan = self._reentry_plan(candidate, zones, anchor)
            return self._wait(
                context, smc,
                "no structurally justified tactical stop within "
                f"{MAX_STOP_ABSOLUTE:.1f} USD — re-entry plan armed, next "
                "candle rescans (a wide HTF structural stop is never used)",
                waiting="LOCAL_SWING" if waiting == "SWEEP" else waiting,
                plan=plan or "wait for a fresh local swing / zone boundary",
            )
        stop_price, stop_distance, stop_source, stop_logic = stop
        if self._last_stop_price != stop_price:
            smc["local_structure_updated"] = "yes"
            self._last_stop_price = stop_price
        smc.update(
            tactical_stop_price=round(stop_price, 2),
            tactical_stop_distance=round(stop_distance, 2),
            tactical_stop_source=stop_source,
            stop_logic=stop_logic,
            invalidation_reason=(
                f"{candidate.value} thesis invalid beyond {stop_price:.2f} "
                f"({stop_source}: {anchor.label} setup broken)"
            ),
        )

        # -- grade + fixed lot -------------------------------------------------
        grade = self._grade(in_killzone, anchor, displacement, mtf)
        smc["grade"] = grade
        lot, lot_why = self._fixed_lot(grade, session, equity, stop_distance,
                                       spread)
        if lot is None:
            return self._wait(context, smc, lot_why, waiting="LOCAL_SWING",
                              plan="wait for a tighter local invalidation")
        # Decision 2026-06-11-06: the tier lot selects the planner's equity
        # risk percentage; display the BUDGETED risk (the planner's floored
        # lot risks at most this), never the obsolete fixed-lot dollars.
        risk_pct = 0.015 if lot == LOT_STRONG else 0.010
        budget_usd = equity * risk_pct
        est_lot = max(
            int(budget_usd / (100.0 * (stop_distance + spread)) / 0.01) * 0.01,
            0.01,
        )
        smc["lot_decision"] = (
            f"~{est_lot:.2f} (tier {lot:.2f} = {risk_pct:.1%} equity risk)"
        )
        risk_usd = min(
            budget_usd, est_lot * 100.0 * (stop_distance + spread)
        )
        smc["risk_if_sl_hit"] = round(risk_usd, 2)

        decision = self._decision(
            inp.symbol, now, candidate, entry, stop_price, stop_distance,
            anchor, trigger, grade, lot, liquidity_context,
        )
        confidence = self._confidence(grade, anchor, trigger)
        smc["reason"] = (
            f"{grade} {candidate.value}: anchor={anchor.label} "
            f"({anchor.detail}) trigger={trigger} "
            f"liquidity={liquidity_context} killzone={killzone} "
            f"stop={stop_source}@{stop_price:.2f} ({stop_distance:.2f}); "
            f"{lot_why}"
        )

        # Risk Governor: final authority (challenge envelope limits).
        # protected_addon=True only keeps the PIPELINE duplicate check from
        # pre-blocking add-on candidates; ChallengeTradePlanner + gateway
        # re-run the authoritative add-on gates before anything is sent.
        verdict = self._governor.evaluate(decision, RiskContext(
            broker=inp.broker,
            current_spread=spread,
            lot_size=lot,
            intended_risk_pct=risk_usd / equity,
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
            lot_size=lot,
        )

    # -- Gate B helpers ---------------------------------------------------------
    @staticmethod
    def _liquidity_context(
        candidate: Direction,
        asian: AsianRangeContext,
        sweeps,
        liquidity_map,
        entry: float,
    ) -> str:
        if asian.known and asian.swept in ("LOW", "BOTH"):
            return "ASIAN_LOW_SWEEP"
        if asian.known and asian.swept == "HIGH":
            return "ASIAN_HIGH_SWEEP"
        if any(s.status is SweepStatus.TRUE_SWEEP for s in sweeps):
            return "SESSION_LIQUIDITY"
        try:
            if candidate is Direction.LONG:
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

    # -- Gate C: anchors ----------------------------------------------------------
    def _find_anchor(
        self,
        candidate: Direction,
        m5: Sequence[Candle],
        structure: StructureResult,
        sweeps,
        zones: Sequence[Zone],
        displacement: float,
        disp_direction: Optional[Direction],
        atr5: float,
    ) -> Optional[_Anchor]:
        want = Bias.BULLISH if candidate is Direction.LONG else Bias.BEARISH

        # 1) liquidity sweep + displacement (the primary institutional entry)
        aligned_sweeps = [
            s for s in sweeps
            if s.status is SweepStatus.TRUE_SWEEP and s.rejection_bias is want
        ]
        if aligned_sweeps and displacement >= ANCHOR_DISPLACEMENT \
                and disp_direction is candidate:
            sweep = max(aligned_sweeps, key=lambda s: s.sweep_index)
            # H6b (decision 2026-06-12-04): freshness is measured at the
            # REJECTION EXTREME (where the sweep actually rejected), not
            # the swept level — trade 11 anchored to a level 47 USD away.
            level = sweep.level.price
            try:
                rejection_candle = m5[sweep.sweep_index]
                level = (
                    rejection_candle.high if candidate is Direction.SHORT
                    else rejection_candle.low
                )
            except (IndexError, TypeError):  # stub/edge: keep swept level
                pass
            return _Anchor(
                "SWEEP_DISPLACEMENT", level=level,
                detail=(
                    f"{sweep.swept_side.value} swept @{sweep.level.price:.2f} "
                    f"rejected @{level:.2f} disp {displacement:.1f}x"
                ),
            )

        # 2/3) FVG / order-block retest (mitigation + favorable close)
        for kind, label in ((ZoneKind.FAIR_VALUE_GAP, "FVG_RETEST"),
                            (ZoneKind.ORDER_BLOCK, "OB_RETEST")):
            zone = self._retested_zone(candidate, m5, zones, kind)
            if zone is not None:
                return _Anchor(
                    label, zone=zone,
                    detail=f"{kind.value} {zone.bottom:.2f}-{zone.top:.2f} "
                           "retested and rejected",
                )

        # 4) break & retest of a broken structure level
        level = self._break_retest_level(candidate, m5, structure, atr5)
        if level is not None:
            return _Anchor("BREAK_RETEST", level=level,
                           detail=f"broken level {level:.2f} retested")

        # 5/6) recent BOS / CHOCH in the trade direction
        events = [
            ev for ev in structure.events
            if ev.bias is want
            and ev.index >= len(m5) - _RECENT_EVENT_WINDOW
        ]
        if events:
            ev = events[-1]
            return _Anchor(
                ev.event_type.value,
                level=ev.price,
                detail=f"{ev.event_type.value} @{ev.price:.2f}",
            )
        return None

    @staticmethod
    def _retested_zone(
        candidate: Direction,
        m5: Sequence[Candle],
        zones: Sequence[Zone],
        kind: ZoneKind,
    ) -> Optional[Zone]:
        """An aligned zone touched within the last few candles with the last
        close back on the favorable side (mitigation + rejection)."""
        want = Bias.BULLISH if candidate is Direction.LONG else Bias.BEARISH
        last = m5[-1]
        recent = list(m5[-_ZONE_TOUCH_WINDOW:])
        candidates = [
            z for z in zones
            if z.kind is kind and z.bias is want
            and any(c.low <= z.top and c.high >= z.bottom for c in recent)
        ]
        for zone in sorted(candidates, key=lambda z: z.created_index,
                           reverse=True):
            if candidate is Direction.LONG and last.close > zone.top:
                return zone
            if candidate is Direction.SHORT and last.close < zone.bottom:
                return zone
        return None

    @staticmethod
    def _break_retest_level(
        candidate: Direction,
        m5: Sequence[Candle],
        structure: StructureResult,
        atr5: float,
    ) -> Optional[float]:
        want = Bias.BULLISH if candidate is Direction.LONG else Bias.BEARISH
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
            if candidate is Direction.LONG:
                touched = any(c.low <= level + tolerance for c in after)
                if touched and last.close > level:
                    return level
            else:
                touched = any(c.high >= level - tolerance for c in after)
                if touched and last.close < level:
                    return level
        return None

    # -- Gate D: local trigger ------------------------------------------------------
    def _entry_trigger(
        self,
        candidate: Direction,
        anchor: _Anchor,
        m5: Sequence[Candle],
        displacement: float,
        disp_direction: Optional[Direction],
    ) -> Optional[str]:
        last = m5[-1]
        directional = (
            last.close > last.open if candidate is Direction.LONG
            else last.close < last.open
        )
        rng = last.high - last.low

        if anchor.label in ("FVG_RETEST", "OB_RETEST") and directional:
            return "MITIGATION_REJECTION"
        if anchor.label == "BREAK_RETEST" and directional:
            return "BREAK_RETEST"
        # pullback rejection: counter-move into the setup, rejected
        if rng > 0:
            if candidate is Direction.SHORT:
                wick = last.high - max(last.open, last.close)
                pulled_back = len(m5) >= 4 and \
                    m5[-2].close >= m5[-4].close  # prior drift against SHORT
            else:
                wick = min(last.open, last.close) - last.low
                pulled_back = len(m5) >= 4 and m5[-2].close <= m5[-4].close
            if wick / rng >= REJECTION_WICK_RATIO and directional and \
                    pulled_back:
                return "PULLBACK_REJECTION"
        # displacement continuation after pullback
        if displacement >= ANCHOR_DISPLACEMENT and \
                disp_direction is candidate and directional:
            return "CONTINUATION"
        return None

    # -- re-entry planning (the anti-freeze rule) -------------------------------------
    @staticmethod
    def _reentry_plan(
        candidate: Direction,
        zones: Sequence[Zone],
        anchor: Optional[_Anchor] = None,
    ) -> Tuple[str, str]:
        """What to wait for next — printed every cycle, refreshed every
        candle. Never a permanent block."""
        want = Bias.BULLISH if candidate is Direction.LONG else Bias.BEARISH
        aligned_fvg = [z for z in zones
                       if z.kind is ZoneKind.FAIR_VALUE_GAP and z.bias is want
                       and not z.mitigated]
        aligned_ob = [z for z in zones
                      if z.kind is ZoneKind.ORDER_BLOCK and z.bias is want
                      and not z.mitigated]
        if anchor is not None and anchor.label in ("FVG_RETEST", "OB_RETEST"):
            return "LOCAL_SWING", (
                "anchor active — wait for a local swing/rejection to form "
                "the tactical stop"
            )
        if aligned_fvg:
            z = aligned_fvg[-1]
            return "FVG_RETEST", (
                f"wait for mitigation of the {want.value.lower()} FVG "
                f"{z.bottom:.2f}-{z.top:.2f}"
            )
        if aligned_ob:
            z = aligned_ob[-1]
            return "OB_RETEST", (
                f"wait for a retest of the {want.value.lower()} order block "
                f"{z.bottom:.2f}-{z.top:.2f}"
            )
        if anchor is not None:
            return "BREAK_RETEST", "wait for a break and retest continuation"
        return "SWEEP", (
            "wait for a liquidity sweep + displacement or a fresh BOS/CHOCH "
            f"in the {candidate.value} direction"
        )

    # -- tactical stop -------------------------------------------------------------
    def _tactical_stop(
        self,
        candidate: Direction,
        entry: float,
        m5: Sequence[Candle],
        m1: Sequence[Candle],
        atr5: float,
        spread: float,
        anchor: _Anchor,
        sweeps,
    ) -> Optional[Tuple[float, float, str, str]]:
        """(price, distance, source, logic): the nearest structurally
        justified invalidation + ATR/spread buffer. None => skip the cycle
        (never a wide HTF structural stop, never an arbitrary wick)."""
        buffer = max(0.25 * atr5, 2.0 * spread, 0.30)
        short = candidate is Direction.SHORT
        candidates: List[Tuple[float, str, str]] = []

        # anchor-zone boundary (the structural invalidation of the setup)
        if anchor.zone is not None:
            level = anchor.zone.top if short else anchor.zone.bottom
            source = ("FVG_boundary" if anchor.zone.kind is
                      ZoneKind.FAIR_VALUE_GAP else "OB_boundary")
            if (short and level > entry) or (not short and level < entry):
                candidates.append((
                    level, source,
                    f"beyond the {anchor.zone.kind.value} boundary "
                    f"{level:.2f} (zone invalidated past it)",
                ))
        # sweep extreme (rejection extreme of the swept level's candle)
        want = Bias.BULLISH if candidate is Direction.LONG else Bias.BEARISH
        aligned = [s for s in sweeps
                   if s.status is SweepStatus.TRUE_SWEEP
                   and s.rejection_bias is want
                   and 0 <= s.sweep_index < len(m5)]
        if aligned:
            sweep = max(aligned, key=lambda s: s.sweep_index)
            extreme = (m5[sweep.sweep_index].high if short
                       else m5[sweep.sweep_index].low)
            if (short and extreme > entry) or (not short and extreme < entry):
                candidates.append((
                    extreme, "rejection_wick",
                    f"beyond the sweep rejection extreme {extreme:.2f} "
                    "(sweep failed past it)",
                ))
        # local M1/M5 swings
        for series, label in ((m1, "local_swing"), (m5, "local_swing")):
            pivot = self._latest_pivot(series, short=short, beyond=entry)
            if pivot is not None:
                candidates.append((
                    pivot, label,
                    f"beyond the local swing {pivot:.2f} "
                    "(structure flips past it)",
                ))

        max_distance = min(MAX_STOP_ABSOLUTE, max(3.0, 3.0 * atr5))
        best: Optional[Tuple[float, float, str, str]] = None
        for level, source, logic in candidates:
            stop_price = level + buffer if short else level - buffer
            distance = (stop_price - entry) if short else (entry - stop_price)
            if distance < MIN_STOP_DISTANCE:
                distance = MIN_STOP_DISTANCE
                stop_price = entry + distance if short else entry - distance
            if distance > max_distance:
                continue
            if best is None or distance < best[1]:
                best = (round(stop_price, 2), round(distance, 2), source,
                        f"{logic} + buffer {buffer:.2f}")
        return best

    @staticmethod
    def _latest_pivot(
        candles: Sequence[Candle], *, short: bool, beyond: float,
        k: int = 2, lookback: int = 40,
    ) -> Optional[float]:
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

    # -- grading / lots ---------------------------------------------------------------
    @staticmethod
    def _grade(in_killzone: bool, anchor: _Anchor, displacement: float,
               mtf: MtfAlignment) -> str:
        if (
            in_killzone
            and anchor.label in ("SWEEP_DISPLACEMENT", "FVG_RETEST",
                                 "OB_RETEST")
            and displacement >= STRONG_DISPLACEMENT
            and mtf.score >= 0.60
        ):
            return SetupGrade.STRONG
        return SetupGrade.NORMAL

    def _fixed_lot(
        self, grade: str, session: SessionType, equity: float,
        stop_distance: float, spread: float,
    ) -> Tuple[Optional[float], str]:
        lot = LOT_STRONG if grade == SetupGrade.STRONG else LOT_NORMAL
        why = (f"{grade} setup -> tier {lot:.2f} "
               f"({'1.5%' if lot == LOT_STRONG else '1.0%'} equity risk)")
        if lot == LOT_STRONG and session in _LOW_LIQUIDITY_SESSIONS:
            lot = LOT_NORMAL
            why = (f"{grade} setup in low-liquidity session {session.value} "
                   f"-> demoted to tier {lot:.2f} (1.0% risk, not blocked)")
        cap = equity * self._limits.max_risk_per_trade
        loss = lot * 100.0 * (stop_distance + spread)
        if loss > cap and lot == LOT_STRONG:
            lot = LOT_NORMAL
            loss = lot * 100.0 * (stop_distance + spread)
            why += (f"; survival cap ${cap:.0f} demotes to {lot:.2f} "
                    f"(loss-at-stop ${loss:.0f})")
        if loss > cap:
            return None, (
                f"tactical stop {stop_distance:.2f} risks ${loss:.0f} at "
                f"{lot:.2f} lot, over the survival cap ${cap:.0f}; skip and "
                "rescan next candle"
            )
        return lot, why

    # -- assembly ------------------------------------------------------------------
    def _decision(
        self, symbol, now, candidate, entry, stop_price, stop_distance,
        anchor: _Anchor, trigger: str, grade: str, lot: float,
        liquidity_context: str,
    ) -> TradeDecision:
        target = (
            entry - 2.0 * stop_distance if candidate is Direction.SHORT
            else entry + 2.0 * stop_distance
        )
        return TradeDecision(
            decision_id=f"smc-{now.strftime('%Y%m%dT%H%M%S')}Z",
            time_utc=now,
            symbol=symbol,
            direction=candidate,
            status=DecisionStatus.PROPOSED,
            setup_type=SETUP_TYPE_TEMPLATE.format(
                anchor=anchor.label.lower(), grade=grade, lot=lot,
            ),
            thesis=(
                f"smc_challenge {grade} {candidate.value}: {anchor.label} "
                f"({anchor.detail}); trigger {trigger}; liquidity "
                f"{liquidity_context}; tactical local invalidation"
            ),
            invalidation_price=stop_price,
            entry_price=entry,
            stop_loss=stop_price,
            take_profits=(round(target, 2),),
            confidence=0.80 if grade == SetupGrade.STRONG else 0.65,
            uncertainty=0.20 if grade == SetupGrade.STRONG else 0.30,
            reason=f"{grade} {anchor.label} via {trigger}",
        )

    @staticmethod
    def _confidence(grade: str, anchor: _Anchor, trigger: str) -> ConfidenceResult:
        strong = grade == SetupGrade.STRONG
        return ConfidenceResult(
            confidence=0.80 if strong else 0.65,
            uncertainty=0.20 if strong else 0.30,
            recommendation=ScoreRecommendation.ALLOW,
            size_factor=1.0,
            reason=f"smc {grade}: {anchor.label} via {trigger}",
        )

    def _context(self, session, htf_bias, structure_bias, candidate,
                 smc: dict) -> PipelineContext:
        return PipelineContext(
            session=session,
            htf_bias=htf_bias,
            regime=Regime.TREND if candidate is not None else Regime.RANGE,
            structure_bias=structure_bias,
            has_setup=candidate is not None,
            regime_reason="smc_challenge A+B+C+D gate evaluation",
            challenge=smc,
        )

    def _wait(self, context, smc: dict, reason: str, *, waiting: str = "",
              plan: str = "") -> PipelineResult:
        smc["reason"] = reason
        smc["waiting_for"] = waiting
        smc["reentry_plan"] = plan or smc.get("reentry_plan", "")
        return PipelineResult(
            stage=PipelineStage.HYPOTHESIS, approved=False,
            reason=reason, context=context,
        )

    # -- shared helpers ----------------------------------------------------------
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
    def _b(bias: Optional[Bias]) -> str:
        return bias.value if bias is not None else "-"

    @staticmethod
    def _m1_state(m1: Sequence[Candle]) -> Optional[str]:
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
    def _displacement(
        candles: Sequence[Candle], body_window: int = 8, range_window: int = 20
    ) -> Tuple[float, Optional[Direction]]:
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
        direction = (
            Direction.LONG if biggest.close > biggest.open
            else Direction.SHORT if biggest.close < biggest.open
            else None
        )
        return ratio, direction

    def _detect_new_candle(self, m5, m1) -> str:
        m5_time = m5[-1].time_utc if m5 else None
        m1_time = m1[-1].time_utc if m1 else None
        fresh = (
            (m5_time is not None and m5_time != self._last_m5_time)
            or (m1_time is not None and m1_time != self._last_m1_time)
        )
        first = self._last_m5_time is None and self._last_m1_time is None
        self._last_m5_time = m5_time
        self._last_m1_time = m1_time
        if first:
            return "first_cycle"
        return "yes" if fresh else "no"

    @staticmethod
    def _aggregate(m5: Sequence[Candle], target: Timeframe) -> List[Candle]:
        try:
            return list(aggregate(m5, target))
        except (AggregationError, ValueError):
            return []

    @staticmethod
    def _atr(candles: Sequence[Candle], period: int = 14) -> float:
        window = list(candles[-period:])
        if not window:
            return 0.0
        return sum(c.high - c.low for c in window) / len(window)


def make_smc_pipeline(
    canonical_symbol: str,
    *,
    max_spread_price: float = 1.0,
    max_staleness: timedelta = timedelta(minutes=30),
) -> SmcExecutionPipeline:
    """Build the SMC execution pipeline for LIVE XAUUSDm data."""
    canonical = canonical_symbol.strip().upper()
    engines = SmcEngines(
        validator=DataValidator(ValidationConfig(
            expected_symbol=canonical,
            detect_gaps=False,
            max_staleness=max_staleness,
        )),
    )
    return SmcExecutionPipeline(
        make_challenge_limits(canonical),
        max_spread=max_spread_price,
        engines=engines,
    )
