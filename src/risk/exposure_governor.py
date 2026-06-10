"""Adaptive Exposure Governor (Task OPERATIONAL-INTELLIGENCE-001).

Static "N trades/day" thinking is replaced by a condition-driven exposure
state. The governor decides — per cycle — how many ENTRIES the session may
still take and how much may be open, from market quality and account state:

- LOCKDOWN    daily/weekly loss limit reached: zero entries (the survival
              anchors are untouched and still enforced downstream too),
- BLOCKED     news block/unknown, dangerous volatility, or spread at max,
- DEFENSIVE   losses/drawdown/news-caution: one careful entry at most,
- NORMAL      ordinary conditions: the standard allowance,
- AGGRESSIVE  strong directional evidence (high confluence + MTF alignment)
              in a kill-zone session with a clean day: extended allowance,
              still bounded by the profile's hard maximum.

Hard guarantees:
- the governor can only TIGHTEN: its allowance never exceeds the profile's
  static bound (which itself obeys 03_RISK_POLICY's Adaptive Exposure
  Policy), and daily 2% / weekly 5% loss anchors are untouched;
- open positions are ALWAYS still managed — exposure gates new entries only;
- no martingale/grid/revenge structurally: losses and drawdown can only
  shrink the allowance, never raise it.
"""

from __future__ import annotations

from dataclasses import dataclass


class ExposureState:
    LOCKDOWN = "LOCKDOWN"
    BLOCKED = "BLOCKED"
    DEFENSIVE = "DEFENSIVE"
    NORMAL = "NORMAL"
    AGGRESSIVE = "AGGRESSIVE"


_KILL_ZONES = {"LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"}


@dataclass(frozen=True)
class ExposureInputs:
    confluence_score: float
    mtf_score: float
    session: str                  # SessionType value or ""
    volatility_dangerous: bool
    spread_ratio: float
    news_blocked: bool            # manual block / HIGH active / unknown
    news_caution: bool
    daily_loss_pct: float
    weekly_loss_pct: float
    max_daily_loss: float
    max_weekly_loss: float
    consecutive_losses: int
    trades_today: int
    open_positions: int
    hard_max_trades: int          # profile static bound (policy-checked)
    hard_max_open: int


@dataclass(frozen=True)
class ExposureDecision:
    state: str
    max_trades_today: int
    trades_remaining: int
    max_open: int
    reason: str

    @property
    def allows_entry(self) -> bool:
        return self.trades_remaining > 0

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "max_trades_today": self.max_trades_today,
            "trades_remaining": self.trades_remaining,
            "max_open": self.max_open,
            "reason": self.reason,
        }


class AdaptiveExposureGovernor:
    """Decides the adaptive entry allowance for the current conditions."""

    def __init__(
        self,
        *,
        defensive_cap: int = 1,
        normal_cap: int = 3,
        aggressive_cap: int = 6,
        aggressive_confluence: float = 0.70,
        aggressive_mtf: float = 0.75,
    ) -> None:
        self._defensive_cap = defensive_cap
        self._normal_cap = normal_cap
        self._aggressive_cap = aggressive_cap
        self._aggr_confluence = aggressive_confluence
        self._aggr_mtf = aggressive_mtf

    def decide(self, i: ExposureInputs) -> ExposureDecision:
        def make(state, cap, max_open, reason) -> ExposureDecision:
            cap = min(cap, i.hard_max_trades)
            max_open = min(max_open, i.hard_max_open)
            return ExposureDecision(
                state=state, max_trades_today=cap,
                trades_remaining=max(0, cap - i.trades_today),
                max_open=max_open, reason=reason,
            )

        # Survival anchors first (also enforced by the risk governor/service).
        if (
            i.daily_loss_pct >= i.max_daily_loss
            or i.weekly_loss_pct >= i.max_weekly_loss
        ):
            return make(ExposureState.LOCKDOWN, 0, 0,
                        "daily/weekly loss limit reached; entries locked")
        if i.news_blocked:
            return make(ExposureState.BLOCKED, 0, 0,
                        "news blocked/unknown; entries blocked")
        if i.volatility_dangerous:
            return make(ExposureState.BLOCKED, 0, 0,
                        "dangerous volatility; entries blocked")
        if i.spread_ratio >= 1.0:
            return make(ExposureState.BLOCKED, 0, 0,
                        "spread at/above the allowed max")

        if (
            i.consecutive_losses >= 2
            or i.daily_loss_pct >= 0.01
            or i.weekly_loss_pct >= 0.03
            or i.news_caution
        ):
            return make(
                ExposureState.DEFENSIVE, self._defensive_cap, 1,
                f"defensive: losses={i.consecutive_losses}, "
                f"daily_dd={i.daily_loss_pct:.3f}, "
                f"news_caution={i.news_caution}",
            )

        if (
            i.confluence_score >= self._aggr_confluence
            and i.mtf_score >= self._aggr_mtf
            and i.session in _KILL_ZONES
            and i.consecutive_losses == 0
            and i.daily_loss_pct < 0.005
        ):
            return make(
                ExposureState.AGGRESSIVE, self._aggressive_cap, 2,
                f"aggressive: confluence={i.confluence_score:.4f}, "
                f"mtf={i.mtf_score:.2f}, session={i.session}, clean day",
            )

        return make(ExposureState.NORMAL, self._normal_cap, 2,
                    "normal conditions")
