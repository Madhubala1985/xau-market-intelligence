"""Session risk profiles — ONE trading profile: liquidity_intel.

The rebuild (Task LIQUIDITY-INTEL-001) collapsed every prior decision profile
into the single autonomous engine. There is exactly ONE live trading profile,
`liquidity_intel`; every earlier profile (demo_challenge, smc_challenge,
smc_v2, continuous, growth_evaluation, and the bounded evaluation profiles) is
RETIRED and CANNOT be selected — `get_profile` raises with an explicit pointer
to the new profile so an old name can never accidentally run.

A SessionProfile names the ONE approved configuration: how often the service
polls and which RiskLimits the governor and planner enforce.

Design rules (03_RISK_POLICY.md is the authority):
- A profile may TIGHTEN the risk policy, never loosen it. Construction raises
  if any limit is looser than the envelope bounds below.
- `max_orders=None` means no artificial per-session order cap: cadence is
  governed by the risk policy and the engine's quality bar — never a fixed
  artificial per-day trade cap.

This module holds no credentials, performs no trading, and reads no env.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional

from src.risk.governor import RiskLimits

# Standard demo policy bounds (03_RISK_POLICY.md) — retained as the reference
# ceiling for the "demo" envelope.
POLICY_MAX_RISK_PER_TRADE = 0.010
POLICY_MAX_DAILY_LOSS = 0.02
POLICY_MAX_WEEKLY_LOSS = 0.05
POLICY_MAX_TRADES_PER_DAY = 6
POLICY_MAX_OPEN_POSITIONS = 2
POLICY_MAX_SPREAD_PRICE = 1.0

# The single liquidity_intel envelope (owner's standing campaign anchors —
# demo only, never weakened): 3%/trade survival cap, daily 5% net pause,
# weekly 10% net stop, max 3 open, a 25/day survival CEILING (the engine's
# quality bar governs the real cadence — there is no artificial fixed per-day
# trade cap), spread <= 1.0. Real mode is forbidden for this envelope.
INTEL_MAX_RISK_PER_TRADE = 0.030
INTEL_MAX_DAILY_LOSS = 0.05
INTEL_MAX_WEEKLY_LOSS = 0.10
INTEL_MAX_TRADES_PER_DAY = 25
INTEL_MAX_OPEN_POSITIONS = 3

PROFILE_NAME = "liquidity_intel"
INTEL_PROFILE_NAMES = frozenset({PROFILE_NAME})

# Every retired profile name -> the same hard-stop message. These can never be
# constructed or selected; the guard in get_profile points the operator at the
# one live profile (replay evidence retired the SMC/challenge family).
RETIRED_PROFILES = frozenset({
    "demo_challenge", "smc_challenge", "smc_v2", "continuous",
    "growth_evaluation", "evaluation", "london", "newyork", "full_day",
    "smoke",
})

_MAX_DURATION_MINUTES = 8 * 60
_UNSET = object()


@dataclass(frozen=True)
class SessionProfile:
    """The single approved trading-session configuration (policy-bounded)."""

    name: str
    description: str
    duration_minutes: Optional[float]  # None = continuous service
    poll_seconds: float = 30.0
    max_orders: Optional[int] = None
    max_open_positions: int = INTEL_MAX_OPEN_POSITIONS
    max_trades_per_day: int = INTEL_MAX_TRADES_PER_DAY
    max_risk_per_trade: float = INTEL_MAX_RISK_PER_TRADE
    max_daily_loss: float = INTEL_MAX_DAILY_LOSS
    max_weekly_loss: float = INTEL_MAX_WEEKLY_LOSS
    max_spread_price: float = POLICY_MAX_SPREAD_PRICE
    # "demo" validates against the standard demo bounds; "liquidity_intel"
    # validates against the INTEL_* envelope and is accepted ONLY for the
    # profile named liquidity_intel.
    envelope: str = "liquidity_intel"

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
        if self.envelope not in ("demo", "liquidity_intel"):
            raise ValueError(
                f"profile {self.name!r}: unknown envelope {self.envelope!r}")
        if self.envelope == "liquidity_intel" \
                and self.name not in INTEL_PROFILE_NAMES:
            raise ValueError(
                f"profile {self.name!r}: the liquidity_intel envelope is "
                f"reserved for {sorted(INTEL_PROFILE_NAMES)}")
        if self.envelope == "liquidity_intel":
            bounds = {
                "max_risk_per_trade": INTEL_MAX_RISK_PER_TRADE,
                "max_daily_loss": INTEL_MAX_DAILY_LOSS,
                "max_weekly_loss": INTEL_MAX_WEEKLY_LOSS,
                "max_trades_per_day": INTEL_MAX_TRADES_PER_DAY,
                "max_open_positions": INTEL_MAX_OPEN_POSITIONS,
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
        violations = [
            field for field, bound in bounds.items()
            if getattr(self, field) > bound
        ]
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


# -- registry: ONE profile -----------------------------------------------------

PROFILES: Dict[str, SessionProfile] = {
    p.name: p
    for p in (
        SessionProfile(
            name=PROFILE_NAME,
            description=(
                "The single autonomous XAU/USD liquidity-intelligence engine "
                "(LIQUIDITY-INTEL-001). DEMO ONLY — never for real funds. The "
                "engine classifies the market POSTURE each cycle "
                "(TREND/LIQUIDITY_REVERSAL/RANGE_SCALP/WAIT/FLAT) from the "
                "full D1/H4/H1/M15/M5/M1 picture, liquidity map, sweeps, "
                "structure, FVG/OB and premium/discount, and decides for "
                "itself whether to engage, wait, or stay flat. Stops sit "
                "beyond the engineered liquidity (never at the naked pool); "
                "equity-scaled sizing; quality-bar gated; MT5 is the only "
                "source of truth for P&L. One execution path. Use "
                "scripts/trading_service.py --profile liquidity_intel."
            ),
            duration_minutes=None,
            poll_seconds=30,
            max_orders=None,
            max_open_positions=INTEL_MAX_OPEN_POSITIONS,
            max_trades_per_day=INTEL_MAX_TRADES_PER_DAY,
            max_risk_per_trade=INTEL_MAX_RISK_PER_TRADE,
            max_daily_loss=INTEL_MAX_DAILY_LOSS,
            max_weekly_loss=INTEL_MAX_WEEKLY_LOSS,
            envelope="liquidity_intel",
        ),
    )
}


def get_profile(name: str) -> SessionProfile:
    key = name.strip().lower()
    if key in RETIRED_PROFILES:
        raise ValueError(
            f"profile {name!r} is RETIRED and cannot run (replay evidence; "
            f"the dual decision paths were removed in LIQUIDITY-INTEL-001). "
            f"Use --profile {PROFILE_NAME}."
        )
    if key not in PROFILES:
        raise KeyError(
            f"unknown session profile {name!r}; available: {sorted(PROFILES)}"
        )
    return PROFILES[key]
