"""Aggressive demo-challenge momentum pipeline (Task DEMO-CHALLENGE-001).

DEMO ONLY. This pipeline exists for ONE purpose: test whether the system can
aggressively capture XAUUSD momentum on a ~$2,000 Exness MT5 DEMO account.
It is the decision engine behind `--profile demo_challenge` and is NEVER used
by any other profile; the institutional DecisionPipeline is untouched.

Why it exists (live evidence, 2026-06-10/11): the institutional model ran
570+ cycles, read the bearish direction correctly, and took ZERO trades —
the dominant blocker was STOP_TOO_WIDE_FOR_ACCOUNT: a huge HTF structural
stop combined with a defensive 0.20% budget on $2,000. It kept repeating the
same stale structural-stop verdict for hours while fresh M1/M5 structure
formed every candle.

Mindset of this pipeline (the DEMO-CHALLENGE-001 correction):
- Every new candle is a NEW execution opportunity check.
- Warmstart/HTF context never locks the entry or the stop: the tactical stop
  is recomputed from CURRENT local M1/M5 structure on every cycle.
- One simple question per cycle: "is there enough current momentum + a local
  invalidation to take a demo trade?" If yes — trade. If no — print exactly
  what is missing.
- Fixed lots only: 0.05 for NORMAL momentum, 0.10 for STRONG momentum
  (low liquidity demotes 0.10 -> 0.05 but never blocks alone).
- No macro/futures/news-calendar dependency: unavailable reads NEUTRAL and
  never blocks (only the operator NEWS_BLOCK file / HIGH-impact-active state
  blocks, enforced in the challenge planner).

What it deliberately KEEPS from the safety stack:
- stop-loss mandatory (tactical local structure, never removed),
- the RiskGovernor still evaluates every candidate (final authority),
- no martingale / averaging down / grid / opposite-direction hedging
  (enforced by ChallengeTradePlanner + governor + gateway),
- the kill switch and the ExecutionGateway remain the only order pathway,
- the demo_challenge survival envelope (3% per trade worst case, 5% daily,
  10% weekly, max 3 open positions) — an account-survival guard, not
  conservative sizing.

This module never sends orders and holds no credentials.
"""

from __future__ import annotations

from datetime import timedelta
from typing import List, Optional, Sequence, Tuple

from src.data.aggregation import AggregationError, aggregate
from src.data.enums import DecisionStatus, Direction, Timeframe
from src.data.schemas import Candle, TradeDecision
from src.data.sessions import SessionEngine, SessionType
from src.data.validation import DataValidator, ValidationConfig, ValidationStatus
from src.regime.htf_bias import HtfBias
from src.regime.regime_engine import Regime
from src.risk.governor import RiskContext, RiskGovernor, RiskLimits
from src.strategy.pipeline import (
    PipelineContext,
    PipelineInput,
    PipelineResult,
    PipelineStage,
)
from src.strategy.scoring import ConfidenceResult, ScoreRecommendation
from src.structure.market_structure import Bias

# Fixed challenge lots (the ONLY lots this profile trades; 0.01 exists solely
# as the planner's margin-rejection fallback, never as a default).
LOT_NORMAL = 0.05
LOT_STRONG = 0.10

# setup_type carries the pipeline's lot choice to the challenge planner in a
# parseable, journaled, human-readable form (single source of truth).
SETUP_TYPE_TEMPLATE = "challenge_{plan}[{state},lot={lot:.2f}]"

# Momentum classification thresholds (M5 displacement = max recent body over
# the median candle range; the same scale the institutional pipeline uses).
STRONG_DISPLACEMENT = 1.6
MIN_DISPLACEMENT = 1.1

# Tactical stop geometry (price units, USD on XAUUSD).
MIN_STOP_DISTANCE = 0.50          # never tighter than this (noise floor)
MAX_STOP_ABSOLUTE = 8.0           # a tactical stop is LOCAL; never $150-wide
REJECTION_WICK_RATIO = 0.45       # wick share of range that reads as rejection

# Sessions where a 0.10 lot is demoted to 0.05 (never a block by itself).
_LOW_LIQUIDITY_SESSIONS = {
    SessionType.ROLLOVER,
    SessionType.LOW_LIQUIDITY,
    SessionType.CLOSED,
}


class MomentumState:
    STRONG = "STRONG"
    NORMAL = "NORMAL"
    WEAK = "WEAK"


