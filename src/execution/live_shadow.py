"""Live shadow session (Task LIVE-001).

Connects read-only MT5 demo data to the DecisionPipeline and journals every
decision through the ShadowRunner. It NEVER sends orders: real-money trading is
forbidden and demo order sending is not enabled here. Each poll cycle:

    read-only MT5 data (candles + tick spread + account snapshot)
      -> PipelineInput
      -> DecisionPipeline.decide()  (no execution)
      -> TradeDecision (synthesized NO_TRADE if data is rejected)
      -> ShadowRunner (journals the decision; optional dry-run gateway)

All MT5 reads go through the injected MT5DataAdapter, which preserves the exact
broker symbol case (e.g. Exness "XAUUSDm"). Clock and sleep are injected so the
session is fully testable without real waiting or a real terminal.

Safety (CLAUDE.md Trading Safety Rule, 05_EXECUTION_POLICY.md):
- never calls order_send / any trade function,
- refuses a sending-enabled gateway,
- aborts immediately if any routed result ever reports sent=True,
- never reads, stores, or logs credentials.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, Tuple

from src.broker.mt5_data_adapter import MT5DataAdapter
from src.data.enums import DecisionStatus, Direction, Timeframe
from src.data.schemas import BrokerState, TradeDecision
from src.data.validation import DataValidator, ValidationConfig
from src.execution.gateway import ExecutionGateway
from src.execution.shadow import ShadowRunner
from src.journal.journal import TradeJournal
from src.risk.governor import RiskContext, RiskGovernor, RiskLimits
from src.risk.news_guard import NewsRiskGuard
from src.risk.state_tracker import RiskStateTracker
from src.strategy.pipeline import (
    DecisionPipeline,
    PipelineEngines,
    PipelineInput,
    PipelineResult,
)


def make_live_pipeline(
    canonical_symbol: str,
    *,
    max_spread_price: float = 1.0,
    max_staleness: timedelta = timedelta(minutes=30),
    threshold_profile: str = "current",
) -> DecisionPipeline:
    """Build a DecisionPipeline configured for LIVE XAU/USD data.

    Live configuration differs from the engine defaults in three ways:
    - the validator must not treat normal XAU session/trading-break gaps as
      blocking (06_DATA_POLICY.md: session gaps are the session engine's job),
    - stale live data must be rejected (no decisions on a frozen feed),
    - the Risk Governor must expect the CANONICAL form of the broker symbol
      (e.g. Exness "XAUUSDm" canonicalizes to "XAUUSDM" in TradeDecision).

    `max_spread_price` is in price units (ask - bid), matching the spread this
    module feeds into RiskContext. The default (1.0 USD) is far stricter than
    the governor's points-oriented default of 50.
    """
    canonical = canonical_symbol.strip().upper()
    engines = PipelineEngines(
        validator=DataValidator(
            ValidationConfig(
                expected_symbol=canonical,
                detect_gaps=False,
                max_staleness=max_staleness,
            )
        ),
        governor=RiskGovernor(
            RiskLimits(expected_symbol=canonical, max_spread=max_spread_price)
        ),
    )
    # Execution-quality scoring must degrade on the same (price-unit) spread
    # scale the governor enforces, not the points-oriented default.
    return DecisionPipeline(engines, max_spread=max_spread_price,
                            threshold_profile=threshold_profile)


@dataclass(frozen=True)
class LiveCycleResult:
    """Outcome of one decision cycle (credential-free).

    Carries the supervised-session evidence required by LIVE-002: the decision,
    its no-trade reason, confidence/uncertainty scores, and the Risk Governor's
    verdict (action + reasons).
    """

    time_utc: datetime
    stage: str
    direction: str
    approved: bool
    reason: str
    decision_id: str
    spread_price: float
    lot_size: float
    confidence: Optional[float] = None
    uncertainty: Optional[float] = None
    risk_action: Optional[str] = None
    risk_reasons: Tuple[str, ...] = ()
    sent: bool = False  # must always be False in shadow mode

    def to_dict(self) -> dict:
        return {
            "time_utc": self.time_utc.isoformat(),
            "stage": self.stage,
            "direction": self.direction,
            "approved": self.approved,
            "reason": self.reason,
            "decision_id": self.decision_id,
            "spread_price": self.spread_price,
            "lot_size": self.lot_size,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "risk_action": self.risk_action,
            "risk_reasons": list(self.risk_reasons),
            "sent": self.sent,
        }


@dataclass(frozen=True)
class LiveShadowReport:
    """Summary of a live shadow session (credential-free)."""

    symbol: str
    started_at_utc: datetime
    ended_at_utc: datetime
    cycles: int
    decisions_logged: int
    actionable_decisions: int
    approved_decisions: int
    orders_sent: int  # must always be 0
    journal_path: str
    results: Tuple[LiveCycleResult, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "task": "LIVE-001",
            "symbol": self.symbol,
            "started_at_utc": self.started_at_utc.isoformat(),
            "ended_at_utc": self.ended_at_utc.isoformat(),
            "cycles": self.cycles,
            "decisions_logged": self.decisions_logged,
            "actionable_decisions": self.actionable_decisions,
            "approved_decisions": self.approved_decisions,
            "orders_sent": self.orders_sent,
            "journal_path": self.journal_path,
            "results": [r.to_dict() for r in self.results],
        }


class LiveShadowSession:
    """Polls read-only MT5 data into the pipeline and journals decisions only."""

    def __init__(
        self,
        *,
        adapter: MT5DataAdapter,
        pipeline: DecisionPipeline,
        journal: TradeJournal,
        symbol: str,
        gateway: Optional[ExecutionGateway] = None,
        news_guard: Optional[NewsRiskGuard] = None,
        exec_timeframe: Timeframe = Timeframe.M5,
        exec_count: int = 300,
        h4_count: int = 180,
        daily_count: int = 120,
        risk_pct: float = 0.005,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        # Shadow mode must never be able to send (mirror ShadowRunner's guard).
        if gateway is not None and gateway.flags.demo_send_enabled:
            raise ValueError(
                "live shadow requires a non-sending gateway (demo send disabled)"
            )
        self._adapter = adapter
        self._pipeline = pipeline
        self._journal = journal
        self._symbol = symbol
        # Risk enforcement inputs (daily/weekly loss, trade counts, streaks)
        # are derived from the journal so the governor sees real history
        # instead of permanent zeros (03_RISK_POLICY.md).
        self._risk_state = RiskStateTracker(journal)
        # News risk (F-5): in shadow mode the flag is raised only when a real
        # source says so (manual block or calendar window). The ORDER path
        # (DemoTradePlanner) additionally fail-closes on an unknown state.
        self._news_guard = news_guard
        self._gateway = gateway
        self._exec_tf = exec_timeframe
        self._exec_count = exec_count
        self._h4_count = h4_count
        self._daily_count = daily_count
        self._risk_pct = risk_pct
        self._monotonic = monotonic
        self._sleep = sleep
        self._now = now

    # -- one cycle ---------------------------------------------------------
    def decide_once(self) -> LiveCycleResult:
        """Run a single read-only decision cycle and journal the decision."""
        now = self._now()

        exec_candles = self._adapter.fetch_candles(self._exec_tf, self._exec_count)
        daily = self._adapter.fetch_candles(Timeframe.D1, self._daily_count)
        h4 = self._adapter.fetch_candles(Timeframe.H4, self._h4_count)
        tick = self._adapter.fetch_tick()
        spread_price = round(tick.spread, 6)
        broker = self._adapter.fetch_broker_state(now)
        risk_state = self._risk_state.snapshot(now, broker.balance)
        news_risk = False
        if self._news_guard is not None:
            news_state = self._news_guard.assess(now)
            news_risk = news_state.known and news_state.risky

        result = self._pipeline.decide(
            PipelineInput(
                symbol=self._symbol,
                exec_candles=exec_candles,
                daily_candles=daily,
                h4_candles=h4,
                broker=broker,
                current_spread=spread_price,
                risk_pct=self._risk_pct,
                news_risk=news_risk,
                daily_loss_pct=risk_state.daily_loss_pct,
                weekly_loss_pct=risk_state.weekly_loss_pct,
                trades_today=risk_state.trades_today,
                consecutive_losses=risk_state.consecutive_losses,
                open_symbols=risk_state.open_symbols,
                now=now,
            )
        )
        decision = self._as_decision(result, now)

        # Journal via a one-shot ShadowRunner cycle: this reuses the shadow
        # no-send guard and the dry-run gateway path (never sends an order).
        context_builder = None
        if self._gateway is not None:
            context_builder = self._make_context_builder(broker, spread_price, result)
        runner = ShadowRunner(
            lambda _history: decision,
            self._journal,
            gateway=self._gateway,
            context_builder=context_builder,
        )
        shadow = runner.run([exec_candles[-1]])
        if shadow.orders_sent != 0:  # pragma: no cover - defensive safety
            raise RuntimeError("live shadow produced a sent order; aborting")

        return LiveCycleResult(
            time_utc=now,
            stage=result.stage.value,
            direction=decision.direction.value,
            approved=bool(result.approved),
            reason=result.reason,
            decision_id=decision.decision_id,
            spread_price=spread_price,
            lot_size=result.lot_size,
            confidence=(
                result.confidence.confidence if result.confidence is not None else None
            ),
            uncertainty=(
                result.confidence.uncertainty if result.confidence is not None else None
            ),
            risk_action=(
                result.risk.action.value if result.risk is not None else None
            ),
            risk_reasons=(
                tuple(result.risk.reasons) if result.risk is not None else ()
            ),
            sent=False,
        )

    # -- session loop ------------------------------------------------------
    def run(
        self,
        *,
        poll_seconds: float,
        duration_seconds: Optional[float] = None,
        max_cycles: Optional[int] = None,
    ) -> LiveShadowReport:
        """Poll decisions until duration elapses or max_cycles is reached.

        At least one stop condition (duration_seconds or max_cycles) is
        required, so the session can never run unbounded.
        """
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        if duration_seconds is None and max_cycles is None:
            raise ValueError("a stop condition is required: duration_seconds or max_cycles")
        if max_cycles is not None and max_cycles <= 0:
            raise ValueError("max_cycles must be positive")
        started = self._now()
        t0 = self._monotonic()
        results: List[LiveCycleResult] = []

        while True:
            results.append(self.decide_once())
            if max_cycles is not None and len(results) >= max_cycles:
                break
            elapsed = self._monotonic() - t0
            if duration_seconds is not None and elapsed >= duration_seconds:
                break
            if duration_seconds is not None:
                self._sleep(min(poll_seconds, duration_seconds - elapsed))
            else:
                self._sleep(poll_seconds)

        ended = self._now()
        actionable = sum(
            1 for r in results if r.direction in (Direction.LONG.value, Direction.SHORT.value)
        )
        approved = sum(1 for r in results if r.approved)
        return LiveShadowReport(
            symbol=self._symbol,
            started_at_utc=started,
            ended_at_utc=ended,
            cycles=len(results),
            decisions_logged=len(results),
            actionable_decisions=actionable,
            approved_decisions=approved,
            orders_sent=0,
            journal_path=str(self._journal.path),
            results=tuple(results),
        )

    # -- helpers -----------------------------------------------------------
    def _as_decision(self, result: PipelineResult, now: datetime) -> TradeDecision:
        if result.decision is not None:
            return result.decision
        # Data rejected (or no decision produced): journal an explicit NO_TRADE.
        return TradeDecision(
            decision_id=f"live-{now.strftime('%Y%m%dT%H%M%S')}Z",
            time_utc=now,
            symbol=self._symbol,
            direction=Direction.NO_TRADE,
            status=DecisionStatus.NO_TRADE,
            reason=result.reason or "no decision produced",
        )

    def _make_context_builder(
        self, broker: BrokerState, spread_price: float, result: PipelineResult
    ) -> Callable[[object, TradeDecision], RiskContext]:
        lot = result.lot_size or 0.0
        size_hint = result.confidence.size_factor if result.confidence else 1.0

        def builder(_candle: object, _decision: TradeDecision) -> RiskContext:
            return RiskContext(
                broker=broker,
                current_spread=spread_price,
                lot_size=lot,
                intended_risk_pct=self._risk_pct,
                size_factor_hint=size_hint,
            )

        return builder
