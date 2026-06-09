"""Risk Governor (Task P7-001).

The Risk Governor has FINAL authority over execution (INIT-003 / 03_RISK_POLICY.md):
no signal, confidence score, hypothesis, futures confirmation, or order-flow proxy
may override it. It evaluates a proposed TradeDecision against broker state and the
risk limits and returns APPROVE / REDUCE / BLOCK.

It NEVER places orders. It only decides permission; the execution gateway (P7-003)
is a separate component.

Mandatory blocking checks (07_TEST_POLICY.md Risk Tests):
- no stop-loss, too much risk, daily loss reached, weekly loss reached,
- spread too high, invalid lot size, broker state unknown, duplicate trade,
- wrong symbol.
Plus exposure / trades-per-day / consecutive-loss / non-actionable guards.

All failing checks are accumulated, so a decision reports every reason it was
blocked. If any blocking check fails, the result is BLOCK regardless of confidence
(confidence can never bypass risk).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet, List, Optional, Tuple

from src.data.enums import BrokerConnectionStatus, Direction
from src.data.schemas import BrokerState, TradeDecision


class RiskAction(str, Enum):
    APPROVE = "APPROVE"
    REDUCE = "REDUCE"
    BLOCK = "BLOCK"


class RiskCheck(str, Enum):
    """Stable codes for each risk check that can block a trade."""

    NON_ACTIONABLE = "NON_ACTIONABLE"
    WRONG_SYMBOL = "WRONG_SYMBOL"
    BROKER_STATE_UNKNOWN = "BROKER_STATE_UNKNOWN"
    NO_STOP_LOSS = "NO_STOP_LOSS"
    INVALID_LOT_SIZE = "INVALID_LOT_SIZE"
    SPREAD_TOO_HIGH = "SPREAD_TOO_HIGH"
    RISK_TOO_HIGH = "RISK_TOO_HIGH"
    DAILY_LOSS_REACHED = "DAILY_LOSS_REACHED"
    WEEKLY_LOSS_REACHED = "WEEKLY_LOSS_REACHED"
    MAX_TRADES_REACHED = "MAX_TRADES_REACHED"
    MAX_OPEN_TRADES = "MAX_OPEN_TRADES"
    DUPLICATE_TRADE = "DUPLICATE_TRADE"
    CONSECUTIVE_LOSSES = "CONSECUTIVE_LOSSES"
    SCORING_BLOCKED = "SCORING_BLOCKED"


@dataclass(frozen=True)
class RiskLimits:
    """Risk limits. Defaults are the demo profile (INIT-007 / 03_RISK_POLICY.md)."""

    expected_symbol: str = "XAUUSD"
    max_risk_per_trade: float = 0.005
    max_daily_loss: float = 0.02
    max_weekly_loss: float = 0.05
    max_trades_per_day: int = 3
    max_open_trades: int = 1
    max_consecutive_losses: Optional[int] = None  # demo: not enforced by default
    max_spread: float = 50.0  # same unit as the spread reported in context
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01


@dataclass(frozen=True)
class RiskContext:
    """Live account/broker/risk inputs at decision time."""

    broker: BrokerState
    current_spread: float
    lot_size: float
    intended_risk_pct: float
    daily_loss_pct: float = 0.0
    weekly_loss_pct: float = 0.0
    trades_today: int = 0
    consecutive_losses: int = 0
    open_symbols: FrozenSet[str] = frozenset()
    size_factor_hint: float = 1.0  # from the confidence engine (P6-002)
    # Set ONLY by the demo planner after PyramidingGuard explicitly ALLOWED a
    # protected add-on (20_LEVERAGE_AND_PYRAMIDING_POLICY.md). Permits the
    # duplicate-symbol check to pass for that one add-on, and only while the
    # configured max_open_trades leaves room. Defaults to False: a plain
    # duplicate same-symbol trade stays blocked.
    protected_addon: bool = False


@dataclass(frozen=True)
class RiskDecision:
    """The governor's verdict for one TradeDecision."""

    action: RiskAction
    size_factor: float
    failed_checks: Tuple[RiskCheck, ...] = ()
    reasons: Tuple[str, ...] = ()

    @property
    def approved(self) -> bool:
        return self.action is not RiskAction.BLOCK

    @property
    def is_blocked(self) -> bool:
        return self.action is RiskAction.BLOCK


@dataclass
class _Failures:
    checks: List[RiskCheck] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    def add(self, check: RiskCheck, reason: str) -> None:
        self.checks.append(check)
        self.reasons.append(reason)


