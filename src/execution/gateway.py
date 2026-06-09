"""MT5 demo execution gateway (Task P7-003).

Places MT5 DEMO orders only after Risk Governor approval and only when every demo
safety flag is set. References 05_EXECUTION_POLICY.md and the CLAUDE.md Trading
Safety Rule.

Safety invariants:
- Real-money execution is refused outright (REAL_FORBIDDEN) whenever real is
  requested (ALLOW_REAL_ORDERS, REAL_TRADING_ENABLED, or TRADING_MODE != DEMO).
- A demo order is sent ONLY when the Risk Governor approves AND
  TRADING_MODE=DEMO, REAL_TRADING_ENABLED=false, ALLOW_DEMO_ORDERS=true,
  ALLOW_MT5_ORDER_SEND=true, ALLOW_REAL_ORDERS=false.
- The DEFAULT flag state sends nothing (dry-run): order_send is never reached
  unless explicitly enabled.
- Execution may never bypass the Risk Governor (05_EXECUTION_POLICY.md final rule).
- The gateway never holds or logs credentials; it calls order_send on an
  already-connected, injected MT5 client.

The MT5 client is injected (MetaTrader5 is Windows-only); tests use a fake and
assert order_send is only called in the allowed case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Mapping, Optional, Tuple

from src.data.enums import BrokerConnectionStatus, Direction
from src.data.schemas import TradeDecision
from src.risk.governor import RiskContext, RiskDecision, RiskGovernor

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _as_bool(value: Optional[str], *, default: bool) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in _TRUE_VALUES


class ExecutionStatus(str, Enum):
    BLOCKED = "BLOCKED"
    REAL_FORBIDDEN = "REAL_FORBIDDEN"
    DRY_RUN = "DRY_RUN"          # approved but sending disabled (safe default)
    FILLED = "FILLED"            # order_send accepted
    REJECTED = "REJECTED"        # order_send rejected by broker


class OrderState(str, Enum):
    """Order lifecycle states (05_EXECUTION_POLICY.md)."""

    SIGNAL_CREATED = "SIGNAL_CREATED"
    RISK_APPROVED = "RISK_APPROVED"
    ORDER_PREPARED = "ORDER_PREPARED"
    ORDER_SENT = "ORDER_SENT"
    ORDER_ACCEPTED = "ORDER_ACCEPTED"
    ORDER_REJECTED = "ORDER_REJECTED"
    BLOCKED = "BLOCKED"


class ExecutionCheck(str, Enum):
    NOT_ACTIONABLE = "NOT_ACTIONABLE"
    WRONG_SYMBOL = "WRONG_SYMBOL"
    NO_STOP_LOSS = "NO_STOP_LOSS"
    NO_TAKE_PROFIT = "NO_TAKE_PROFIT"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    DUPLICATE = "DUPLICATE"
    RISK_BLOCKED = "RISK_BLOCKED"
    KILL_SWITCH = "KILL_SWITCH"


@dataclass(frozen=True)
class ExecutionFlags:
    """Execution permission flags (05_EXECUTION_POLICY.md). Defaults send nothing."""

    trading_mode: str = "DEMO"
    real_trading_enabled: bool = False
    allow_demo_orders: bool = False
    allow_real_orders: bool = False
    allow_mt5_order_send: bool = False

    @property
    def real_requested(self) -> bool:
        return (
            self.allow_real_orders
            or self.real_trading_enabled
            or self.trading_mode.strip().upper() != "DEMO"
        )

    @property
    def demo_send_enabled(self) -> bool:
        return (
            self.trading_mode.strip().upper() == "DEMO"
            and not self.real_trading_enabled
            and self.allow_demo_orders
            and self.allow_mt5_order_send
            and not self.allow_real_orders
        )


def load_execution_flags(env: Mapping[str, str]) -> ExecutionFlags:
    """Build ExecutionFlags from an environment mapping (no credentials read)."""
    return ExecutionFlags(
        trading_mode=str(env.get("TRADING_MODE", "DEMO")).strip() or "DEMO",
        real_trading_enabled=_as_bool(env.get("REAL_TRADING_ENABLED"), default=False),
        allow_demo_orders=_as_bool(env.get("ALLOW_DEMO_ORDERS"), default=False),
        allow_real_orders=_as_bool(env.get("ALLOW_REAL_ORDERS"), default=False),
        allow_mt5_order_send=_as_bool(env.get("ALLOW_MT5_ORDER_SEND"), default=False),
    )


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of an execution attempt."""

    status: ExecutionStatus
    states: Tuple[OrderState, ...]
    sent: bool
    order_ticket: Optional[int] = None
    failed_checks: Tuple[ExecutionCheck, ...] = ()
    risk_decision: Optional[RiskDecision] = None
    reason: str = ""