def make_challenge_limits(expected_symbol: str) -> RiskLimits:
    """RiskLimits for the demo_challenge envelope (owner-directed, DEMO only).

    Imported lazily from session_profiles values would create an import cycle;
    the profile in session_profiles carries the same numbers and tests pin
    them to each other.
    """
    return RiskLimits(
        expected_symbol=expected_symbol,
        max_risk_per_trade=0.030,
        max_daily_loss=0.05,
        max_weekly_loss=0.10,
        max_trades_per_day=10,
        max_open_trades=3,
        max_spread=1.0,
    )


class ChallengeMomentumPipeline:
    """Simplified momentum decision engine. Same decide() interface as
    DecisionPipeline, so SupervisedDemoSession / TradingService drive it
    unchanged (gateway, journal, reconciliation, trailing all reused)."""

    def __init__(
        self,
        limits: RiskLimits,
        *,
        max_spread: float = 1.0,
        validator: Optional[DataValidator] = None,
        session_engine: Optional[SessionEngine] = None,
    ) -> None:
        if max_spread <= 0:
            raise ValueError("max_spread must be > 0")
        self._limits = limits
        self._governor = RiskGovernor(limits)
        self._max_spread = max_spread
        self._validator = validator or DataValidator()
        self._session = session_engine or SessionEngine()
        self.threshold_profile = "demo_challenge"
        # Fresh-entry scan state: every new candle re-arms the search.
        self._last_m5_time = None
        self._last_m1_time = None
        self._last_stop_price: Optional[float] = None

    # -- public ------------------------------------------------------------
    def decide(self, inp: PipelineInput) -> PipelineResult:
        now = inp.now or (
            inp.exec_candles[-1].time_utc if inp.exec_candles else None
        )
        report = self._validator.validate_candles(inp.exec_candles, now=now)
        if report.status is not ValidationStatus.VALID:
            return PipelineResult(
                stage=PipelineStage.DATA_REJECTED, approved=False,
                reason=(
                    "data rejected: "
                    f"{[i.code.value for i in report.blocking_issues]}"
                ),
            )

        m5 = list(inp.exec_candles)
        m15 = list(inp.m15_candles) if inp.m15_candles else self._aggregate_m15(m5)
        m1 = list(inp.m1_candles) if inp.m1_candles else []
        last = m5[-1]
        entry = last.close
        session = self._session.classify(now)
        spread = max(inp.current_spread, 0.0)
        equity = inp.broker.equity or inp.broker.balance or 0.0

        new_candle = self._detect_new_candle(m5, m1)
        atr5 = self._atr(m5)

        m15_bias = self._bias(m15)
        m5_bias = self._bias(m5)
        displacement, disp_direction = self._displacement(m5)
        m1_disp, m1_dir = self._displacement(m1) if len(m1) >= 10 else (0.0, None)

        candidate, state, momentum_why = self._classify_momentum(
            m15_bias, m5_bias, displacement, disp_direction, m1_disp, m1_dir
        )
        entry_plan = (
            self._entry_trigger(candidate, m5) if candidate is not None else "wait"
        )

        challenge = {
            "profile": "demo_challenge",
            "fresh_entry_scan": "ACTIVE",
            "new_candle_detected": new_candle,
            "local_structure_updated": "no",
            "direction": candidate.value if candidate else "NONE",
            "momentum_state": state,
            "m15_bias": m15_bias.value,
            "m5_bias": m5_bias.value,
            "displacement": round(displacement, 2),
            "m1_displacement": round(m1_disp, 2),
            "entry_plan": entry_plan,
            "tactical_stop_price": None,
            "tactical_stop_distance": None,
            "tactical_stop_source": "none",
            "lot_decision": "NONE",
            "reason": "",
        }
        context = self._context(session, m15_bias, m5_bias, candidate, challenge)

        # The one simple question, answered in order of what is missing.
        if spread > self._max_spread:
            return self._wait(
                context, challenge,
                f"spread too high ({spread:.3f} > {self._max_spread:.3f})",
            )
        if equity <= 0:
            return self._wait(context, challenge, "account equity unknown")
        if candidate is None or state == MomentumState.WEAK:
            return self._wait(context, challenge, f"momentum weak ({momentum_why})")
        if entry_plan == "wait":
            return self._wait(
                context, challenge,
                "waiting for break/retest (momentum present but no breakout, "
                "pullback rejection, or displacement continuation trigger)",
            )

        stop = self._tactical_stop(candidate, entry, m5, m1, atr5, spread)
        if stop is None:
            return self._wait(
                context, challenge,
                "waiting for local swing stop (no valid M1/M5 local "
                f"invalidation within {MAX_STOP_ABSOLUTE:.1f} USD; a wide "
                "structural stop is NOT used in demo_challenge)",
            )
        stop_price, stop_distance, stop_source = stop
        if self._last_stop_price != stop_price:
            challenge["local_structure_updated"] = "yes"
            self._last_stop_price = stop_price
        challenge.update(
            tactical_stop_price=round(stop_price, 2),
            tactical_stop_distance=round(stop_distance, 2),
            tactical_stop_source=stop_source,
        )

        lot, lot_why = self._fixed_lot(
            state, session, equity, stop_distance, spread
        )
        if lot is None:
            return self._wait(context, challenge, lot_why)
        challenge["lot_decision"] = f"{lot:.2f}"

        decision = self._decision(
            inp.symbol, now, candidate, entry, stop_price, stop_distance,
            state, entry_plan, lot, momentum_why,
        )
        confidence = self._confidence(state, momentum_why)
        challenge["reason"] = (
            f"{state} {candidate.value} momentum via {entry_plan}; "
            f"tactical stop {stop_source} @{stop_price:.2f} "
            f"({stop_distance:.2f}); {lot_why}"
        )

        # Risk Governor: final authority, challenge envelope limits.
        # protected_addon=True here only keeps the PIPELINE's duplicate check
        # from pre-blocking add-on candidates; the ChallengeTradePlanner and
        # the gateway re-run the authoritative add-on gates (first trade in
        # floating profit, same direction, max 3) before anything is sent.
        verdict = self._governor.evaluate(decision, RiskContext(
            broker=inp.broker,
            current_spread=spread,
            lot_size=lot,
            intended_risk_pct=(
                lot * 100.0 * (stop_distance + spread) / equity
            ),
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

    # -- momentum ------------------------------------------------------------
    @staticmethod
    def _bias(candles: Sequence[Candle], n: int = 20) -> Bias:
        closes = [c.close for c in candles]
        if len(closes) < n + 1:
            return Bias.NEUTRAL
        sma = sum(closes[-n:]) / n
        last = closes[-1]
        net = last - closes[-(n + 1)]
        if last > sma and net > 0:
            return Bias.BULLISH
        if last < sma and net < 0:
            return Bias.BEARISH
        return Bias.NEUTRAL

    @staticmethod
    def _displacement(
        candles: Sequence[Candle], body_window: int = 8, range_window: int = 20
    ) -> Tuple[float, Optional[Direction]]:
        """Max recent body over the median range + that body's direction."""
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

    def _classify_momentum(
        self,
        m15_bias: Bias,
        m5_bias: Bias,
        displacement: float,
        disp_direction: Optional[Direction],
        m1_disp: float,
        m1_dir: Optional[Direction],
    ) -> Tuple[Optional[Direction], str, str]:
        """LONG/SHORT candidate + STRONG/NORMAL/WEAK + why."""
        aligned = m15_bias is m5_bias and m15_bias is not Bias.NEUTRAL
        if aligned:
            candidate = (
                Direction.LONG if m5_bias is Bias.BULLISH else Direction.SHORT
            )
            if displacement >= STRONG_DISPLACEMENT and disp_direction is candidate:
                return candidate, MomentumState.STRONG, (
                    f"M15+M5 aligned {m5_bias.value} with displacement "
                    f"{displacement:.1f}x"
                )
            return candidate, MomentumState.NORMAL, (
                f"M15+M5 aligned {m5_bias.value} "
                f"(displacement {displacement:.1f}x)"
            )
        # Displacement path: M5 directional drive, M1 (when present) agreeing.
        if (
            m5_bias is not Bias.NEUTRAL
            and displacement >= MIN_DISPLACEMENT
            and disp_direction is not None
            and (
                (m5_bias is Bias.BULLISH and disp_direction is Direction.LONG)
                or (m5_bias is Bias.BEARISH and disp_direction is Direction.SHORT)
            )
            and (m1_dir is None or m1_dir is disp_direction)
        ):
            state = (
                MomentumState.STRONG
                if displacement >= STRONG_DISPLACEMENT and m1_dir is disp_direction
                else MomentumState.NORMAL
            )
            return disp_direction, state, (
                f"M5 {m5_bias.value} displacement {displacement:.1f}x"
                + (f" with M1 agreement ({m1_disp:.1f}x)" if m1_dir else "")
            )
        return None, MomentumState.WEAK, (
            f"m15={m15_bias.value} m5={m5_bias.value} "
            f"displacement={displacement:.1f}x — no aligned drive"
        )

    @staticmethod
    def _entry_trigger(candidate: Direction, m5: Sequence[Candle]) -> str:
        """breakout | pullback_rejection | continuation | wait."""
        if len(m5) < 14:
            return "wait"
        last = m5[-1]
        prior = list(m5[-13:-1])
        rng = last.high - last.low
        if candidate is Direction.SHORT:
            if last.close < min(c.low for c in prior):
                return "breakout"
            upper_wick = last.high - max(last.open, last.close)
            if rng > 0 and upper_wick / rng >= REJECTION_WICK_RATIO \
                    and last.close <= last.open:
                return "pullback_rejection"
            if last.close < last.open and (last.open - last.close) >= 0.5 * rng:
                return "continuation"
            return "wait"
        if last.close > max(c.high for c in prior):
            return "breakout"
        lower_wick = min(last.open, last.close) - last.low
        if rng > 0 and lower_wick / rng >= REJECTION_WICK_RATIO \
                and last.close >= last.open:
            return "pullback_rejection"
        if last.close > last.open and (last.close - last.open) >= 0.5 * rng:
            return "continuation"
        return "wait"

    # -- tactical stop ---------------------------------------------------------
    def _tactical_stop(
        self,
        candidate: Direction,
        entry: float,
        m5: Sequence[Candle],
        m1: Sequence[Candle],
        atr5: float,
        spread: float,
    ) -> Optional[Tuple[float, float, str]]:
        """(stop_price, distance, source) from CURRENT local structure.

        Candidates, nearest valid first: M1 local swing, M5 local swing,
        last-candle rejection extreme, recent pullback extreme — each plus an
        ATR/spread buffer. No candidate within MAX_STOP_ABSOLUTE => None
        (skip the cycle; never fall back to a huge structural stop).
        """
        buffer = max(0.25 * atr5, 2.0 * spread, 0.30)
        short = candidate is Direction.SHORT
        candidates: List[Tuple[float, str]] = []

        for series, label in ((m1, "m1_local_swing"), (m5, "m5_local_swing")):
            pivot = self._latest_pivot(series, short=short, beyond=entry)
            if pivot is not None:
                candidates.append((pivot, label))
        last = m5[-1]
        rejection = last.high if short else last.low
        if (short and rejection > entry) or (not short and rejection < entry):
            candidates.append((rejection, "rejection_wick"))
        pullback_window = list(m5[-6:])
        pullback = (
            max(c.high for c in pullback_window) if short
            else min(c.low for c in pullback_window)
        )
        if (short and pullback > entry) or (not short and pullback < entry):
            candidates.append((pullback, "pullback_extreme"))

        max_distance = min(MAX_STOP_ABSOLUTE, max(3.0, 3.0 * atr5))
        best: Optional[Tuple[float, float, str]] = None
        for level, source in candidates:
            stop_price = level + buffer if short else level - buffer
            distance = (stop_price - entry) if short else (entry - stop_price)
            if distance < MIN_STOP_DISTANCE:
                distance = MIN_STOP_DISTANCE
                stop_price = (
                    entry + distance if short else entry - distance
                )
            if distance > max_distance:
                continue
            if best is None or distance < best[1]:
                best = (round(stop_price, 2), round(distance, 2), source)
        return best

    @staticmethod
    def _latest_pivot(
        candles: Sequence[Candle], *, short: bool, beyond: float,
        k: int = 2, lookback: int = 40,
    ) -> Optional[float]:
        """Most recent k-pivot swing high (short) / low (long) past `beyond`."""
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

    # -- fixed lot ---------------------------------------------------------------
    def _fixed_lot(
        self,
        state: str,
        session: SessionType,
        equity: float,
        stop_distance: float,
        spread: float,
    ) -> Tuple[Optional[float], str]:
        """0.10 for STRONG / 0.05 for NORMAL; low liquidity demotes 0.10 ->
        0.05; the survival cap (max_risk_per_trade) demotes then skips. The
        planner may additionally fall back to 0.01 ONLY on a margin refusal.
        """
        lot = LOT_STRONG if state == MomentumState.STRONG else LOT_NORMAL
        why = f"{state} momentum -> fixed lot {lot:.2f}"
        if lot == LOT_STRONG and session in _LOW_LIQUIDITY_SESSIONS:
            lot = LOT_NORMAL
            why = (
                f"{state} momentum in low-liquidity session "
                f"{session.value} -> demoted to {lot:.2f} (not blocked)"
            )
        cap = equity * self._limits.max_risk_per_trade
        loss = lot * 100.0 * (stop_distance + spread)
        if loss > cap and lot == LOT_STRONG:
            lot = LOT_NORMAL
            loss = lot * 100.0 * (stop_distance + spread)
            why += (
                f"; survival cap ${cap:.0f} demotes to {lot:.2f} "
                f"(loss-at-stop ${loss:.0f})"
            )
        if loss > cap:
            return None, (
                f"tactical stop {stop_distance:.2f} risks ${loss:.0f} at "
                f"{lot:.2f} lot, over the survival cap ${cap:.0f} "
                f"({self._limits.max_risk_per_trade:.1%}); skip this cycle "
                "and wait for a tighter local stop"
            )
        return lot, why

    # -- assembly -----------------------------------------------------------------
    def _decision(
        self,
        symbol: str,
        now,
        candidate: Direction,
        entry: float,
        stop_price: float,
        stop_distance: float,
        state: str,
        entry_plan: str,
        lot: float,
        momentum_why: str,
    ) -> TradeDecision:
        target = (
            entry - 2.0 * stop_distance if candidate is Direction.SHORT
            else entry + 2.0 * stop_distance
        )
        return TradeDecision(
            decision_id=f"chal-{now.strftime('%Y%m%dT%H%M%S')}Z",
            time_utc=now,
            symbol=symbol,
            direction=candidate,
            status=DecisionStatus.PROPOSED,
            setup_type=SETUP_TYPE_TEMPLATE.format(
                plan=entry_plan, state=state, lot=lot
            ),
            thesis=(
                f"demo_challenge {state} {candidate.value} momentum: "
                f"{momentum_why}; {entry_plan} entry with tactical local stop"
            ),
            invalidation_price=stop_price,
            entry_price=entry,
            stop_loss=stop_price,
            take_profits=(round(target, 2),),
            confidence=0.80 if state == MomentumState.STRONG else 0.65,
            uncertainty=0.20 if state == MomentumState.STRONG else 0.30,
            reason=f"{state} momentum {entry_plan}",
        )

    @staticmethod
    def _confidence(state: str, why: str) -> ConfidenceResult:
        strong = state == MomentumState.STRONG
        return ConfidenceResult(
            confidence=0.80 if strong else 0.65,
            uncertainty=0.20 if strong else 0.30,
            recommendation=ScoreRecommendation.ALLOW,
            size_factor=1.0,
            reason=f"demo_challenge momentum {state}: {why}",
        )

    def _context(
        self,
        session: SessionType,
        m15_bias: Bias,
        m5_bias: Bias,
        candidate: Optional[Direction],
        challenge: dict,
    ) -> PipelineContext:
        htf = (
            HtfBias.BULLISH if m15_bias is Bias.BULLISH
            else HtfBias.BEARISH if m15_bias is Bias.BEARISH
            else HtfBias.NEUTRAL
        )
        regime = Regime.TREND if candidate is not None else Regime.RANGE
        return PipelineContext(
            session=session,
            htf_bias=htf,
            regime=regime,
            structure_bias=m5_bias,
            has_setup=candidate is not None,
            regime_reason="demo_challenge momentum read (no regime gating)",
            challenge=challenge,
        )

    def _wait(
        self, context: PipelineContext, challenge: dict, reason: str
    ) -> PipelineResult:
        challenge["reason"] = reason
        return PipelineResult(
            stage=PipelineStage.HYPOTHESIS, approved=False,
            reason=reason, context=context,
        )

    def _detect_new_candle(
        self, m5: Sequence[Candle], m1: Sequence[Candle]
    ) -> str:
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
    def _aggregate_m15(m5: Sequence[Candle]) -> List[Candle]:
        try:
            return list(aggregate(m5, Timeframe.M15))
        except (AggregationError, ValueError):
            return []

    @staticmethod
    def _atr(candles: Sequence[Candle], period: int = 14) -> float:
        window = list(candles[-period:])
        if not window:
            return 0.0
        return sum(c.high - c.low for c in window) / len(window)


def make_challenge_pipeline(
    canonical_symbol: str,
    *,
    max_spread_price: float = 1.0,
    max_staleness: timedelta = timedelta(minutes=30),
) -> ChallengeMomentumPipeline:
    """Build the demo_challenge pipeline for LIVE XAUUSDm data.

    Mirrors make_live_pipeline's data handling: session gaps are not blocking
    (the session engine owns sessions) and a stale feed is rejected.
    """
    canonical = canonical_symbol.strip().upper()
    return ChallengeMomentumPipeline(
        make_challenge_limits(canonical),
        max_spread=max_spread_price,
        validator=DataValidator(ValidationConfig(
            expected_symbol=canonical,
            detect_gaps=False,
            max_staleness=max_staleness,
        )),
    )
