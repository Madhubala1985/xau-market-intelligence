"""Day-narrative engine for the SMC v2 decision brain (SMC-V2-001).

Classifies the TRADING DAY (not the candle) into a narrative state and
maintains a conviction score for direction, per 26_SMC_V2_DESIGN.md.

Design invariant: the narrative is a PURE FUNCTION of the day's candles
and session context — no hidden mutable state — so a historical replay
reproduces exactly what the live service would have decided. Hysteresis
comes from the evidence timeline itself (e.g. an established trend stays
a trend until opposing displacement appears), not from stored flags.

This module never trades, never sizes, never touches risk: it only
narrates. The v2 pipeline consumes the narrative to select playbooks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from src.data.enums import Direction
from src.data.schemas import Candle
from src.data.session_levels import AsianRangeContext


class DayState(str, Enum):
    OPENING = "OPENING"                  # not enough day evidence yet
    ASIAN_RANGE = "ASIAN_RANGE"          # inside the Asian accumulation
    TREND_DAY = "TREND_DAY"              # directional legs + expansion
    RANGE_DAY = "RANGE_DAY"              # failed breaks both sides
    TRAP_REVERSAL = "TRAP_REVERSAL"      # swept extreme reclaimed + reversal
    POST_SPIKE_CHOP = "POST_SPIKE_CHOP"  # violent leg, no acceptance yet
    EXHAUSTED = "EXHAUSTED"              # mature trend + opposing structure


# Playbook names (the v2 pipeline maps these to entry logic).
PB_TREND_CONTINUATION = "TREND_CONTINUATION"
PB_SWEEP_RECLAIM = "SWEEP_RECLAIM"
PB_RANGE_FADE = "RANGE_FADE"

# Evidence thresholds (tuned ONLY by replay evidence, never live).
LEG_BODY_MULT = 1.5          # displacement leg: body >= mult * median body
TREND_EXPANSION_MIN = 1.2    # range expansion vs Asian range for a trend day
SPIKE_LEG_ATR_MULT = 4.0     # single leg this size => POST_SPIKE_CHOP window
SPIKE_COOLOFF_CANDLES = 9    # M5 candles of acceptance needed after a spike
RANGE_FAILED_BREAKS_MIN = 2  # failed breaks per side for RANGE_DAY
EXHAUSTION_LEGS = 4          # legs in one direction before exhaustion watch
CONVICTION_ENTRY_MIN = 0.45  # |conviction| needed to trade at all


@dataclass(frozen=True)
class Leg:
    """One M5 displacement leg."""

    index: int
    direction: Direction
    size: float  # body size in USD


@dataclass(frozen=True)
class DayNarrative:
    state: DayState
    direction: Optional[Direction]            # trend/trap direction
    conviction: float                         # [-1 short .. +1 long]
    allowed_playbooks: Tuple[str, ...]
    allowed_directions: Tuple[Direction, ...]
    pyramids_allowed: bool
    rearm_condition: str                      # printed when nothing allowed
    evidence: Tuple[str, ...]                 # human-readable trail

    @property
    def tradeable(self) -> bool:
        return bool(self.allowed_playbooks)


class DayNarrativeEngine:
    """Pure day classifier; safe to call every cycle and in replay."""

    def narrate(
        self,
        m5: Sequence[Candle],
        *,
        asian: Optional[AsianRangeContext] = None,
        htf_direction: Optional[Direction] = None,
        swept_levels: Sequence[Tuple[float, Direction]] = (),
        reclaim_held: Optional[bool] = None,
        reclaim_fresh: Optional[bool] = None,
    ) -> DayNarrative:
        """Classify the day from its own candles.

        `m5` should cover the current UTC day (the caller slices); a longer
        window only strengthens the baseline. `swept_levels` are key-level
        sweeps detected upstream as (level, rejection_direction) with
        `reclaim_held` for the freshest one.
        """
        day = self._today_slice(m5)
        evidence: List[str] = []
        if len(day) < 6:
            return self._narrative(
                DayState.OPENING, None, 0.0,
                rearm="waiting for the day to develop (need >= 6 M5 candles)",
                evidence=("day just opened",),
            )

        baseline_atr = self._atr(m5)
        legs = self._legs(day)
        up_legs = [l for l in legs if l.direction is Direction.LONG]
        down_legs = [l for l in legs if l.direction is Direction.SHORT]
        expansion = self._expansion(day, asian)
        failed_up, failed_down = self._failed_breaks(day)
        last = day[-1]

        # -- TRAP_REVERSAL: key level swept, reclaim held, reversal leg -----
        # Checked BEFORE the spike gate: a held reclaim with reversal
        # displacement is the richer read of the same violence. NOTE: a
        # stale held reclaim deliberately KEEPS the day in this state — it
        # acts as the day's trend-following mode in the reversal direction
        # (replay-proven: gating traps on fresh reclaims flipped 12-day
        # net R from +10.9 to -14/-17). reclaim_fresh is accepted for
        # diagnostics but does not gate the state.
        _ = reclaim_fresh
        if swept_levels and reclaim_held:
            level, rejection_dir = swept_levels[-1]
            reversal_legs = (
                up_legs if rejection_dir is Direction.LONG else down_legs
            )
            if reversal_legs and reversal_legs[-1].index >= len(day) - 24:
                evidence.append(
                    f"key level {level:.2f} swept, reclaim HELD, reversal "
                    f"displacement {rejection_dir.value} present"
                )
                # Trap conviction deliberately EXCLUDES the day-net term
                # and HTF zeroing: a genuine reversal opposes the day's
                # net tape by definition (replay-proven: adding the net
                # term here flipped 12-day net R from +10.9 to -8.6).
                conviction = self._conviction(
                    htf_direction, legs, swept_levels, reclaim_held, evidence
                )
                return self._narrative(
                    DayState.TRAP_REVERSAL, rejection_dir, conviction,
                    evidence=evidence,
                    playbooks=(PB_SWEEP_RECLAIM, PB_TREND_CONTINUATION),
                    directions=(rejection_dir,),
                    pyramids=False,
                )

        # -- POST_SPIKE_CHOP: a violent candle without acceptance -----------
        spike = self._fresh_spike(day, baseline_atr)
        if spike is not None:
            leg, age = spike
            evidence.append(
                f"spike candle {leg.size:.1f} USD "
                f"({leg.size / baseline_atr:.1f}x ATR) {age} candles ago — "
                "no acceptance yet"
            )
            conviction = self._conviction(
                htf_direction, legs, swept_levels, reclaim_held, evidence,
                day, baseline_atr,
            )
            return self._narrative(
                DayState.POST_SPIKE_CHOP, leg.direction, conviction,
                rearm=(
                    f"stand down {SPIKE_COOLOFF_CANDLES - age} more M5 "
                    "candles OR until a key-level sweep+reclaim prints"
                ),
                evidence=evidence,
                # the ONE exception institutional flow respects in a spike:
                # a fresh sweep+reclaim of a key level.
                playbooks=(PB_SWEEP_RECLAIM,) if reclaim_held else (),
                directions=self._reclaim_directions(swept_levels,
                                                    reclaim_held),
            )

        # -- TREND_DAY: dominant displacement + real expansion ---------------
        # Two roads to dominance: aggregate LEG SIZE (impulsive days), or
        # directional EFFICIENCY (steady grind days have no outsized
        # candles — the net move IS the evidence).
        up_size = sum(l.size for l in up_legs)
        down_size = sum(l.size for l in down_legs)
        net = day[-1].close - day[0].open
        day_range = max(
            max(c.high for c in day) - min(c.low for c in day), 0.01
        )
        efficiency = abs(net) / day_range
        dominant: Optional[Direction] = None
        if up_size >= 3 * baseline_atr and up_size >= 2 * max(down_size, 0.01):
            dominant = Direction.LONG
        elif (down_size >= 3 * baseline_atr
              and down_size >= 2 * max(up_size, 0.01)):
            dominant = Direction.SHORT
        elif abs(net) >= 2.5 * baseline_atr and efficiency >= 0.55:
            dominant = Direction.LONG if net > 0 else Direction.SHORT
            evidence.append(
                f"grind trend: net {net:+.1f} USD at {efficiency:.0%} "
                "directional efficiency"
            )
        # Expansion proves we LEFT the Asian accumulation — but a day that
        # trends THROUGH Asia has no accumulation to leave (replay
        # 2026-06-08: -48 USD inside the Asian session, expansion ~1.0,
        # never classified). High directional efficiency qualifies instead.
        trend_confirmed = (
            expansion >= TREND_EXPANSION_MIN or efficiency >= 0.60
        )
        if dominant is not None and trend_confirmed:
            dom_legs = up_legs if dominant is Direction.LONG else down_legs
            evidence.append(
                f"{len(dom_legs)} {dominant.value} leg(s) totalling "
                f"{(up_size if dominant is Direction.LONG else down_size):.1f}"
                f" USD, expansion {expansion:.1f}x Asian range"
            )
            conviction = self._conviction(
                htf_direction, legs, swept_levels, reclaim_held, evidence,
                day, baseline_atr,
            )
            # EXHAUSTED: mature trend + the LAST displacement opposes it.
            if (
                len(dom_legs) >= EXHAUSTION_LEGS
                and legs and legs[-1].direction is not dominant
            ):
                evidence.append(
                    f"mature trend ({len(dom_legs)} legs) with fresh "
                    "opposing displacement — exhaustion watch"
                )
                return self._narrative(
                    DayState.EXHAUSTED, dominant, conviction,
                    rearm=(
                        "no fresh entries: wait for a key-level "
                        "sweep+reclaim (reversal) or a new aligned leg"
                    ),
                    evidence=evidence,
                )
            return self._narrative(
                DayState.TREND_DAY, dominant, conviction,
                evidence=evidence,
                playbooks=(PB_TREND_CONTINUATION, PB_SWEEP_RECLAIM),
                directions=(dominant,),
                pyramids=True,
            )

        # -- RANGE_DAY: failed breaks on both sides AND no directional
        # efficiency (replay 2026-06-11: range fades fired on a +150 USD
        # trend day whose volatility printed failed breaks on both sides).
        if (
            failed_up >= RANGE_FAILED_BREAKS_MIN
            and failed_down >= RANGE_FAILED_BREAKS_MIN
            and efficiency < 0.40
        ):
            evidence.append(
                f"failed breaks: {failed_up} above / {failed_down} below — "
                "two-sided rejection"
            )
            conviction = self._conviction(
                htf_direction, legs, swept_levels, reclaim_held, evidence,
                day, baseline_atr,
            )
            return self._narrative(
                DayState.RANGE_DAY, None, conviction,
                evidence=evidence,
                playbooks=(PB_RANGE_FADE,),
                directions=(Direction.LONG, Direction.SHORT),
                pyramids=False,
            )

        # -- ASIAN_RANGE / undeveloped ---------------------------------------
        if asian is not None and asian.known and expansion < 1.0:
            evidence.append(
                f"price inside/near the Asian range (expansion "
                f"{expansion:.1f}x) — accumulation"
            )
            conviction = self._conviction(
                htf_direction, legs, swept_levels, reclaim_held, evidence,
                day, baseline_atr,
            )
            return self._narrative(
                DayState.ASIAN_RANGE, None, conviction,
                rearm="wait for a sweep of the Asian high/low or a "
                      "displacement leg out of the range",
                evidence=evidence,
                # the classic Asian-sweep play is allowed:
                playbooks=(PB_SWEEP_RECLAIM,) if reclaim_held else (),
                directions=self._reclaim_directions(swept_levels,
                                                    reclaim_held),
            )

        evidence.append(
            f"undeveloped: legs {len(up_legs)}L/{len(down_legs)}S, "
            f"expansion {expansion:.1f}x, failed breaks "
            f"{failed_up}/{failed_down}"
        )
        conviction = self._conviction(
            htf_direction, legs, swept_levels, reclaim_held, evidence,
            day, baseline_atr,
        )
        _ = last
        return self._narrative(
            DayState.OPENING, None, conviction,
            rearm="no day narrative yet: wait for legs/expansion/sweep "
                  "evidence",
            evidence=evidence,
        )

    # -- evidence primitives -------------------------------------------------
    @staticmethod
    def _today_slice(m5: Sequence[Candle]) -> List[Candle]:
        if not m5:
            return []
        day = m5[-1].time_utc.date()
        out = [c for c in m5 if c.time_utc.date() == day]
        return out

    @staticmethod
    def _atr(candles: Sequence[Candle], period: int = 100) -> float:
        window = list(candles)[-period:]
        if not window:
            return 0.0
        return sum(c.high - c.low for c in window) / len(window)

    @staticmethod
    def _legs(day: Sequence[Candle]) -> List[Leg]:
        bodies = sorted(abs(c.close - c.open) for c in day)
        median = bodies[len(bodies) // 2] if bodies else 0.0
        if median <= 0:
            return []
        legs: List[Leg] = []
        for i, c in enumerate(day):
            body = abs(c.close - c.open)
            if body >= LEG_BODY_MULT * median and body > 0:
                direction = (
                    Direction.LONG if c.close > c.open else Direction.SHORT
                )
                # merge consecutive same-direction candles into one leg
                if legs and legs[-1].direction is direction \
                        and i - legs[-1].index <= 2:
                    legs[-1] = Leg(i, direction, legs[-1].size + body)
                else:
                    legs.append(Leg(i, direction, body))
        return legs

    @staticmethod
    def _expansion(
        day: Sequence[Candle], asian: Optional[AsianRangeContext]
    ) -> float:
        if (
            asian is None or not asian.known
            or asian.high is None or asian.low is None
            or asian.high <= asian.low
        ):
            return 0.0
        asian_range = asian.high - asian.low
        day_high = max(c.high for c in day)
        day_low = min(c.low for c in day)
        return (day_high - day_low) / asian_range

    @staticmethod
    def _failed_breaks(day: Sequence[Candle]) -> Tuple[int, int]:
        """Wicks beyond the developing extreme that closed back inside."""
        failed_up = failed_down = 0
        hi = day[0].high
        lo = day[0].low
        for c in day[1:]:
            if c.high > hi and c.close < hi:
                failed_up += 1
            if c.low < lo and c.close > lo:
                failed_down += 1
            hi = max(hi, c.high)
            lo = min(lo, c.low)
        return failed_up, failed_down

    def _fresh_spike(
        self, day: Sequence[Candle], baseline_atr: float
    ) -> Optional[Tuple[Leg, int]]:
        """A SINGLE candle of violence (not an accumulated trend leg):
        steady directional days must never read as spikes."""
        if baseline_atr <= 0:
            return None
        recent = list(day)[-(SPIKE_COOLOFF_CANDLES + 1):]
        offset = len(day) - len(recent)
        for i in range(len(recent) - 1, -1, -1):
            c = recent[i]
            body = abs(c.close - c.open)
            if body >= SPIKE_LEG_ATR_MULT * baseline_atr:
                direction = (
                    Direction.LONG if c.close > c.open else Direction.SHORT
                )
                age = len(day) - 1 - (offset + i)
                return Leg(offset + i, direction, body), age
        return None

    # -- conviction -----------------------------------------------------------
    @staticmethod
    def _conviction(
        htf_direction: Optional[Direction],
        legs: Sequence[Leg],
        swept_levels: Sequence[Tuple[float, Direction]],
        reclaim_held: Optional[bool],
        evidence: List[str],
        day: Sequence[Candle] = (),
        baseline_atr: float = 0.0,
    ) -> float:
        score = 0.0
        net = 0.0
        decisive_net = False
        if day and baseline_atr > 0:
            net = day[-1].close - day[0].open
            if abs(net) >= 2.5 * baseline_atr:
                decisive_net = True
                score += 0.25 if net > 0 else -0.25
        # The D3 lesson, replay-confirmed (2026-06-11: a BEARISH D1/H4
        # suppressed conviction through a +150 USD rally): a stale HTF
        # bias contributes NOTHING when the day's own tape decisively
        # opposes it.
        htf_opposed = decisive_net and (
            (htf_direction is Direction.LONG and net < 0)
            or (htf_direction is Direction.SHORT and net > 0)
        )
        if htf_opposed:
            evidence.append("HTF bias zeroed: day tape decisively opposes it")
        elif htf_direction is Direction.LONG:
            score += 0.3
        elif htf_direction is Direction.SHORT:
            score -= 0.3
        leg_net = 0.0
        for leg in legs:
            leg_net += 0.15 if leg.direction is Direction.LONG else -0.15
        score += max(-0.45, min(0.45, leg_net))
        if swept_levels and reclaim_held:
            _, rejection_dir = swept_levels[-1]
            score += 0.4 if rejection_dir is Direction.LONG else -0.4
        score = max(-1.0, min(1.0, score))
        evidence.append(f"conviction {score:+.2f}")
        return score

    @staticmethod
    def _reclaim_directions(
        swept_levels: Sequence[Tuple[float, Direction]],
        reclaim_held: Optional[bool],
    ) -> Tuple[Direction, ...]:
        if swept_levels and reclaim_held:
            return (swept_levels[-1][1],)
        return ()

    # -- assembly --------------------------------------------------------------
    @staticmethod
    def _narrative(
        state: DayState,
        direction: Optional[Direction],
        conviction: float,
        *,
        evidence: Sequence[str],
        playbooks: Tuple[str, ...] = (),
        directions: Tuple[Direction, ...] = (),
        pyramids: bool = False,
        rearm: str = "",
    ) -> DayNarrative:
        return DayNarrative(
            state=state,
            direction=direction,
            conviction=round(conviction, 2),
            allowed_playbooks=playbooks,
            allowed_directions=directions,
            pyramids_allowed=pyramids,
            rearm_condition=rearm,
            evidence=tuple(evidence),
        )
