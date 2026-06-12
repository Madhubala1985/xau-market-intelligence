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

# 03_RISK_POLICY.md "Adaptive Demo Risk Policy" (decision 2026-06-10-08):
# the ABSOLUTE demo per-trade ceiling. The AdaptiveRiskEngine applies tighter
# per-phase ceilings (1.0%/0.8%/0.6%/0.5%) and an evidence-driven budget
# below them; this static bound is what the governor/planner enforce.
POLICY_MAX_RISK_PER_TRADE = 0.010
POLICY_MAX_DAILY_LOSS = 0.02
POLICY_MAX_WEEKLY_LOSS = 0.05
# Adaptive Exposure Policy (decision 2026-06-10-11): the static trades/day
# bound becomes the ADAPTIVE EXPOSURE GOVERNOR's hard maximum (reached only
# in AGGRESSIVE conditions); ordinary conditions remain at 3 and adverse
# conditions go to 1 or 0. Daily 2% / weekly 5% anchors are unchanged.
POLICY_MAX_TRADES_PER_DAY = 6
# 03_RISK_POLICY says max 1 open trade; decision log 2026-06-10-03 resolved
# the contradiction with 20_LEVERAGE_AND_PYRAMIDING_POLICY tightest-rule-wins:
# a second position may exist ONLY as a guard-approved protected add-on.
POLICY_MAX_OPEN_POSITIONS = 2
# Live price-unit spread limit established in make_live_pipeline (LIVE-001).
POLICY_MAX_SPREAD_PRICE = 1.0

# DEMO-CHALLENGE-001 (owner decision 2026-06-11-01): a SEPARATE, DEMO-ONLY
# risk envelope for the aggressive fixed-lot momentum profile. This is NOT a
# loosening of the standard demo policy: it is an explicitly owner-directed
# carve-out, available EXCLUSIVELY to the profile literally named
# "demo_challenge" (construction refuses it anywhere else), forbidden for
# real mode, and still bounded: per-trade worst case 3% (0.10 lot at the
# widest tactical stop), daily 5% pauses entries (account-survival guard,
# not conservative sizing), weekly 10% stops the service, max 3 open
# same-direction positions, stop-loss mandatory, no martingale structurally.
CHALLENGE_MAX_RISK_PER_TRADE = 0.030
CHALLENGE_MAX_DAILY_LOSS = 0.05
CHALLENGE_MAX_WEEKLY_LOSS = 0.10
CHALLENGE_MAX_TRADES_PER_DAY = 25  # owner amendment 2026-06-12-06 (was 15/10)
CHALLENGE_MAX_OPEN_POSITIONS = 3
CHALLENGE_PROFILE_NAME = "demo_challenge"
# SMC-EXECUTION-001 (owner decision 2026-06-11-03): the challenge profile is
# the institutional SMC execution mode; smc_challenge is the primary name,
# demo_challenge remains as an alias of the SAME behavior (the retail
# momentum pipeline no longer exists). Both share the challenge envelope.
SMC_PROFILE_NAME = "smc_challenge"
CHALLENGE_PROFILE_NAMES = frozenset({CHALLENGE_PROFILE_NAME, SMC_PROFILE_NAME})

_MAX_DURATION_MINUTES = 8 * 60  # SupervisedDemoSession hard ceiling

_UNSET = object()  # "not overridden" marker (None is a meaningful value here)


