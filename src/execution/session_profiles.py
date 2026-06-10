"""Session risk profiles for supervised demo evaluation (Task DEMO-EVAL).

A SessionProfile names ONE approved configuration of a supervised demo
evaluation session: how long it runs, how often it polls, how many orders the
SESSION itself may send, and which RiskLimits the governor and planner enforce.

Design rules (03_RISK_POLICY.md is the authority):

- A profile may TIGHTEN the demo risk policy, never loosen it. Construction
  raises if any limit is looser than the policy bounds below, so a future
  profile (or a careless edit) cannot silently weaken risk.
- `max_orders=None` means the session imposes NO artificial per-session order
  cap: the number of trades is then governed purely by the risk policy
  (max trades/day, daily/weekly loss, open-position and duplicate checks),
  confidence tiers, regime, and setup quality. This is the serious-evaluation
  default.
- `max_orders=1` exists ONLY in the smoke profile, as an optional first-run /
  smoke-test parameter — it is not the system's design.
- The same profiles shape a future real session: real mode would add its own
  (tighter) policy bounds and readiness gates, not a different execution stack.

This module holds no credentials, performs no trading, and reads no env.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional

from src.risk.governor import RiskLimits

# 03_RISK_POLICY.md "Demo Risk Profile" — the loosest any demo profile may be.
POLICY_MAX_RISK_PER_TRADE = 0.005
POLICY_MAX_DAILY_LOSS = 0.02
POLICY_MAX_WEEKLY_LOSS = 0.05
POLICY_MAX_TRADES_PER_DAY = 3
# 03_RISK_POLICY says max 1 open trade; decision log 2026-06-10-03 resolved
# the contradiction with 20_LEVERAGE_AND_PYRAMIDING_POLICY tightest-rule-wins:
# a second position may exist ONLY as a guard-approved protected add-on.
POLICY_MAX_OPEN_POSITIONS = 2
# Live price-unit spread limit established in make_live_pipeline (LIVE-001).
POLICY_MAX_SPREAD_PRICE = 1.0

_MAX_DURATION_MINUTES = 8 * 60  # SupervisedDemoSession hard ceiling

_UNSET = object()  # "not overridden" marker (None is a meaningful value here)


@dataclass(frozen=True)
class SessionProfile:
    """One approved supervised-demo session configuration (policy-bounded)."""

    name: str
    description: str
    duration_minutes: float
    poll_seconds: float = 30.0
    # None = no artificial session cap; the risk policy governs.
    max_orders: Optional[int] = None
    max_open_positions: int = POLICY_MAX_OPEN_POSITIONS
    max_trades_per_day: int = POLICY_MAX_TRADES_PER_DAY
    max_risk_per_trade: float = POLICY_MAX_RISK_PER_TRADE
    max_daily_loss: float = POLICY_MAX_DAILY_LOSS
    max_weekly_loss: float = POLICY_MAX_WEEKLY_LOSS
    max_spread_price: float = POLICY_MAX_SPREAD_PRICE

    def __post_init__(self) -> None:
        if not (0 < self.duration_minutes <= _MAX_DURATION_MINUTES):
            raise ValueError(
                f"profile {self.name!r}: duration_minutes must be in "
                f"(0, {_MAX_DURATION_MINUTES}]"
            )
        if self.poll_seconds <= 0:
            raise ValueError(f"profile {self.name!r}: poll_seconds must be > 0")
        if self.max_orders is not None and self.max_orders < 0:
            raise ValueError(f"profile {self.name!r}: max_orders must be >= 0")
        # Profiles may only TIGHTEN the demo risk policy.
        violations = []
        if self.max_risk_per_trade > POLICY_MAX_RISK_PER_TRADE:
            violations.append("max_risk_per_trade")
        if self.max_daily_loss > POLICY_MAX_DAILY_LOSS:
            violations.append("max_daily_loss")
        if self.max_weekly_loss > POLICY_MAX_WEEKLY_LOSS:
            violations.append("max_weekly_loss")
        if self.max_trades_per_day > POLICY_MAX_TRADES_PER_DAY:
            violations.append("max_trades_per_day")
        if self.max_open_positions > POLICY_MAX_OPEN_POSITIONS:
            violations.append("max_open_positions")
        if self.max_spread_price > POLICY_MAX_SPREAD_PRICE:
            violations.append("max_spread_price")
        if violations:
            raise ValueError(
                f"profile {self.name!r} is looser than 03_RISK_POLICY.md demo "
                f"limits: {violations}"
            )

    def risk_limits(self, expected_symbol: str) -> RiskLimits:
        """The RiskLimits the governor and planner enforce for this profile."""
        return RiskLimits(
            expected_symbol=expected_symbol,
            max_risk_per_trade=self.max_risk_per_trade,
            max_daily_loss=self.max_daily_loss,
            max_weekly_loss=self.max_weekly_loss,
            max_trades_per_day=self.max_trades_per_day,
            max_open_trades=self.max_open_positions,
            max_spread=self.max_spread_price,
        )

    def with_overrides(
        self,
        *,
        duration_minutes: Optional[float] = None,
        poll_seconds: Optional[float] = None,
        max_orders: object = _UNSET,
        max_open_positions: Optional[int] = None,
    ) -> "SessionProfile":
        """Apply operator CLI overrides; __post_init__ re-validates the result.

        `max_orders` accepts None explicitly ("no session cap"), so a distinct
        sentinel marks "not overridden".
        """
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


# -- registry -----------------------------------------------------------------

PROFILES: Dict[str, SessionProfile] = {
    p.name: p
    for p in (
        SessionProfile(
            name="smoke",
            description=(
                "Short smoke validation: ONE order maximum, single position. "
                "The only profile with an artificial one-order cap."
            ),
            duration_minutes=10,
            poll_seconds=30,
            max_orders=1,
            max_open_positions=1,
        ),
        SessionProfile(
            name="evaluation",
            description=(
                "Default supervised demo evaluation (~1 hour): no artificial "
                "session order cap; risk policy, confidence, regime, and setup "
                "quality govern."
            ),
            duration_minutes=60,
            poll_seconds=30,
            max_orders=None,
        ),
        SessionProfile(
            name="london",
            description=(
                "London-session evaluation (~4 hours): start at the London "
                "open; policy-governed."
            ),
            duration_minutes=240,
            poll_seconds=60,
            max_orders=None,
        ),
        SessionProfile(
            name="newyork",
            description=(
                "New York-session evaluation (~4 hours, covers the LDN/NY "
                "overlap): start at the NY open; policy-governed."
            ),
            duration_minutes=240,
            poll_seconds=60,
            max_orders=None,
        ),
        SessionProfile(
            name="full_day",
            description=(
                "Full-day supervised evaluation (8 hours, the hard session "
                "ceiling): policy-governed."
            ),
            duration_minutes=480,
            poll_seconds=60,
            max_orders=None,
        ),
    )
}


def get_profile(name: str) -> SessionProfile:
    key = name.strip().lower()
    if key not in PROFILES:
        raise KeyError(
            f"unknown session profile {name!r}; available: {sorted(PROFILES)}"
        )
    return PROFILES[key]
