"""SMC v2 decision brain (SMC-V2-001, decision 2026-06-12-10). DEMO ONLY.

Narrative-driven decision layer per 26_SMC_V2_DESIGN.md: the DAY is
classified first (DayNarrativeEngine), playbooks are selected per state,
and a candidate must pass a quality score — instead of v1's stateless
per-candle gate checks.

Reused UNCHANGED from SmcExecutionPipeline (the proven chassis-facing
helpers): data validation, anchor detection, entry triggers, tactical
stop construction (8 USD ceiling), H8 zone consumption, equity-risk lot
tiers, RiskGovernor evaluation, TradeDecision assembly. The envelope
(make_challenge_limits) is shared, never widened.

New in v2:
- DayNarrative gate: untradeable states (POST_SPIKE_CHOP, EXHAUSTED,
  OPENING) refuse entries with an explicit re-arm condition.
- Conviction gate: |conviction| >= CONVICTION_ENTRY_MIN and sign
  agreement with the candidate direction.
- Playbooks: TREND_CONTINUATION / SWEEP_RECLAIM / RANGE_FADE, each with
  its own anchor requirements; counter-narrative directions can never
  trade (no D3/D5 patching needed — the narrative IS the trend logic).
- Trade memory: max 2 SL losses per direction per day (a third attempt
  requires a fresh held reclaim); a playbook with 2 SL losses in a day
  stands down for the day.
- Quality score in [0,1]; entry >= S_NORMAL, STRONG tier >= S_STRONG.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from src.data.enums import Direction, Timeframe
from src.data.validation import ValidationStatus
from src.liquidity.sweep import SweepStatus
from src.regime.chop_classifier import ChopSubtype
from src.risk.governor import RiskContext
from src.strategy.day_narrative import (
    CONVICTION_ENTRY_MIN,
    DayNarrativeEngine,
    DayState,
    PB_RANGE_FADE,
    PB_SWEEP_RECLAIM,
    PB_TREND_CONTINUATION,
)
from src.strategy.pipeline import (
    PipelineInput,
    PipelineResult,
    PipelineStage,
)
from src.strategy.smc_execution import (
    LOT_STRONG,
    STALE_ANCHOR_ATR_MULT,
    SetupGrade,
    SmcExecutionPipeline,
)
from src.structure.market_structure import Bias

# Entry bar 0.62: an off-hours setup with only a naked local-swing stop
# (conviction 0.21 + event 0.15 + freshness 0.15 + stop 0.07 + timing
# 0.02 = 0.60) must NOT clear it — that is the low-liquidity loss class
# of 2026-06-11 (trades 2/3). Kill-zone timing or a structural stop
# source is required to cross it. Tuned only by replay evidence.
S_NORMAL = 0.62
S_STRONG = 0.78
PROBE_LIMIT_PER_DIRECTION = 2   # SL losses; a 3rd needs a fresh reclaim
PLAYBOOK_DAY_LIMIT = 2          # SL losses; the playbook stands down
SWEEP_FRESH_CANDLES = 12        # M5 candles for a reclaim to count as fresh
RANGE_FADE_EXTREME_PCT = 0.30   # entry within this fraction of the extreme


class SmcV2Pipeline(SmcExecutionPipeline):
    """Day-narrative + playbook + quality-score decision brain."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.threshold_profile = "smc_v2"
        self._narrator = DayNarrativeEngine()
        self._memory_day = None
        self._sl_losses_by_direction: Dict[Direction, int] = {}
        self._sl_losses_by_playbook: Dict[str, int] = {}
        self._playbook_by_direction: Dict[Direction, str] = {}

    # -- trade memory -----------------------------------------------------
    def note_stop_loss(self, direction, stop_price, time_utc) -> None:
        super().note_stop_loss(direction, stop_price, time_utc)
        if direction is None:
            return
        # the note may arrive before the first decide() of the day
        if time_utc is not None:
            self._reset_memory_on_new_day(time_utc)
        self._sl_losses_by_direction[direction] = (
            self._sl_losses_by_direction.get(direction, 0) + 1
        )
        playbook = self._playbook_by_direction.get(direction)
        if playbook:
            self._sl_losses_by_playbook[playbook] = (
                self._sl_losses_by_playbook.get(playbook, 0) + 1
            )

    def _reset_memory_on_new_day(self, now) -> None:
        day = now.date() if now is not None else None
        if day != self._memory_day:
            self._memory_day = day
            self._sl_losses_by_direction.clear()
            self._sl_losses_by_playbook.clear()
            self._playbook_by_direction.clear()

    # -- decision ----------------------------------------------------------
    def decide(self, inp: PipelineInput) -> PipelineResult:  # noqa: C901
        e = self._e
        now = inp.now or (
            inp.exec_candles[-1].time_utc if inp.exec_candles else None
        )
        self._reset_memory_on_new_day(now)
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
        h1 = list(inp.h1_candles) if inp.h1_candles else []
        m1 = list(inp.m1_candles) if inp.m1_candles else []
        last = m5[-1]
        entry = last.close
        session = e.session.classify(now)
        spread = max(inp.current_spread, 0.0)
        equity = inp.broker.equity or inp.broker.balance or 0.0
        atr5 = self._atr(m5)
        new_candle = self._detect_new_candle(m5, m1)

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

        # -- narrative ------------------------------------------------------
        swept_levels, reclaim_held, fresh_reclaim = self._sweep_story(
            m5, sweeps
        )
        htf_direction = mtf.direction or self._htf_direction(htf_bias)
        narrative = self._narrator.narrate(
            m5, asian=asian, htf_direction=htf_direction,
            swept_levels=swept_levels, reclaim_held=reclaim_held,
            reclaim_fresh=fresh_reclaim,
        )

        killzone = session.value
        in_killzone = session in self._kill_zones()
        liquidity_context = self._liquidity_context(
            narrative.direction or htf_direction or Direction.LONG,
            asian, sweeps, liquidity_map, entry,
        )
        smc = {
            "mode": "smc_v2",
            "profile": "smc_v2",
            "fresh_entry_scan": "ACTIVE",
            "new_candle_detected": new_candle,
            "local_structure_updated": "no",
            "direction": "NONE",
            "grade": "NONE",
            "htf_context": (
                f"d1={self._b(mtf.d1)} h4={self._b(mtf.h4)} "
                f"h1={self._b(mtf.h1)} m15={self._b(mtf.m15)} "
                f"m5={self._b(mtf.m5)} mtf_score={mtf.score:.2f} "
                f"htf_bias={htf_bias.value}"
            ),
            "killzone": killzone,
            "liquidity_context": liquidity_context,
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
            "narrative": (
                f"{narrative.state.value}"
                f"{'/' + narrative.direction.value if narrative.direction else ''}"
                f" conviction={narrative.conviction:+.2f}"
                f" playbooks={','.join(narrative.allowed_playbooks) or '-'}"
                f" evidence[{'; '.join(narrative.evidence)}]"
            ),
        }
        context = self._context(session, htf_bias, structure.final_bias,
                                narrative.direction, smc)

        if spread > self._max_spread:
            return self._wait(
                context, smc,
                f"spread too high ({spread:.3f} > {self._max_spread:.3f})",
            )
        if equity <= 0:
            return self._wait(context, smc, "account equity unknown")

        # -- hard safety gate (kept from D6): dangerous volatility -----------
        environment = m5[:-1] if len(m5) > 1 else m5
        spread_ratio = spread / self._max_spread if self._max_spread else 0.0
        vol = e.volatility.classify(environment, spread_ratio=spread_ratio)
        chop = e.chop.classify(
            environment, sweeps, spread_ratio=spread_ratio,
            directional_score=mtf.score,
        )
        smc["market_state"] = (
            f"vol={vol.state.value} chop={chop.subtype.value}"
        )
        if vol.dangerous:
            return self._wait(
                context, smc,
                f"VOLATILITY_BLOCK: {vol.state.value} — {vol.reason}",
                waiting="SWEEP",
                plan="wait for volatility to normalize",
            )

        # -- narrative gate ---------------------------------------------------
        if not narrative.tradeable:
            return self._wait(
                context, smc,
                f"DAY_NARRATIVE_{narrative.state.value}: no playbook is "
                f"armed — {narrative.rearm_condition}",
                waiting="SWEEP",
                plan=narrative.rearm_condition,
            )

        # -- conviction gate ----------------------------------------------------
        candidate = self._candidate_from(narrative)
        if candidate is None:
            return self._wait(
                context, smc,
                f"CONVICTION_INSUFFICIENT: {narrative.conviction:+.2f} "
                f"(need |c| >= {CONVICTION_ENTRY_MIN:.2f} agreeing with an "
                f"allowed direction {[d.value for d in narrative.allowed_directions]})",
                waiting="SWEEP",
                plan="wait for the day evidence to agree with a playbook "
                     "direction",
            )
        smc["direction"] = candidate.value

        # -- trade memory: probe limit per direction --------------------------
        # Replay-confirmed (2026-06-08, +5.3R down-day): trend days pay for
        # persistence — two pullback stop-outs must not lock out the whole
        # trend. WITH an established trend the limit is doubled; against or
        # without one it stays 2.
        probes = self._sl_losses_by_direction.get(candidate, 0)
        # TREND_DAY only. Replay-measured (12 days): extending the
        # relaxation to TRAP_REVERSAL cost ~6R net (87 trades, +4.92)
        # versus the strict form (82 trades, +10.90) — extra trap-state
        # probes do not pay.
        aligned_trend = (
            narrative.state is DayState.TREND_DAY
            and narrative.direction is candidate
        )
        probe_limit = (
            PROBE_LIMIT_PER_DIRECTION * 2 if aligned_trend
            else PROBE_LIMIT_PER_DIRECTION
        )
        if probes >= probe_limit and not fresh_reclaim:
            return self._wait(
                context, smc,
                f"PROBE_LIMIT: {probes} stop-outs {candidate.value} today — "
                "a third attempt requires a FRESH key-level sweep+reclaim",
                waiting="SWEEP",
                plan="wait for a fresh sweep+reclaim in the candidate "
                     "direction",
            )

        # -- playbook selection -------------------------------------------------
        playbook, anchor, trigger, why_blocked = self._select_playbook(
            narrative, candidate, m5, structure, sweeps, zones,
            displacement, disp_direction, atr5, reclaim_held, entry,
        )
        if playbook is None:
            waiting, plan = self._reentry_plan(candidate, zones)
            return self._wait(
                context, smc,
                why_blocked or "no playbook setup present",
                waiting=waiting, plan=plan,
            )
        smc["smc_anchor"] = anchor.label
        smc["entry_trigger"] = trigger
        smc["playbook"] = playbook

        # -- stale anchor (D2, kept) -------------------------------------------
        if (
            anchor.level is not None and atr5 > 0
            and abs(entry - anchor.level) > STALE_ANCHOR_ATR_MULT * atr5
        ):
            waiting, plan = self._reentry_plan(candidate, zones, anchor)
            return self._wait(
                context, smc,
                f"SMC_ANCHOR_STALE: {anchor.label} level {anchor.level:.2f}"
                f" is {abs(entry - anchor.level):.2f} from price",
                waiting=waiting, plan=plan,
            )

        # -- tactical stop (reused) ----------------------------------------------
        stop = self._tactical_stop(candidate, entry, m5, m1, atr5, spread,
                                   anchor, sweeps)
        if stop is None:
            waiting, plan = self._reentry_plan(candidate, zones, anchor)
            return self._wait(
                context, smc,
                "no structurally justified tactical stop within 8.0 USD — "
                "re-entry plan armed",
                waiting="LOCAL_SWING",
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
                f"({stop_source}: {playbook} setup broken)"
            ),
        )

        # -- H8 zone consumption (reused) -----------------------------------------
        consumed_block = self._consumed_stop_block(
            candidate, stop_price, atr5, now
        )
        if consumed_block:
            return self._wait(
                context, smc, consumed_block,
                waiting="LOCAL_SWING",
                plan="wait for structure beyond the consumed level or for "
                     "it to go stale (30 min)",
            )

        # -- quality score ------------------------------------------------------
        score, score_detail = self._quality_score(
            narrative, anchor, stop_source, in_killzone,
            liquidity_context, atr5, entry,
        )
        smc["quality"] = f"{score:.2f} [{score_detail}]"
        if score < S_NORMAL:
            return self._wait(
                context, smc,
                f"QUALITY_BELOW_BAR: score {score:.2f} < {S_NORMAL:.2f} "
                f"[{score_detail}] — only clean setups trade",
                waiting="SWEEP",
                plan="wait for a higher-quality setup (better stop source, "
                     "fresher event, or kill-zone timing)",
            )
        grade = (
            SetupGrade.STRONG if score >= S_STRONG else SetupGrade.NORMAL
        )
        smc["grade"] = grade

        lot, lot_why = self._fixed_lot(grade, session, equity, stop_distance,
                                       spread)
        if lot is None:
            return self._wait(context, smc, lot_why, waiting="LOCAL_SWING",
                              plan="wait for a tighter local invalidation")
        risk_pct = 0.015 if lot == LOT_STRONG else 0.010
        budget_usd = equity * risk_pct
        est_lot = max(
            int(budget_usd / (100.0 * (stop_distance + spread)) / 0.01) * 0.01,
            0.01,
        )
        smc["lot_decision"] = (
            f"~{est_lot:.2f} (tier {lot:.2f} = {risk_pct:.1%} equity risk)"
        )
        risk_usd = min(budget_usd, est_lot * 100.0 * (stop_distance + spread))
        smc["risk_if_sl_hit"] = round(risk_usd, 2)

        decision = self._decision(
            inp.symbol, now, candidate, entry, stop_price, stop_distance,
            anchor, trigger, grade, lot,
            f"{narrative.state.value}:{playbook}",
        )
        confidence = self._confidence(grade, anchor, trigger)
        smc["reason"] = (
            f"{grade} {candidate.value} [{playbook} @ "
            f"{narrative.state.value}]: anchor={anchor.label} "
            f"({anchor.detail}) trigger={trigger} quality={score:.2f} "
            f"stop={stop_source}@{stop_price:.2f} ({stop_distance:.2f}); "
            f"{lot_why}"
        )
        self._playbook_by_direction[candidate] = playbook

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
            protected_addon=(
                inp.broker.open_positions > 0 and narrative.pyramids_allowed
            ),
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

    # -- v2 helpers --------------------------------------------------------------
    @staticmethod
    def _kill_zones():
        from src.strategy.smc_execution import _KILL_ZONES
        return _KILL_ZONES

    @staticmethod
    def _sweep_story(
        m5, sweeps
    ) -> Tuple[List[Tuple[float, Direction]], bool, bool]:
        """(swept key levels with rejection direction, latest reclaim held,
        reclaim is fresh)."""
        story: List[Tuple[float, Direction]] = []
        held = False
        fresh = False
        true_sweeps = [
            s for s in sweeps if s.status is SweepStatus.TRUE_SWEEP
        ]
        if not true_sweeps or not m5:
            return story, held, fresh
        last_close = m5[-1].close
        for s in sorted(true_sweeps, key=lambda s: s.sweep_index):
            direction = (
                Direction.LONG if s.rejection_bias is Bias.BULLISH
                else Direction.SHORT
            )
            story.append((s.level.price, direction))
        latest = max(true_sweeps, key=lambda s: s.sweep_index)
        latest_dir = (
            Direction.LONG if latest.rejection_bias is Bias.BULLISH
            else Direction.SHORT
        )
        held = (
            last_close > latest.level.price
            if latest_dir is Direction.LONG
            else last_close < latest.level.price
        )
        fresh = held and (
            latest.sweep_index >= len(m5) - SWEEP_FRESH_CANDLES
        )
        return story, held, fresh

    @staticmethod
    def _candidate_from(narrative) -> Optional[Direction]:
        if abs(narrative.conviction) < CONVICTION_ENTRY_MIN:
            return None
        wanted = (
            Direction.LONG if narrative.conviction > 0 else Direction.SHORT
        )
        if wanted in narrative.allowed_directions:
            return wanted
        return None

    def _select_playbook(
        self, narrative, candidate, m5, structure, sweeps, zones,
        displacement, disp_direction, atr5, reclaim_held, entry,
    ):
        """(playbook, anchor, trigger, why_blocked)."""
        anchor = self._find_anchor(
            candidate, m5, structure, sweeps, zones, displacement,
            disp_direction, atr5,
        )
        if anchor is None:
            return None, None, None, (
                "no SMC anchor for the narrative direction yet "
                f"({candidate.value})"
            )
        trigger = self._entry_trigger(
            candidate, anchor, m5, displacement, disp_direction
        )
        if trigger is None:
            return None, None, None, (
                f"anchor {anchor.label} present but no executable local "
                "trigger yet"
            )
        blocked_reasons: List[str] = []
        for playbook in narrative.allowed_playbooks:
            if self._sl_losses_by_playbook.get(playbook, 0) \
                    >= PLAYBOOK_DAY_LIMIT:
                blocked_reasons.append(
                    f"{playbook} stood down ({PLAYBOOK_DAY_LIMIT} stop-outs "
                    "today)"
                )
                continue
            if playbook == PB_SWEEP_RECLAIM:
                if anchor.label == "SWEEP_DISPLACEMENT" and reclaim_held:
                    return playbook, anchor, trigger, ""
                blocked_reasons.append(
                    "SWEEP_RECLAIM needs a held reclaim with a sweep anchor"
                )
            elif playbook == PB_TREND_CONTINUATION:
                if anchor.label in ("FVG_RETEST", "OB_RETEST",
                                    "BREAK_RETEST", "SWEEP_DISPLACEMENT"):
                    return playbook, anchor, trigger, ""
                blocked_reasons.append(
                    f"TREND_CONTINUATION needs a retest/sweep anchor "
                    f"(got {anchor.label})"
                )
            elif playbook == PB_RANGE_FADE:
                day = [c for c in m5
                       if c.time_utc.date() == m5[-1].time_utc.date()]
                hi = max(c.high for c in day)
                lo = min(c.low for c in day)
                rng = max(hi - lo, 0.01)
                near_extreme = (
                    (hi - entry) / rng <= RANGE_FADE_EXTREME_PCT
                    if candidate is Direction.SHORT
                    else (entry - lo) / rng <= RANGE_FADE_EXTREME_PCT
                )
                if near_extreme and anchor.label in (
                    "SWEEP_DISPLACEMENT", "FVG_RETEST", "OB_RETEST",
                ):
                    return playbook, anchor, trigger, ""
                blocked_reasons.append(
                    "RANGE_FADE only at the range extreme with a "
                    "sweep/retest anchor"
                )
        return None, None, None, "; ".join(blocked_reasons) or \
            "no playbook conditions met"

    @staticmethod
    def _quality_score(
        narrative, anchor, stop_source, in_killzone, liquidity_context,
        atr5, entry,
    ) -> Tuple[float, str]:
        parts: List[str] = []
        score = 0.0
        c = min(abs(narrative.conviction), 1.0)
        score += 0.30 * c
        parts.append(f"conviction {0.30 * c:.2f}")
        event = {
            "SWEEP_DISPLACEMENT": 0.25, "FVG_RETEST": 0.18,
            "OB_RETEST": 0.18, "BREAK_RETEST": 0.15,
            "CHOCH": 0.10, "BOS": 0.10,
        }.get(anchor.label, 0.05)
        score += event
        parts.append(f"event {event:.2f}")
        fresh = 0.15
        if anchor.level is not None and atr5 > 0:
            fresh = 0.15 if abs(entry - anchor.level) <= 3 * atr5 else 0.06
        score += fresh
        parts.append(f"freshness {fresh:.2f}")
        stop_q = {
            "rejection_wick": 0.15, "FVG_boundary": 0.15,
            "OB_boundary": 0.15, "local_swing": 0.07,
        }.get(stop_source, 0.05)
        score += stop_q
        parts.append(f"stop {stop_q:.2f}")
        timing = 0.15 if in_killzone else (
            0.08 if liquidity_context != "NONE" else 0.02
        )
        score += timing
        parts.append(f"timing {timing:.2f}")
        return round(score, 2), ", ".join(parts)


def make_smc_v2_pipeline(canonical_symbol: str, *, max_spread_price: float = 1.0,
                         max_staleness=None):
    """Build the SMC v2 pipeline for live XAU data (same envelope as v1)."""
    from datetime import timedelta

    from src.data.validation import DataValidator, ValidationConfig
    from src.strategy.smc_execution import SmcEngines, make_challenge_limits

    canonical = canonical_symbol.strip().upper()
    engines = SmcEngines(
        validator=DataValidator(ValidationConfig(
            expected_symbol=canonical,
            detect_gaps=False,
            max_staleness=max_staleness or timedelta(minutes=30),
        )),
    )
    return SmcV2Pipeline(
        make_challenge_limits(canonical),
        max_spread=max_spread_price,
        engines=engines,
    )
