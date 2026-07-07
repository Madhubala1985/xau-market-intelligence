"""Gold Intelligence engine (Task GOLD-INTEL-001). DEMO ONLY.

The SINGLE autonomous XAU/USD decision engine: three brains on one path.

1. OPPORTUNITY BRAIN — the day-narrative decision logic (SmcV2Pipeline), the
   only decision layer in this repo's history with a positive real-history
   replay record (+2.43R/10d under punitive fills; +7.0R/8.5mo longhaul;
   +8.16R on unseen walk-forward validation days). Classify the DAY first
   (TREND/RANGE/TRAP/POST_SPIKE/EXHAUSTED), playbooks per state, conviction
   gate, quality bar, within-day trade memory, institutional cadence cap.
   Trade count is an OUTPUT of opportunity, never a target: the entries/day
   sweep on real history was positive at 2-3/day and NEGATIVE at 4+/day.

2. RISK BRAIN — the macro regime dial (research/regime.py), the one artifact
   that survived the full research gauntlet. Tighten-only: a TIGHTENING
   regime (rising real yields + rising dollar) demotes STRONG entries to
   NORMAL size. It can never upsize and never creates trades. When macro
   data is unavailable/stale it reads UNAVAILABLE and changes nothing.

3. COST BRAIN — ALPHA-HUNT-001's measured lessons as hard entry gates:
   - the COMEX close/reopen window (16:55-18:20 ET) is untradeable at retail
     costs (measured reopen spread ~5.7 bps vs ~2.3 normal; the reopen
     anomaly itself lives inside the spread — decision 2026-07-05-02);
   - ONE price-level-independent cost rule: estimated round-trip cost
     (live spread + slippage allowance) must stay under MAX_COST_R of the
     stop distance (1R) — beyond that the trade is structurally unwinnable
     (XAU lesson: edges must clear >> 5 bps/trade).

This module sends no orders and holds no credentials; the ExecutionGateway
remains the only order pathway and the RiskGovernor has final authority.
Demo-only, mandatory SL, no martingale, kill switch: absolute.
"""

from __future__ import annotations

from dataclasses import replace as dc_replace
from datetime import timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from src.data.enums import Direction
from src.data.validation import DataValidator, ValidationConfig
from src.risk.governor import RiskLimits
from src.strategy.pipeline import PipelineInput, PipelineResult
from src.strategy.smc_execution import SmcEngines
from src.strategy.smc_v2 import SmcV2Pipeline
from src.structure.market_structure import Bias, StructureEventType

# Single profile identity.
PROFILE_NAME = "gold_intel"

# Opportunity-brain knobs: the replay-validated smc_v2 optimum (tuned ONLY by
# walk-forward replay, never live).
DEFAULT_QUALITY_BAR = 0.70
DEFAULT_STRONG_BAR = 0.78
DEFAULT_MAX_ENTRIES_PER_DAY = 2
DEFAULT_TREND_TARGET_R = 3.0

# Cost brain (pre-declared constants; evidence in reports/research/).
ET = ZoneInfo("America/New_York")
REOPEN_BLOCK_START_ET = (16, 55)   # inclusive, ET
REOPEN_BLOCK_END_ET = (18, 20)     # exclusive, ET
# ONE coherent cost rule, price-level independent: estimated round-trip cost
# (live spread + slippage allowance) as a fraction of 1R (the stop distance)
# must stay under MAX_COST_R. The June 2026 replay book was net positive
# INCLUDING trades that paid ~0.3-0.4R in punitive costs; beyond ~0.4R a 2R
# target needs >60% wins — structurally unwinnable. A fixed USD stop floor is
# WRONG across price levels ($2k gold vs $4k gold) and is not used.
SLIPPAGE_ALLOWANCE_USD = 0.30
MAX_COST_R = 0.40

# Risk brain: dial <= 1/3 (2+ of 3 lookbacks say TIGHTENING) demotes STRONG.
REGIME_DEMOTE_BELOW = 0.34

# Exit model (chassis-validated in the gold_alpha era; tighten-only).
BE_TRIGGER_R = 1.0     # arm break-even at +1R
TRAIL_ATR_MULT = 1.5   # trail this many M5-ATR behind once running


