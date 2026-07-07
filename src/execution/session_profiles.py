"""Session risk profiles — ONE trading profile: gold_intel.

GOLD-ALPHA-001 rebuild: a single XAU/USD profit-maximisation model on one
execution path. Every earlier profile (liquidity_intel, smc_v2, smc_challenge,
demo_challenge, continuous, growth_evaluation, and the bounded evaluation
profiles) is RETIRED and CANNOT be selected — `get_profile` raises with a
pointer to the new profile so an old name can never accidentally run.

A profile may TIGHTEN the risk policy, never loosen it (construction enforces
the envelope bounds). `max_orders=None` = no artificial per-session cap; the
engine's expected-value bar governs cadence. No credentials, no trading here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional

from src.risk.governor import RiskLimits

# Standard demo policy bounds (reference ceiling for the "demo" envelope).
POLICY_MAX_RISK_PER_TRADE = 0.010
POLICY_MAX_DAILY_LOSS = 0.02
POLICY_MAX_WEEKLY_LOSS = 0.05
POLICY_MAX_TRADES_PER_DAY = 6
POLICY_MAX_OPEN_POSITIONS = 2
POLICY_MAX_SPREAD_PRICE = 1.0

# The single gold_intel envelope (DEMO). GOLD-INTEL-001 reinstates the
# circuit-breakers the gold_alpha era disabled: the replay evidence says
# drawdown control IS the growth lever (compounding survives; blown weeks
# do not; overtrading beyond 3/day measured NEGATIVE on real history).
#   - per-trade risk cap 3% (planner sizes 3% STRONG / 2% NORMAL below it);
#   - daily 5% pause, weekly 10% stop, max 3 open, 25/day survival CEILING
#     (the brain's own 2/day cadence cap governs the real number);
#   - spread cap kept (execution quality).
# Structural safety is enforced elsewhere and absolute: mandatory stop-loss,
# no martingale/grid/averaging-down, MT5 truth, kill switch, demo-only.
GOLD_MAX_RISK_PER_TRADE = 0.03
GOLD_MAX_DAILY_LOSS = 0.05
GOLD_MAX_WEEKLY_LOSS = 0.10
GOLD_MAX_TRADES_PER_DAY = 25
GOLD_MAX_OPEN_POSITIONS = 3

PROFILE_NAME = "gold_intel"
GOLD_PROFILE_NAMES = frozenset({PROFILE_NAME})

# Every retired profile name -> a hard stop in get_profile.
RETIRED_PROFILES = frozenset({
    "gold_alpha", "liquidity_intel", "demo_challenge", "smc_challenge", "smc_v2",
    "continuous", "growth_evaluation", "evaluation", "london", "newyork",
    "full_day", "smoke",
})

_MAX_DURATION_MINUTES = 8 * 60
_UNSET = object()


@dataclass(frozen=True)
class SessionProfile:
    name: str
    description: str
    duration_minutes: Optional[float]  # None = continuous service
    poll_seconds: float = 30.0
    max_orders: Optional[int] = None
    max_open_positions: int = GOLD_MAX_OPEN_POSITIONS
    max_trades_per_day: int = GOLD_MAX_TRADES_PER_DAY
    max_risk_per_trade: float = GOLD_MAX_RISK_PER_TRADE
    max_daily_loss: float = GOLD_MAX_DAILY_LOSS
    max_weekly_loss: float = GOLD_MAX_WEEKLY_LOSS
    max_spread_price: float = POLICY_MAX_SPREAD_PRICE
    envelope: str = "gold_intel"

    def __post_init__(self) -> None:
        if self.duration_minutes is not None and not (
            0 < self.duration_minutes <= _MAX_DURATION_MINUTES
        ):
            raise ValueError(
                f"profile {self.name!r}: duration_minutes must be in "
                f"(0, {_MAX_DURATION_MINUTES}] or None (continuous service)")
        if self.poll_seconds <= 0:
            raise ValueError(f"profile {self.name!r}: poll_seconds must be > 0")
        if self.max_orders is not None and self.max_orders < 0:
            raise ValueError(f"profile {self.name!r}: max_orders must be >= 0")
        if self.envelope not in ("demo", "gold_intel"):
            raise ValueError(
                f"profile {self.name!r}: unknown envelope {self.envelope!r}")
        if self.envelope == "gold_intel" and self.name not in GOLD_PROFILE_NAMES:
            raise ValueError(
                f"profile {self.name!r}: the gold_intel envelope is reserved "
                f"for {sorted(GOLD_PROFILE_NAMES)}")
        if self.envelope == "gold_intel":
            bounds = {
                "max_risk_per_trade": GOLD_MAX_RISK_PER_TRADE,
                "max_daily_loss": GOLD_MAX_DAILY_LOSS,
                "max_weekly_loss": GOLD_MAX_WEEKLY_LOSS,
                "max_trades_per_day": GOLD_MAX_TRADES_PER_DAY,
                "max_open_positions": GOLD_MAX_OPEN_POSITIONS,
                "max_spread_price": POLICY_MAX_SPREAD_PRICE,
            }
        else:
            bounds = {
                "max_risk_per_trade": POLICY_MAX_RISK_PER_TRADE,
                "max_daily_loss": POLICY_MAX_DAILY_LOSS,
                "max_weekly_loss": POLICY_MAX_WEEKLY_LOSS,
                "max_trades_per_day": POLICY_MAX_TRADES_PER_DAY,
                "max_open_positions": POLICY_MAX_OPEN_POSITIONS,
                "max_spread_price": POLICY_MAX_SPREAD_PRICE,
            }
        violations = [f for f, b in bounds.items() if getattr(self, f) > b]
        if violations:
            raise ValueError(
                f"profile {self.name!r} is looser than 03_RISK_POLICY.md "
                f"limits: {violations}")

    def risk_limits(self, expected_symbol: str) -> RiskLimits:
        return RiskLimits(
            expected_symbol=expected_symbol,
            max_risk_per_trade=self.max_risk_per_trade,
            max_daily_loss=self.max_daily_loss,
            max_weekly_loss=self.max_weekly_loss,
            max_trades_per_day=self.max_trades_per_day,
            max_open_trades=self.max_open_positions,
            max_spread=self.max_spread_price)

    def with_overrides(self, *, duration_minutes: Optional[float] = None,
                       poll_seconds: Optional[float] = None,
                       max_orders: object = _UNSET,
                       max_open_positions: Optional[int] = None
                       ) -> "SessionProfile":
        changes: dict = {}
        if duration_minutes is not None:
            changes["duration_minutes"] = duration_minutes
        if poll_seconds is not None:
            changes["poll_seconds"] = poll_seconds
        if max_orders is not _UNSET:
            changes["max_orders"] = max_orders
        if max_open_positions is not None:
            changes["max_open_positions"] = max_open_positions
        return replace(self, **changes) if changes else self


PROFILES: Dict[str, SessionProfile] = {
    p.name: p
    for p in (
        SessionProfile(
            name=PROFILE_NAME,
            description=(
                "GoldIntel (GOLD-INTEL-001): the single XAU/USD engine — "
                "three brains, one path. DEMO ONLY. (1) Opportunity brain: "
                "the day-narrative decision logic, the only layer with a "
                "positive real-history replay record; classifies the DAY "
                "first, playbooks per state, conviction + quality bar, "
                "2 entries/day institutional cadence. (2) Risk brain: the "
                "macro regime dial (tighten-only STRONG->NORMAL demotion in "
                "TIGHTENING). (3) Cost brain: no entries in the COMEX reopen "
                "window, minimum stop width, spread-vs-stop gate. Use "
                "scripts/trading_service.py --profile gold_intel."),
            duration_minutes=None, poll_seconds=30, max_orders=None,
            max_open_positions=GOLD_MAX_OPEN_POSITIONS,
            max_trades_per_day=GOLD_MAX_TRADES_PER_DAY,
            max_risk_per_trade=GOLD_MAX_RISK_PER_TRADE,
            max_daily_loss=GOLD_MAX_DAILY_LOSS,
            max_weekly_loss=GOLD_MAX_WEEKLY_LOSS, envelope="gold_intel"),
    )
}


def get_profile(name: str) -> SessionProfile:
    key = name.strip().lower()
    if key in RETIRED_PROFILES:
        raise ValueError(
            f"profile {name!r} is RETIRED and cannot run (GOLD-INTEL-001 "
            f"retired all prior profiles). Use --profile {PROFILE_NAME}.")
    if key not in PROFILES:
        raise KeyError(
            f"unknown session profile {name!r}; available: {sorted(PROFILES)}")
    return PROFILES[key]