@dataclass
class _Log:
    states: List[OrderState] = field(default_factory=list)
    failed: List[ExecutionCheck] = field(default_factory=list)

    def state(self, s: OrderState) -> None:
        self.states.append(s)

    def fail(self, c: ExecutionCheck) -> None:
        self.failed.append(c)


class ExecutionGateway:
    """Sends MT5 demo orders only after risk approval and full safety checks."""

    def __init__(
        self,
        governor: RiskGovernor,
        flags: Optional[ExecutionFlags] = None,
        client: Optional[Any] = None,
        *,
        expected_symbol: str = "XAUUSD",
        magic: int = 0,
        deviation: int = 20,
        kill_switch: Optional[Any] = None,
    ) -> None:
        self._governor = governor
        self._flags = flags or ExecutionFlags()  # safe default: sends nothing
        self._client = client
        self._expected_symbol = expected_symbol.strip().upper()
        self._magic = magic
        self._deviation = deviation
        # Manual halt (DEMO-001): anything with a truthy .engaged blocks sending.
        self._kill_switch = kill_switch

    @property
    def flags(self) -> ExecutionFlags:
        """Read-only view of the execution permission flags."""
        return self._flags

    def execute(self, decision: TradeDecision, context: RiskContext) -> ExecutionResult:
        log = _Log()
        log.state(OrderState.SIGNAL_CREATED)

        # 1) Hard real-money refusal before anything else.
        if self._flags.real_requested:
            log.state(OrderState.BLOCKED)
            return self._result(
                ExecutionStatus.REAL_FORBIDDEN, log, sent=False,
                reason="real trading is forbidden; only DEMO is permitted",
            )

        # 2) Manual kill switch: an engaged halt blocks everything downstream.
        if self._kill_switch is not None and self._kill_switch.engaged:
            log.fail(ExecutionCheck.KILL_SWITCH)
            log.state(OrderState.BLOCKED)
            return self._result(
                ExecutionStatus.BLOCKED, log, sent=False,
                reason="manual kill switch is engaged; all sending halted",
            )

        # 3) Execution pre-checks (05_EXECUTION_POLICY.md checklist).
        self._pre_checks(decision, context, log)

        # 4) Risk Governor is final authority; execution can never bypass it.
        verdict = self._governor.evaluate(decision, context)
        if verdict.is_blocked:
            log.fail(ExecutionCheck.RISK_BLOCKED)

        if log.failed:
            log.state(OrderState.BLOCKED)
            return self._result(
                ExecutionStatus.BLOCKED, log, sent=False, risk_decision=verdict,
                reason="blocked by execution checks / risk governor",
            )

        log.state(OrderState.RISK_APPROVED)

        # 5) Safe default: if demo sending is not fully enabled, do not send.
        if not self._flags.demo_send_enabled:
            log.state(OrderState.ORDER_PREPARED)
            return self._result(
                ExecutionStatus.DRY_RUN, log, sent=False, risk_decision=verdict,
                reason="demo order sending disabled; dry-run only",
            )

        # 6) Prepare and send the demo order.
        log.state(OrderState.ORDER_PREPARED)
        request = self._build_request(decision, context, verdict)
        log.state(OrderState.ORDER_SENT)
        send_result = self._mt5.order_send(request)

        if self._accepted(send_result):
            log.state(OrderState.ORDER_ACCEPTED)
            return self._result(
                ExecutionStatus.FILLED, log, sent=True, risk_decision=verdict,
                order_ticket=getattr(send_result, "order", None),
                reason="demo order accepted",
            )
        log.state(OrderState.ORDER_REJECTED)
        return self._result(
            ExecutionStatus.REJECTED, log, sent=True, risk_decision=verdict,
            reason="demo order rejected by broker",
        )

    # -- checks ------------------------------------------------------------
    def _pre_checks(self, decision: TradeDecision, context: RiskContext, log: _Log) -> None:
        if decision.direction not in (Direction.LONG, Direction.SHORT):
            log.fail(ExecutionCheck.NOT_ACTIONABLE)
        if decision.symbol.strip().upper() != self._expected_symbol:
            log.fail(ExecutionCheck.WRONG_SYMBOL)
        if decision.stop_loss is None:
            log.fail(ExecutionCheck.NO_STOP_LOSS)
        if not decision.take_profits:
            log.fail(ExecutionCheck.NO_TAKE_PROFIT)
        broker = context.broker
        if broker.connection_status is not BrokerConnectionStatus.CONNECTED or not broker.trade_allowed:
            log.fail(ExecutionCheck.BROKER_DISCONNECTED)
        open_syms = {s.strip().upper() for s in context.open_symbols}
        if decision.symbol.strip().upper() in open_syms or broker.open_positions > 0:
            log.fail(ExecutionCheck.DUPLICATE)

    # -- order construction ------------------------------------------------
    @property
    def _mt5(self) -> Any:
        if self._client is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except ImportError as exc:  # pragma: no cover - platform dependent
                raise RuntimeError(
                    "MetaTrader5 is unavailable; inject a client to send orders"
                ) from exc
            self._client = mt5
        return self._client

    def _build_request(
        self, decision: TradeDecision, context: RiskContext, verdict: RiskDecision
    ) -> dict:
        mt5 = self._mt5
        is_long = decision.direction is Direction.LONG
        order_type = (
            getattr(mt5, "ORDER_TYPE_BUY", 0) if is_long else getattr(mt5, "ORDER_TYPE_SELL", 1)
        )
        volume = round(context.lot_size * verdict.size_factor, 8)
        take_profit = decision.take_profits[0] if decision.take_profits else None
        # NOTE: contains no credentials (login/password/server) by construction.
        return {
            "action": getattr(mt5, "TRADE_ACTION_DEAL", 1),
            "symbol": decision.symbol,
            "volume": volume,
            "type": order_type,
            "price": decision.entry_price,
            "sl": decision.stop_loss,
            "tp": take_profit,
            "deviation": self._deviation,
            "magic": self._magic,
            "comment": "XAUUSD demo",
        }

    def _accepted(self, send_result: Any) -> bool:
        if send_result is None:
            return False
        done = getattr(self._mt5, "TRADE_RETCODE_DONE", 10009)
        return getattr(send_result, "retcode", None) == done

    # -- result ------------------------------------------------------------
    @staticmethod
    def _result(
        status: ExecutionStatus,
        log: _Log,
        *,
        sent: bool,
        reason: str,
        order_ticket: Optional[int] = None,
        risk_decision: Optional[RiskDecision] = None,
    ) -> ExecutionResult:
        return ExecutionResult(
            status=status,
            states=tuple(log.states),
            sent=sent,
            order_ticket=order_ticket,
            failed_checks=tuple(log.failed),
            risk_decision=risk_decision,
            reason=reason,
        )