@dataclass(frozen=True)
class SessionProfile:
    """One approved supervised-demo session configuration (policy-bounded)."""

    name: str
    description: str
    # None = no fixed duration: the profile is for the CONTINUOUS trading
    # service, which runs until kill switch / risk shutdown / operator stop.
    # Bounded session runners must refuse a None-duration profile.
    duration_minutes: Optional[float]
    poll_seconds: float = 30.0
    # None = no artificial session cap; the risk policy governs.
    max_orders: Optional[int] = None
    max_open_positions: int = POLICY_MAX_OPEN_POSITIONS
    max_trades_per_day: int = POLICY_MAX_TRADES_PER_DAY
    max_risk_per_trade: float = POLICY_MAX_RISK_PER_TRADE
    max_daily_loss: float = POLICY_MAX_DAILY_LOSS
    max_weekly_loss: float = POLICY_MAX_WEEKLY_LOSS
    max_spread_price: float = POLICY_MAX_SPREAD_PRICE
    # "demo" validates against the standard demo policy bounds above;
    # "demo_challenge" validates against the CHALLENGE_* envelope and is
    # accepted ONLY for the profile named demo_challenge (DEMO-CHALLENGE-001).
    envelope: str = "demo"

    def __post_init__(self) -> None:
        if self.duration_minutes is not None and not (
            0 < self.duration_minutes <= _MAX_DURATION_MINUTES
        ):
            raise ValueError(
                f"profile {self.name!r}: duration_minutes must be in "
                f"(0, {_MAX_DURATION_MINUTES}] or None (continuous service)"
            )
        if self.poll_seconds <= 0:
            raise ValueError(f"profile {self.name!r}: poll_seconds must be > 0")
        if self.max_orders is not None and self.max_orders < 0:
            raise ValueError(f"profile {self.name!r}: max_orders must be >= 0")
        if self.envelope not in ("demo", "demo_challenge"):
            raise ValueError(
                f"profile {self.name!r}: unknown envelope {self.envelope!r}"
            )
        # The demo_challenge envelope is an owner-directed, DEMO-ONLY
        # carve-out (DEMO-CHALLENGE-001 / SMC-EXECUTION-001) tied to the
        # challenge profiles only — no other profile can adopt it.
        if self.envelope == "demo_challenge" \
                and self.name not in CHALLENGE_PROFILE_NAMES:
            raise ValueError(
                f"profile {self.name!r}: the demo_challenge envelope is "
                f"reserved for {sorted(CHALLENGE_PROFILE_NAMES)}"
            )
        if self.envelope == "demo_challenge":
            bounds = {
                "max_risk_per_trade": CHALLENGE_MAX_RISK_PER_TRADE,
                "max_daily_loss": CHALLENGE_MAX_DAILY_LOSS,
                "max_weekly_loss": CHALLENGE_MAX_WEEKLY_LOSS,
                "max_trades_per_day": CHALLENGE_MAX_TRADES_PER_DAY,
                "max_open_positions": CHALLENGE_MAX_OPEN_POSITIONS,
                "max_spread_price": POLICY_MAX_SPREAD_PRICE,
            }
        else:
            # Profiles may only TIGHTEN the demo risk policy.
            bounds = {
                "max_risk_per_trade": POLICY_MAX_RISK_PER_TRADE,
                "max_daily_loss": POLICY_MAX_DAILY_LOSS,
                "max_weekly_loss": POLICY_MAX_WEEKLY_LOSS,
                "max_trades_per_day": POLICY_MAX_TRADES_PER_DAY,
                "max_open_positions": POLICY_MAX_OPEN_POSITIONS,
                "max_spread_price": POLICY_MAX_SPREAD_PRICE,
            }
        violations = [
            field for field, bound in bounds.items()
            if getattr(self, field) > bound
        ]
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
            max_trades_per_day=3,
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
            max_trades_per_day=3,
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
            max_trades_per_day=3,
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
            max_trades_per_day=3,
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
            max_trades_per_day=3,
        ),
        SessionProfile(
            name="continuous",
            description=(
                "Continuous MT5 trading service (the MAIN mode): no fixed "
                "duration, no artificial order cap; runs until kill switch, "
                "risk shutdown, or operator stop. Pauses while the market is "
                "closed. Use scripts/trading_service.py."
            ),
            duration_minutes=None,
            poll_seconds=60,
            max_orders=None,
            max_trades_per_day=3,
        ),
        SessionProfile(
            name="growth_evaluation",
            description=(
                "Serious demo GROWTH evaluation (the milestone campaign "
                "$2k -> $10k -> $15k -> $25k): continuous, no artificial "
                "duration or order caps, adaptive exposure governor decides "
                "the entry allowance per conditions (up to 6/day only in "
                "AGGRESSIVE conditions; 0 in poor ones). Daily 2% / weekly "
                "5% anchors unchanged. Use scripts/trading_service.py."
            ),
            duration_minutes=None,
            poll_seconds=60,
            max_orders=None,
            max_trades_per_day=6,
        ),
        SessionProfile(
            name=CHALLENGE_PROFILE_NAME,
            description=(
                "DEPRECATED ALIAS of smc_challenge (SMC-EXECUTION-001): the "
                "retail momentum behavior was removed; this name now runs "
                "the SAME institutional SMC execution mode. DEMO ONLY."
            ),
            duration_minutes=None,
            poll_seconds=30,
            max_orders=None,
            max_open_positions=CHALLENGE_MAX_OPEN_POSITIONS,
            max_trades_per_day=CHALLENGE_MAX_TRADES_PER_DAY,
            max_risk_per_trade=CHALLENGE_MAX_RISK_PER_TRADE,
            max_daily_loss=CHALLENGE_MAX_DAILY_LOSS,
            max_weekly_loss=CHALLENGE_MAX_WEEKLY_LOSS,
            envelope="demo_challenge",
        ),
        SessionProfile(
            name=SMC_PROFILE_NAME,
            description=(
                "Institutional SMC execution mode (SMC-EXECUTION-001). DEMO "
                "ONLY — never for real funds. A trade requires ALL gates: "
                "HTF context (D1/H4/H1/M15), session/liquidity context "
                "(kill zone, Asian/session sweep, liquidity target), an SMC "
                "anchor (sweep+displacement, FVG/OB retest, break-retest, "
                "BOS/CHOCH), and an executable M5/M1 trigger with a "
                "structurally justified tactical stop. Fixed lots "
                "0.05/0.10; add-ons only onto protected winners (>=0.5R or "
                "break-even); max 3 open; MT5 is the only source of truth "
                "for P&L. Use scripts/trading_service.py --profile "
                "smc_challenge."
            ),
            duration_minutes=None,
            poll_seconds=30,
            max_orders=None,
            max_open_positions=CHALLENGE_MAX_OPEN_POSITIONS,
            max_trades_per_day=CHALLENGE_MAX_TRADES_PER_DAY,
            max_risk_per_trade=CHALLENGE_MAX_RISK_PER_TRADE,
            max_daily_loss=CHALLENGE_MAX_DAILY_LOSS,
            max_weekly_loss=CHALLENGE_MAX_WEEKLY_LOSS,
            envelope="demo_challenge",
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