def make_intel_limits(expected_symbol: str) -> RiskLimits:
    """The single gold_intel risk envelope (demo-only, anchors absolute):
    3%/trade cap, daily 5% pause, weekly 10% stop, max 3 open, 25/day
    survival CEILING (the brain's own 2/day cadence cap governs the real
    number), spread <= 1.0. The gold_alpha era's disabled circuit-breakers
    are reinstated: the evidence says drawdown control IS the growth lever
    (compounding survives; blown weeks do not)."""
    return RiskLimits(
        expected_symbol=expected_symbol,
        max_risk_per_trade=0.030,
        max_daily_loss=0.05,
        max_weekly_loss=0.10,
        max_trades_per_day=25,
        max_open_trades=3,
        max_spread=1.0,
    )


def _in_reopen_block(inp: PipelineInput) -> bool:
    candles = inp.exec_candles
    if not candles:
        return False
    et = candles[-1].time_utc.astimezone(ET)
    hm = (et.hour, et.minute)
    return REOPEN_BLOCK_START_ET <= hm < REOPEN_BLOCK_END_ET


class GoldIntelEngine(SmcV2Pipeline):
    """Day-narrative brain + regime risk dial + cost gates, branded for the
    single --profile gold_intel. Same decide()/note_stop_loss contract the
    chassis drives."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.threshold_profile = PROFILE_NAME
        self._regime_exposure: Optional[float] = None
        self._regime_label: str = "UNAVAILABLE"
        # Original stop distance per open direction (advisory memory for the
        # exit model's R math; cleared on close, safe if stale: tighten-only).
        self._open_risk: dict = {}

    # ---- risk brain input (set by the runner; tighten-only) ----
    def set_regime(self, exposure: Optional[float], label: str = "") -> None:
        """Feed the macro regime dial. None/empty = honest UNAVAILABLE
        (neutral: no demotion, never an upsize)."""
        if exposure is None:
            self._regime_exposure = None
            self._regime_label = "UNAVAILABLE"
            return
        self._regime_exposure = max(0.0, min(1.0, float(exposure)))
        self._regime_label = label or "SET"

    # ---- decision path ----
    def decide(self, inp: PipelineInput) -> PipelineResult:
        result = super().decide(inp)
        ctx = result.context
        ch = getattr(ctx, "challenge", None) if ctx is not None else None
        if ch:
            ch["mode"] = PROFILE_NAME
            ch["profile"] = PROFILE_NAME
            dial = ("-" if self._regime_exposure is None
                    else f"{self._regime_exposure:.2f}")
            ch["regime_dial"] = f"{self._regime_label} exposure={dial}"
        if not (result.approved and result.decision is not None):
            return result

        # COST BRAIN: hard entry gates (entries only; open positions are
        # managed by the chassis regardless).
        block = self._cost_gate(inp, result)
        if block is not None:
            # the brain counted this approval against its daily cadence cap,
            # but no trade happened — restore the slot.
            if self._entries_today > 0:
                self._entries_today -= 1
            if ch:
                ch["cost_gate"] = block
                ch["reason"] = block
            return dc_replace(result, approved=False, decision=None,
                              lot_size=0.0, reason=block)

        # RISK BRAIN: tighten-only STRONG -> NORMAL demotion in TIGHTENING.
        exp = self._regime_exposure
        if (exp is not None and exp < REGIME_DEMOTE_BELOW
                and result.decision.setup_type
                and "lot=0.10" in result.decision.setup_type):
            demoted = result.decision.model_copy(update={
                "setup_type": result.decision.setup_type.replace(
                    "lot=0.10", "lot=0.05"),
            })
            if ch:
                ch["grade"] = "NORMAL (regime-demoted from STRONG)"
                ch["regime_demotion"] = (
                    f"macro dial {exp:.2f} < {REGIME_DEMOTE_BELOW} -> size tier"
                    " demoted (tighten-only)")
            return dc_replace(result, decision=demoted)
        return result

    # ---- exit model (called by the session for open positions) ----
    def manage_stop(self, direction, entry_price, current_stop,
                    current_price, m5) -> Optional[float]:
        """Return a TIGHTEN-ONLY new stop, or None: break-even at +1R, an
        ATR trail beyond it, and a fast thesis-failure exit when M5 structure
        flips (CHOCH) against the position. Never widens; the gateway
        enforces that too."""
        if entry_price is None or current_price is None or not m5:
            return None
        long = direction is Direction.LONG
        # Remember the ORIGINAL risk while the stop is still on the loss side
        # (once tightened to BE the live stop no longer measures 1R).
        if current_stop is not None:
            on_loss_side = (current_stop < entry_price if long
                            else current_stop > entry_price)
            if on_loss_side:
                self._open_risk[direction] = abs(entry_price - current_stop)
        atr = self._atr(list(m5))
        r_dist = self._open_risk.get(direction) or (1.5 * atr if atr > 0
                                                    else None)
        proposals = []
        if r_dist and r_dist > 0:
            in_profit_r = ((current_price - entry_price) if long
                           else (entry_price - current_price)) / r_dist
            if in_profit_r >= BE_TRIGGER_R:
                proposals.append(entry_price)
                trail = (current_price - TRAIL_ATR_MULT * atr if long
                         else current_price + TRAIL_ATR_MULT * atr)
                proposals.append(trail)
        # fast thesis-failure exit: fresh CHOCH against the position
        structure = self._e.structure.analyze(list(m5))
        against = Bias.BEARISH if long else Bias.BULLISH
        recent = [ev for ev in structure.events
                  if ev.event_type is StructureEventType.CHOCH
                  and ev.bias is against
                  and ev.index >= len(m5) - 3]
        if recent:
            buf = max(0.2 * atr, 0.30)
            proposals.append(current_price - buf if long
                             else current_price + buf)
        if not proposals:
            return None
        if long:
            target = max(proposals)
            if current_stop is not None and target <= current_stop:
                return None
            return round(target, 2)
        target = min(proposals)
        if current_stop is not None and target >= current_stop:
            return None
        return round(target, 2)

    def note_trade_closed(self, direction, r_multiple: float) -> None:
        """Every close (win/TP/trail/SL) clears the exit model's memory for
        that direction. SL-loss bookkeeping stays in note_stop_loss."""
        if direction is not None:
            self._open_risk.pop(direction, None)

    def _cost_gate(self, inp: PipelineInput, result: PipelineResult
                   ) -> Optional[str]:
        d = result.decision
        if _in_reopen_block(inp):
            return ("COST_REOPEN_WINDOW: no entries 16:55-18:20 ET (measured "
                    "reopen spread ~5.7 bps; the window is untradeable at "
                    "retail costs)")
        if d.entry_price and d.stop_loss:
            stop_dist = abs(d.entry_price - d.stop_loss)
            cost = max(inp.current_spread or 0.0, 0.0) + SLIPPAGE_ALLOWANCE_USD
            if stop_dist > 0 and cost / stop_dist > MAX_COST_R:
                return (f"COST_TOO_LARGE_VS_RISK: est. cost {cost:.2f} USD = "
                        f"{cost / stop_dist:.2f}R of the {stop_dist:.2f} stop "
                        f"(max {MAX_COST_R:.2f}R) — structurally unwinnable "
                        "(XAU >>5 bps lesson)")
        return None


def make_gold_intel_pipeline(
    canonical_symbol: str,
    *,
    max_spread_price: float = 1.0,
    quality_bar: float = DEFAULT_QUALITY_BAR,
    strong_bar: float = DEFAULT_STRONG_BAR,
    max_entries_per_day: int = DEFAULT_MAX_ENTRIES_PER_DAY,
    trend_target_r: float = DEFAULT_TREND_TARGET_R,
    structural_stops_only: bool = False,
    max_staleness: Optional[timedelta] = None,
) -> GoldIntelEngine:
    """Build the single gold_intel decision engine for LIVE XAUUSDm."""
    canonical = canonical_symbol.strip().upper()
    engines = SmcEngines(
        validator=DataValidator(ValidationConfig(
            expected_symbol=canonical,
            detect_gaps=False,
            max_staleness=max_staleness or timedelta(minutes=30),
        )),
    )
    return GoldIntelEngine(
        make_intel_limits(canonical),
        max_spread=max_spread_price,
        engines=engines,
        quality_bar=quality_bar,
        strong_bar=strong_bar,
        max_entries_per_day=max_entries_per_day,
        trend_target_r=trend_target_r,
        structural_stops_only=structural_stops_only,
    )
