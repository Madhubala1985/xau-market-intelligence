"""Post-trade attribution + a rolling performance store (Task GOLD-ALPHA-001).

The learning loop the model is built around: when a trade closes, classify WHY
it won or (especially) lost, keep a rolling record keyed by setup_type + regime,
and expose an EV adjustment the decision engine reads BEFORE the next trade —
so setups/regimes that are repeatedly failing for an attributable reason get
down-weighted instead of being re-tried on hope.

Pure, deterministic, credential-free. Holds no MT5 handles and sends nothing.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, Optional, Tuple


class LossReason(str, Enum):
    BAD_ENTRY = "BAD_ENTRY"
    BAD_SL_PLACEMENT = "BAD_SL_PLACEMENT"
    LIQUIDITY_TRAP = "LIQUIDITY_TRAP"
    WRONG_REGIME = "WRONG_REGIME"
    LATE_ENTRY = "LATE_ENTRY"
    SPREAD_VOLATILITY = "SPREAD_VOLATILITY"
    WEAK_CONFIRMATION = "WEAK_CONFIRMATION"
    INVALID_THESIS = "INVALID_THESIS"
    WIN = "WIN"  # not a loss; recorded for symmetry


@dataclass(frozen=True)
class TradeContext:
    """What the engine knew at entry — recorded so a close can be attributed."""

    setup_type: str
    regime: str
    direction: str          # "LONG"/"SHORT"
    entry: float
    stop: float
    target: float
    score: float            # EV-ish score at entry
    p_win: float
    displacement: float     # impulse size vs ATR at entry
    spread_ratio: float     # spread / max_spread at entry
    confirmation: float     # 0..1 strength of the trigger/confirmation
    stop_beyond_pool: bool  # was the SL placed past the engineered liquidity?
    extended: bool          # was price already far into an extended move?


def classify_outcome(
    ctx: TradeContext,
    *,
    won: bool,
    r_multiple: float,
    swept_then_reversed: bool = False,
) -> LossReason:
    """Heuristic WHY for a closed trade. `swept_then_reversed` is True when the
    stop was taken and price then resumed the trade's direction (a stop hunt)."""
    if won:
        return LossReason.WIN
    # A stop taken right where liquidity rests, then price reverses our way, is
    # the single most important failure to catch and stop repeating.
    if swept_then_reversed and not ctx.stop_beyond_pool:
        return LossReason.LIQUIDITY_TRAP
    if not ctx.stop_beyond_pool:
        return LossReason.BAD_SL_PLACEMENT
    if ctx.regime in ("POST_SPIKE_CHOP", "DANGEROUS_CHOP", "LOW_QUALITY_CHOP",
                      "RANGE_DAY"):
        return LossReason.WRONG_REGIME
    if ctx.spread_ratio >= 0.8:
        return LossReason.SPREAD_VOLATILITY
    if ctx.extended:
        return LossReason.LATE_ENTRY
    if ctx.confirmation < 0.5:
        return LossReason.WEAK_CONFIRMATION
    if ctx.score < 0.25:
        return LossReason.BAD_ENTRY
    return LossReason.INVALID_THESIS


@dataclass
class _Bucket:
    outcomes: Deque[float] = field(default_factory=lambda: deque(maxlen=20))
    reasons: Dict[str, int] = field(default_factory=dict)

    def record(self, r_multiple: float, reason: LossReason) -> None:
        self.outcomes.append(r_multiple)
        self.reasons[reason.value] = self.reasons.get(reason.value, 0) + 1

    @property
    def n(self) -> int:
        return len(self.outcomes)

    @property
    def win_rate(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(1 for r in self.outcomes if r > 0) / len(self.outcomes)

    @property
    def avg_r(self) -> float:
        return sum(self.outcomes) / len(self.outcomes) if self.outcomes else 0.0


class PerformanceStore:
    """Rolling per-(setup_type, regime) outcomes + an EV adjustment the engine
    reads before trading. Recently-failing setups are down-weighted; a setup
    repeatedly hit by the SAME attributable failure is penalised harder."""

    MIN_SAMPLE = 4         # need at least this many before adjusting
    PENALTY_PER_LOW_WR = 0.18  # p_win penalty when recent WR is poor
    TRAP_PENALTY = 0.12    # extra when the same setup keeps getting trapped

    def __init__(self) -> None:
        self._by_key: Dict[Tuple[str, str], _Bucket] = {}
        self._global_reasons: Dict[str, int] = {}

    def _key(self, setup_type: str, regime: str) -> Tuple[str, str]:
        return (setup_type, regime)

    def record(self, ctx: TradeContext, *, won: bool, r_multiple: float,
               reason: LossReason) -> None:
        bucket = self._by_key.setdefault(self._key(ctx.setup_type, ctx.regime),
                                         _Bucket())
        bucket.record(r_multiple, reason)
        self._global_reasons[reason.value] = (
            self._global_reasons.get(reason.value, 0) + 1)

    def p_win_adjustment(self, setup_type: str, regime: str) -> float:
        """A signed adjustment (<= 0) applied to the engine's p_win estimate
        for this setup/regime based on recent realised performance."""
        bucket = self._by_key.get(self._key(setup_type, regime))
        if bucket is None or bucket.n < self.MIN_SAMPLE:
            return 0.0
        adj = 0.0
        if bucket.win_rate < 0.30:
            adj -= self.PENALTY_PER_LOW_WR
        elif bucket.win_rate < 0.40:
            adj -= self.PENALTY_PER_LOW_WR / 2
        # repeated identical failure (e.g. liquidity traps) on this setup
        worst = max(bucket.reasons.items(), key=lambda kv: kv[1], default=None)
        if worst and worst[0] in (
            LossReason.LIQUIDITY_TRAP.value, LossReason.WRONG_REGIME.value
        ) and worst[1] >= 3:
            adj -= self.TRAP_PENALTY
        return adj

    def summary(self, setup_type: str, regime: str) -> str:
        bucket = self._by_key.get(self._key(setup_type, regime))
        if bucket is None or bucket.n == 0:
            return "no history"
        top = sorted(bucket.reasons.items(), key=lambda kv: -kv[1])[:2]
        reasons = ", ".join(f"{k}x{v}" for k, v in top)
        return (f"n={bucket.n} wr={bucket.win_rate:.0%} avgR={bucket.avg_r:+.2f}"
                + (f" [{reasons}]" if reasons else ""))

    def global_reason_counts(self) -> Dict[str, int]:
        return dict(self._global_reasons)
