"""Live shadow mode (Task P11-001).

Runs live (or replayed) market analysis and logs every decision WITHOUT sending
real-money orders. References 05_EXECUTION_POLICY.md (live shadow mode) and the
CLAUDE.md Trading Safety Rule.

Shadow mode is analysis + journaling only. It never sends orders. If an
ExecutionGateway is provided, it is used solely to record what the gated pipeline
WOULD decide (dry-run), and the runner refuses to operate unless that gateway has
order sending disabled. If any routed result ever reports sent=True, the runner
raises immediately (defensive; this must never happen).

Strategy contract:
    strategy(history: Sequence[Candle]) -> Optional[TradeDecision]
where history is candles[:t+1] (strictly causal). Returned decisions (including
WAIT / NO_TRADE) are journaled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from src.data.enums import Direction
from src.data.schemas import Candle, TradeDecision
from src.execution.gateway import ExecutionGateway, ExecutionResult
from src.journal.journal import TradeJournal
from src.risk.governor import RiskContext

Strategy = Callable[[Sequence[Candle]], Optional[TradeDecision]]
ContextBuilder = Callable[[Candle, TradeDecision], RiskContext]


@dataclass(frozen=True)
class ShadowReport:
    """Summary of a shadow run."""

    decisions_logged: int
    decisions: Tuple[TradeDecision, ...]
    executions: Tuple[ExecutionResult, ...]
    orders_sent: int  # must always be 0 in shadow mode


class ShadowRunner:
    """Analyzes live/replayed candles, journals decisions, and never sends orders."""

    def __init__(
        self,
        strategy: Strategy,
        journal: TradeJournal,
        *,
        gateway: Optional[ExecutionGateway] = None,
        context_builder: Optional[ContextBuilder] = None,
    ) -> None:
        if gateway is not None:
            # Shadow mode must not be able to send: refuse a sending-enabled gateway.
            if gateway.flags.demo_send_enabled:
                raise ValueError(
                    "shadow mode requires a non-sending gateway (demo send disabled)"
                )
            if context_builder is None:
                raise ValueError("context_builder is required when a gateway is provided")
        self._strategy = strategy
        self._journal = journal
        self._gateway = gateway
        self._context_builder = context_builder

    def run(self, candles: Sequence[Candle]) -> ShadowReport:
        logged = 0
        decisions: List[TradeDecision] = []
        executions: List[ExecutionResult] = []

        for t in range(len(candles)):
            history = candles[: t + 1]  # strictly causal
            decision = self._strategy(history)
            if decision is None:
                continue

            # Log every decision (trade and no-trade).
            self._journal.log_decision(decision)
            logged += 1
            decisions.append(decision)

            # Optionally record the gated (dry-run) outcome -- never send.
            if self._gateway is not None and decision.direction in (
                Direction.LONG,
                Direction.SHORT,
            ):
                context = self._context_builder(candles[t], decision)
                result = self._gateway.execute(decision, context)
                if result.sent:
                    raise RuntimeError(
                        "shadow mode produced a sent order; aborting (safety violation)"
                    )
                executions.append(result)

        return ShadowReport(
            decisions_logged=logged,
            decisions=tuple(decisions),
            executions=tuple(executions),
            orders_sent=0,
        )