class RiskGovernor:
    """Evaluates risk for a proposed trade. Never executes orders."""

    def __init__(self, limits: Optional[RiskLimits] = None) -> None:
        self._limits = limits or RiskLimits()

    def evaluate(self, decision: TradeDecision, context: RiskContext) -> RiskDecision:
        limits = self._limits
        f = _Failures()

        # A non-actionable decision is nothing to approve.
        if decision.direction not in (Direction.LONG, Direction.SHORT):
            return RiskDecision(
                action=RiskAction.BLOCK,
                size_factor=0.0,
                failed_checks=(RiskCheck.NON_ACTIONABLE,),
                reasons=(f"decision direction {decision.direction.value} is not actionable",),
            )

        self._check_symbol(decision, f)
        self._check_broker(context.broker, f)
        self._check_stop_loss(decision, f)
        self._check_lot(context.lot_size, f)
        self._check_spread(context.current_spread, f)
        self._check_risk(context.intended_risk_pct, f)
        self._check_losses(context, f)
        self._check_counts(context, f)
        self._check_duplicate(decision, context, f)

        if f.checks:
            return RiskDecision(
                action=RiskAction.BLOCK,
                size_factor=0.0,
                failed_checks=tuple(f.checks),
                reasons=tuple(f.reasons),
            )

        # No blocking failure: scoring may still reduce or veto size.
        hint = context.size_factor_hint
        if hint <= 0.0:
            return RiskDecision(
                action=RiskAction.BLOCK,
                size_factor=0.0,
                failed_checks=(RiskCheck.SCORING_BLOCKED,),
                reasons=("confidence/uncertainty scoring blocked the trade",),
            )
        if hint < 1.0:
            return RiskDecision(
                action=RiskAction.REDUCE,
                size_factor=hint,
                reasons=(f"approved with reduced size (factor {hint})",),
            )
        return RiskDecision(
            action=RiskAction.APPROVE,
            size_factor=1.0,
            reasons=("all risk checks passed",),
        )

    # -- individual checks -------------------------------------------------
    def _check_symbol(self, decision: TradeDecision, f: _Failures) -> None:
        expected = self._limits.expected_symbol.strip().upper()
        if decision.symbol.strip().upper() != expected:
            f.add(
                RiskCheck.WRONG_SYMBOL,
                f"symbol {decision.symbol!r} != expected {expected!r}",
            )

    def _check_broker(self, broker: BrokerState, f: _Failures) -> None:
        if (
            broker.connection_status is not BrokerConnectionStatus.CONNECTED
            or not broker.trade_allowed
            or broker.balance is None
        ):
            f.add(
                RiskCheck.BROKER_STATE_UNKNOWN,
                "broker not connected / trading not allowed / balance unknown",
            )

    def _check_stop_loss(self, decision: TradeDecision, f: _Failures) -> None:
        if decision.stop_loss is None:
            f.add(RiskCheck.NO_STOP_LOSS, "trade has no stop-loss")

    def _check_lot(self, lot_size: float, f: _Failures) -> None:
        limits = self._limits
        if (
            lot_size <= 0
            or lot_size < limits.min_lot
            or lot_size > limits.max_lot
            or not self._aligned(lot_size, limits.lot_step)
        ):
            f.add(RiskCheck.INVALID_LOT_SIZE, f"invalid lot size {lot_size}")

    def _check_spread(self, current_spread: float, f: _Failures) -> None:
        if current_spread > self._limits.max_spread:
            f.add(
                RiskCheck.SPREAD_TOO_HIGH,
                f"spread {current_spread} exceeds max {self._limits.max_spread}",
            )

    def _check_risk(self, intended_risk_pct: float, f: _Failures) -> None:
        if intended_risk_pct > self._limits.max_risk_per_trade:
            f.add(
                RiskCheck.RISK_TOO_HIGH,
                f"risk {intended_risk_pct} exceeds max {self._limits.max_risk_per_trade}",
            )

    def _check_losses(self, context: RiskContext, f: _Failures) -> None:
        limits = self._limits
        if context.daily_loss_pct >= limits.max_daily_loss:
            f.add(
                RiskCheck.DAILY_LOSS_REACHED,
                f"daily loss {context.daily_loss_pct} >= max {limits.max_daily_loss}",
            )
        if context.weekly_loss_pct >= limits.max_weekly_loss:
            f.add(
                RiskCheck.WEEKLY_LOSS_REACHED,
                f"weekly loss {context.weekly_loss_pct} >= max {limits.max_weekly_loss}",
            )
        if (
            limits.max_consecutive_losses is not None
            and context.consecutive_losses >= limits.max_consecutive_losses
        ):
            f.add(
                RiskCheck.CONSECUTIVE_LOSSES,
                f"consecutive losses {context.consecutive_losses} reached limit",
            )

    def _check_counts(self, context: RiskContext, f: _Failures) -> None:
        limits = self._limits
        if context.trades_today >= limits.max_trades_per_day:
            f.add(
                RiskCheck.MAX_TRADES_REACHED,
                f"trades today {context.trades_today} >= max {limits.max_trades_per_day}",
            )
        if context.broker.open_positions >= limits.max_open_trades:
            f.add(
                RiskCheck.MAX_OPEN_TRADES,
                f"open positions {context.broker.open_positions} >= max {limits.max_open_trades}",
            )

    def _check_duplicate(
        self, decision: TradeDecision, context: RiskContext, f: _Failures
    ) -> None:
        if decision.symbol.strip().upper() not in {
            s.strip().upper() for s in context.open_symbols
        }:
            return
        # A same-symbol position is open. The ONLY permitted case is a
        # protected add-on (PyramidingGuard ALLOWED, flagged by the planner)
        # while the open count is still below the configured max_open_trades.
        if (
            context.protected_addon
            and context.broker.open_positions < self._limits.max_open_trades
        ):
            return
        f.add(
            RiskCheck.DUPLICATE_TRADE,
            f"a position on {decision.symbol} is already open",
        )

    @staticmethod
    def _aligned(value: float, step: float) -> bool:
        if step <= 0:
            return True
        units = value / step
        return abs(units - round(units)) <= 1e-9
