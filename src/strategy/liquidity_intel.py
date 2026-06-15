"""Liquidity Intelligence decision engine (Task LIQUIDITY-INTEL-001). DEMO ONLY.

The SINGLE autonomous XAU/USD decision engine wired into the trading service.
It is the proven day-narrative brain (the only logic with a positive replay
record: +7.0R over an 8.5-month replay, 7/10 months positive) running on the
clean single-path architecture of this rebuild.

Decision: from-scratch posture experiments lost on real history (replay
2026-06-15: -27R / ~18% win at every selectivity). Option 1 (owner-directed)
keeps the rebuild's plumbing — ONE account source (.env), ONE execution path,
ONE planner (IntelTradePlanner), ONE journal, ONE accounting source (MT5),
ONE trading service, retired profiles refused — and restores the validated
day-narrative decision logic as the ONE engine.

Engine internals (composed, not duplicated):
- `SmcExecutionPipeline` (src/strategy/smc_execution.py): the A+B+C+D gate
  chassis (HTF context, killzone/liquidity, SMC anchor, executable trigger +
  structurally justified TACTICAL stop beyond the engineered extreme).
- `SmcV2Pipeline` (src/strategy/smc_v2.py): the day-narrative brain on top —
  classify the DAY first (TREND/RANGE/TRAP/POST_SPIKE/EXHAUSTED), playbooks
  per state, conviction gate, quality score, within-day trade memory, and an
  institutional cadence cap (the brain's OWN entries/day, far tighter than the
  envelope's survival ceiling).

`LiquidityIntelEngine` is `SmcV2Pipeline` re-branded for the single profile;
the per-cycle output reads `profile=liquidity_intel`. This module sends no
orders and holds no credentials; the ExecutionGateway remains the only order
pathway and the RiskGovernor has final authority.

Shipped selectivity knobs (tuned ONLY by walk-forward replay, never live):
quality_bar 0.70, strong_bar 0.78, max 2 entries/day, 3R trend targets.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from src.data.validation import DataValidator, ValidationConfig
from src.risk.governor import RiskLimits
from src.strategy.pipeline import PipelineInput, PipelineResult
from src.strategy.smc_execution import SmcEngines
from src.strategy.smc_v2 import SmcV2Pipeline

# Single profile identity.
PROFILE_NAME = "liquidity_intel"

# Shipped defaults (the smc_v2 maximum-selectivity config that produced the
# only positive replay; +7.0R/8.5mo, +8.16R unseen validation days).
DEFAULT_QUALITY_BAR = 0.70
DEFAULT_STRONG_BAR = 0.78
DEFAULT_MAX_ENTRIES_PER_DAY = 2
DEFAULT_TREND_TARGET_R = 3.0


def make_intel_limits(expected_symbol: str) -> RiskLimits:
    """The single liquidity_intel risk envelope (demo-only, anchors absolute):
    3%/trade survival cap, daily 5% net pause, weekly 10% net stop, max 3
    open, a 25/day survival CEILING (the brain's own cadence cap governs the
    real cadence), spread <= 1.0. Real mode forbidden for this envelope."""
    return RiskLimits(
        expected_symbol=expected_symbol,
        max_risk_per_trade=0.030,
        max_daily_loss=0.05,
        max_weekly_loss=0.10,
        max_trades_per_day=25,
        max_open_trades=3,
        max_spread=1.0,
    )


class LiquidityIntelEngine(SmcV2Pipeline):
    """The single decision engine: the proven day-narrative brain, re-branded
    for --profile liquidity_intel. Same decide()/note_stop_loss contract the
    chassis drives."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.threshold_profile = PROFILE_NAME

    def decide(self, inp: PipelineInput) -> PipelineResult:
        result = super().decide(inp)
        # Re-brand the per-cycle output to the single profile (honest label).
        ctx = result.context
        ch = getattr(ctx, "challenge", None) if ctx is not None else None
        if ch:
            ch["mode"] = PROFILE_NAME
            ch["profile"] = PROFILE_NAME
        return result


def make_liquidity_intel_pipeline(
    canonical_symbol: str,
    *,
    max_spread_price: float = 1.0,
    quality_bar: float = DEFAULT_QUALITY_BAR,
    strong_bar: float = DEFAULT_STRONG_BAR,
    max_entries_per_day: int = DEFAULT_MAX_ENTRIES_PER_DAY,
    trend_target_r: float = DEFAULT_TREND_TARGET_R,
    structural_stops_only: bool = False,
    max_staleness: Optional[timedelta] = None,
) -> LiquidityIntelEngine:
    """Build the single liquidity_intel decision engine for LIVE XAUUSDm."""
    canonical = canonical_symbol.strip().upper()
    engines = SmcEngines(
        validator=DataValidator(ValidationConfig(
            expected_symbol=canonical,
            detect_gaps=False,
            max_staleness=max_staleness or timedelta(minutes=30),
        )),
    )
    return LiquidityIntelEngine(
        make_intel_limits(canonical),
        max_spread=max_spread_price,
        engines=engines,
        quality_bar=quality_bar,
        strong_bar=strong_bar,
        max_entries_per_day=max_entries_per_day,
        trend_target_r=trend_target_r,
        structural_stops_only=structural_stops_only,
    )
