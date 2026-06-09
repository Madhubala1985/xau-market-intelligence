"""Protected pyramiding guard (Task RISK-001).

References 20_LEVERAGE_AND_PYRAMIDING_POLICY.md "Protected Pyramiding" and
"Forbidden Pyramiding".

Add to winners only. Never add to losers. Every add-on is a NEW trade thesis.
Total exposure stays capped.

An add-on (same-direction) trade is allowed only when ALL hold:
1. the existing trade is already protected at break-even or locked profit,
2. the existing trade is not moving toward its original stop-loss (not in loss),
3. the add-on has a fresh valid setup,
4. the add-on has its own thesis, invalidation, stop-loss and entry,
5. HTF bias / liquidity direction / regime still support continuation,
6. total combined XAU/USD exposure stays within the allowed cap.

This guard never places orders. It only decides whether an add-on is permitted;
the Risk Governor (P7-001) still has final authority over the add-on itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from src.data.enums import Direction
from src.data.schemas import TradeDecision

_EPS = 1e-9


class PyramidAction(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


class PyramidCheck(str, Enum):
    """Stable codes for each pyramiding check that can block an add-on."""

    ADDON_NOT_ACTIONABLE = "ADDON_NOT_ACTIONABLE"
    DIRECTION_MISMATCH = "DIRECTION_MISMATCH"
    ADDON_MISSING_RISK_PLAN = "ADDON_MISSING_RISK_PLAN"
    NO_FRESH_SETUP = "NO_FRESH_SETUP"
    CONTINUATION_NOT_SUPPORTED = "CONTINUATION_NOT_SUPPORTED"
    NO_EXISTING_TRADE = "NO_EXISTING_TRADE"
    EXISTING_NOT_PROTECTED = "EXISTING_NOT_PROTECTED"
    ADDING_TO_LOSS = "ADDING_TO_LOSS"
    EXPOSURE_CAP_EXCEEDED = "EXPOSURE_CAP_EXCEEDED"


@dataclass(frozen=True)
class OpenTrade:
    """An open XAU/USD position used to evaluate protected pyramiding."""

    symbol: str
    direction: Direction
    entry_price: float
    stop_loss: float          # CURRENT stop (may be trailed to BE / profit)
    current_price: float
    lot_size: float
    contract_size: float = 100.0  # oz per 1.0 lot (XAU/USD)

    def __post_init__(self) -> None:
        if self.direction not in (Direction.LONG, Direction.SHORT):
            raise ValueError("open trade must be LONG or SHORT")
        for name in ("entry_price", "stop_loss", "current_price", "lot_size", "contract_size"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")

    @property
    def is_protected(self) -> bool:
        """True when the stop is at break-even or locked into profit."""
        if self.direction is Direction.LONG:
            return self.stop_loss >= self.entry_price - _EPS
        return self.stop_loss <= self.entry_price + _EPS

    @property
    def in_loss(self) -> bool:
        """True when price is on the losing side of entry (moving toward stop)."""
        if self.direction is Direction.LONG:
            return self.current_price < self.entry_price - _EPS
        return self.current_price > self.entry_price + _EPS


@dataclass(frozen=True)
class PyramidLimits:
    """Total open XAU/USD exposure caps for pyramiding (demo defaults)."""

    max_total_lots: float = 0.30
    max_total_risk_usd: float = 200.0


@dataclass(frozen=True)
class PyramidResult:
    action: PyramidAction
    failed_checks: Tuple[PyramidCheck, ...] = ()
    reasons: Tuple[str, ...] = ()
    total_lots: float = 0.0
    total_risk_usd: float = 0.0

    @property
    def allowed(self) -> bool:
        return self.action is PyramidAction.ALLOW


@dataclass
class _Failures:
    checks: List[PyramidCheck] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    def add(self, check: PyramidCheck, reason: str) -> None:
        self.checks.append(check)
        self.reasons.append(reason)


class PyramidingGuard:
    """Decides whether a same-direction add-on trade is permitted."""

    def __init__(self, limits: Optional[PyramidLimits] = None) -> None:
        self._limits = limits or PyramidLimits()

    def evaluate(
        self,
        addon: TradeDecision,
        addon_lot: float,
        addon_risk_usd: float,
        existing_trades: Sequence[OpenTrade],
        *,
        fresh_setup: bool,
        continuation_supported: bool,
    ) -> PyramidResult:
        limits = self._limits
        f = _Failures()

        symbol = addon.symbol.strip().upper()
        same_symbol = [
            t for t in existing_trades if t.symbol.strip().upper() == symbol
        ]

        # The add-on must itself be a complete, actionable new trade thesis.
        if addon.direction not in (Direction.LONG, Direction.SHORT):
            f.add(
                PyramidCheck.ADDON_NOT_ACTIONABLE,
                f"add-on direction {addon.direction.value} is not actionable",
            )
        if not (addon.thesis and addon.thesis.strip()) or addon.invalidation_price is None \
                or addon.stop_loss is None or addon.entry_price is None:
            f.add(
                PyramidCheck.ADDON_MISSING_RISK_PLAN,
                "add-on needs its own thesis, invalidation, stop-loss and entry",
            )
        if not fresh_setup:
            f.add(PyramidCheck.NO_FRESH_SETUP, "add-on has no fresh valid setup")
        if not continuation_supported:
            f.add(
                PyramidCheck.CONTINUATION_NOT_SUPPORTED,
                "HTF bias / liquidity / regime no longer support continuation",
            )

        # There must be an existing same-direction position to add to.
        same_dir = [t for t in same_symbol if t.direction is addon.direction]
        if not same_dir:
            f.add(
                PyramidCheck.NO_EXISTING_TRADE,
                "no existing same-direction position to pyramid into",
            )
        if same_symbol and any(t.direction is not addon.direction for t in same_symbol):
            f.add(
                PyramidCheck.DIRECTION_MISMATCH,
                "an opposing-direction position is open; this is not pyramiding",
            )

        # Every existing same-direction trade must be protected and not in loss.
        for t in same_dir:
            if not t.is_protected:
                f.add(
                    PyramidCheck.EXISTING_NOT_PROTECTED,
                    "existing trade is not protected at break-even or locked profit",
                )
            if t.in_loss:
                f.add(
                    PyramidCheck.ADDING_TO_LOSS,
                    "existing trade is in loss / moving toward its stop-loss",
                )

        # Total combined exposure must stay within the cap.
        total_lots = sum(t.lot_size for t in same_symbol) + addon_lot
        total_risk = sum(self._open_risk(t) for t in same_symbol) + addon_risk_usd
        if total_lots > limits.max_total_lots + _EPS:
            f.add(
                PyramidCheck.EXPOSURE_CAP_EXCEEDED,
                f"total lots {total_lots:.2f} exceed cap {limits.max_total_lots}",
            )
        if total_risk > limits.max_total_risk_usd + _EPS:
            f.add(
                PyramidCheck.EXPOSURE_CAP_EXCEEDED,
                f"total open risk ${total_risk:.2f} exceeds cap "
                f"${limits.max_total_risk_usd}",
            )

        if f.checks:
            return PyramidResult(
                action=PyramidAction.BLOCK,
                failed_checks=tuple(f.checks),
                reasons=tuple(f.reasons),
                total_lots=total_lots,
                total_risk_usd=total_risk,
            )
        return PyramidResult(
            action=PyramidAction.ALLOW,
            reasons=("protected pyramiding permitted",),
            total_lots=total_lots,
            total_risk_usd=total_risk,
        )

    @staticmethod
    def _open_risk(trade: OpenTrade) -> float:
        """Remaining dollar risk to the CURRENT stop (0 once protected at/through BE)."""
        if trade.direction is Direction.LONG:
            distance = trade.current_price - trade.stop_loss
        else:
            distance = trade.stop_loss - trade.current_price
        if distance <= 0:
            return 0.0
        return distance * trade.lot_size * trade.contract_size
