"""Supervised MT5 demo trading session (Tasks DEMO-002 / DEMO-EVAL).

The ONLY component that may lead to a demo order being sent — and it still
cannot send anything itself: every order goes through DemoTradePlanner (sizing
+ pyramiding + governor) and then ExecutionGateway (its own checks + flags +
kill switch). Real trading is refused at construction.

Hard session preconditions (constructor raises otherwise):
- explicit operator confirmation token ("START SUPERVISED DEMO"),
- a READY DemoPreflight report produced on this host,
- a gateway that does not request real trading.

Per cycle:
 1. kill switch check — engaged ends the session immediately,
 2. read-only data: candles, tick, broker state, open positions,
 3. close detection: journal OPEN records whose broker position vanished get
    a closing record with realized P&L from deal history (so loss limits see
    real losses); unknown P&L stays OPEN -> reconciliation fails closed,
 4. reconciliation (orphans block entries),
 5. DecisionPipeline decision (journaled, every cycle),
 6. stop protection: break-even/trailing proposals applied ONLY via
    gateway.modify_stop (never widens, kill-switch aware),
 7. entry: planner plan -> gateway execute; a FILLED order is journaled with
    its MT5 ticket (notes="ticket=<n>") for future reconciliation.

Order limits (DEMO-EVAL): `max_orders=None` (the default) imposes NO
artificial per-session cap — how much the session trades is governed by the
risk policy (max trades/day, daily/weekly loss, open-position and duplicate
checks), confidence tiers, regime, and setup quality. An integer cap remains
available for smoke runs (session profile "smoke" sets 1).

Modes (separated honestly in the report):
- DEMO_LIVE: gateway flags enable demo sending; FILLED orders are real MT5
  demo orders with broker tickets.
- DRY_RUN: sending disabled; approved plans still flow planner -> gateway and
  are counted as `orders_simulated` (rehearsal of the same code path, nothing
  reaches order_send and nothing is journaled as an open trade).
Shadow analysis (no gateway at all) lives in LiveShadowSession, not here.

Every step is recorded as a SessionEvent, and every cycle adds a CycleStat
(regime, session, confidence, spread, news/risk state, entry action) so the
post-session evaluation and reflection reports can analyze the session.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, List, Optional, Tuple

from src.broker.mt5_data_adapter import BrokerPosition, MT5DataAdapter
from src.data.enums import DecisionStatus, Direction, Timeframe, TradeOutcome
from src.data.schemas import BrokerState, TradeDecision, TradeRecord
from src.execution.demo_planner import DemoTradePlanner, TradePlan
from src.execution.gateway import ExecutionGateway, ExecutionStatus
from src.execution.kill_switch import KillSwitch
from src.execution.positions import PositionReconciler, ReconciliationReport
from src.execution.preflight import PreflightReport
from src.journal.journal import TradeJournal
from src.risk.exposure_governor import (
    AdaptiveExposureGovernor,
    ExposureDecision,
    ExposureInputs,
)
from src.risk.governor import RiskContext
from src.risk.leverage_sizing import AccountSnapshot
from src.risk.news_guard import NewsRiskGuard
from src.risk.state_tracker import (
    RiskStateSnapshot,
    RiskStateTracker,
    collapse_records,
)
from src.strategy.pipeline import DecisionPipeline, PipelineInput, PipelineResult
from src.trade_management.position_manager import PositionProtectionManager

CONFIRMATION_TOKEN = "START SUPERVISED DEMO"
_MAX_SESSION_SECONDS = 8 * 3600  # hard ceiling on any supervised session

_TICKET_NOTE = "ticket={ticket}"


@dataclass(frozen=True)
class SessionEvent:
    time_utc: datetime
    kind: str
    detail: str  # MUST be credential-free

    def to_dict(self) -> dict:
        return {
            "time_utc": self.time_utc.isoformat(),
            "kind": self.kind,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CycleStat:
    """Per-cycle evaluation data (credential-free) for post-session analysis."""

    time_utc: datetime
    stage: str
    direction: str
    approved: bool
    reason: str
    spread_price: float
    confidence: Optional[float] = None
    uncertainty: Optional[float] = None
    regime: Optional[str] = None
    session: Optional[str] = None
    htf_bias: Optional[str] = None
    news_known: bool = False
    news_risky: bool = False
    news_status: str = ""  # NEWS_CLEAR/BLOCK/UNKNOWN/HIGH_IMPACT_SOON/ACTIVE
    risk_action: Optional[str] = None
    # What the entry path did this cycle:
    # NONE (not actionable/approved) | SENT | SIMULATED | REJECTED |
    # PLAN_BLOCKED | ENTRY_BLOCKED | CAP_REACHED | ORDER_ERROR
    entry_action: str = "NONE"
    entry_detail: str = ""
    # INTELLIGENCE-001: graded reasoning, surfaced per cycle.
    regime_subtype: Optional[str] = None
    mtf_direction: Optional[str] = None
    mtf_score: Optional[float] = None
    confluence_score: Optional[float] = None
    risk_tier: Optional[str] = None
    risk_pct: Optional[float] = None
    intel: dict = field(default_factory=dict)  # full reasoning detail (JSON-safe)

    def to_dict(self) -> dict:
        return {
            "time_utc": self.time_utc.isoformat(),
            "stage": self.stage,
            "direction": self.direction,
            "approved": self.approved,
            "reason": self.reason,
            "spread_price": self.spread_price,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "regime": self.regime,
            "session": self.session,
            "htf_bias": self.htf_bias,
            "news_known": self.news_known,
            "news_risky": self.news_risky,
            "news_status": self.news_status,
            "risk_action": self.risk_action,
            "entry_action": self.entry_action,
            "entry_detail": self.entry_detail,
            "regime_subtype": self.regime_subtype,
            "mtf_direction": self.mtf_direction,
            "mtf_score": self.mtf_score,
            "confluence_score": self.confluence_score,
            "risk_tier": self.risk_tier,
            "risk_pct": self.risk_pct,
            "intel": dict(self.intel),
        }


@dataclass(frozen=True)
class CycleOutcome:
    """Everything one cycle produced (credential-free).

    Returned by run_cycle() so the continuous trading service (CONTINUOUS-001)
    can drive THIS exact execution stack — same planner, governor, gateway,
    journal — and render live terminal progress without duplicating logic.
    """

    stat: CycleStat
    bid: float
    ask: float
    positions: Tuple[BrokerPosition, ...]
    reconciliation_clean: bool
    risk: "RiskStateSnapshot"
    events: Tuple[SessionEvent, ...]  # only the events of THIS cycle
    orders_sent_total: int
    orders_simulated_total: int
    violations_total: int
    decisions_total: int
    sent_ticket: Optional[int] = None


@dataclass(frozen=True)
class DemoSessionReport:
    """Summary of one supervised demo session (credential-free)."""

    symbol: str
    mode: str  # DEMO_LIVE | DRY_RUN
    started_at_utc: datetime
    ended_at_utc: datetime
    cycles: int
    decisions_logged: int
    entries_blocked: int
    orders_sent: int        # real MT5 demo orders (FILLED, ticket captured)
    orders_simulated: int   # DRY_RUN approvals (sending disabled rehearsal)
    orders_rejected: int
    stop_updates: int
    violations: int
    verdict: str  # CLEAN | HALTED_BY_KILL_SWITCH | ATTENTION_REQUIRED
    halt_reason: str
    final_reconciliation: Optional[dict]
    profile: str = ""
    max_orders: Optional[int] = None
    events: Tuple[SessionEvent, ...] = field(default_factory=tuple)
    cycle_stats: Tuple[CycleStat, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "task": "DEMO-002",
            "symbol": self.symbol,
            "mode": self.mode,
            "profile": self.profile,
            "max_orders": self.max_orders,
            "started_at_utc": self.started_at_utc.isoformat(),
            "ended_at_utc": self.ended_at_utc.isoformat(),
            "cycles": self.cycles,
            "decisions_logged": self.decisions_logged,
            "entries_blocked": self.entries_blocked,
            "orders_sent": self.orders_sent,
            "orders_simulated": self.orders_simulated,
            "orders_rejected": self.orders_rejected,
            "stop_updates": self.stop_updates,
            "violations": self.violations,
            "verdict": self.verdict,
            "halt_reason": self.halt_reason,
            "final_reconciliation": self.final_reconciliation,
            "events": [e.to_dict() for e in self.events],
            "cycle_stats": [c.to_dict() for c in self.cycle_stats],
        }


class SupervisedDemoSession:
    """Runs the supervised demo loop. Orders flow ONLY through the gateway."""

    def __init__(
        self,
        *,
        adapter: MT5DataAdapter,
        pipeline: DecisionPipeline,
        planner: DemoTradePlanner,
        gateway: ExecutionGateway,
        journal: TradeJournal,
        symbol: str,
        confirmation: str,
        preflight: PreflightReport,
        news_guard: NewsRiskGuard,
        kill_switch: KillSwitch,
        reconciler: Optional[PositionReconciler] = None,
        protection: Optional[PositionProtectionManager] = None,
        max_orders: Optional[int] = None,
        profile_name: str = "",
        # OPERATIONAL-001: adaptive exposure (tighten-only; None = off).
        exposure_governor: Optional[AdaptiveExposureGovernor] = None,
        hard_max_trades: int = 3,
        hard_max_open: int = 2,
        max_daily_loss: float = 0.02,
        max_weekly_loss: float = 0.05,
        risk_pct: float = 0.005,
        # SMC-EXECUTION-001: after this many consecutive MT5-verified losses,
        # new entries pause for the cooldown (open positions still managed).
        loss_cooldown_losses: int = 2,
        loss_cooldown_minutes: float = 30.0,
        exec_timeframe: Timeframe = Timeframe.M5,
        exec_count: int = 300,
        h4_count: int = 180,
        daily_count: int = 120,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if confirmation != CONFIRMATION_TOKEN:
            raise ValueError(
                f"supervised demo requires the explicit confirmation token "
                f"{CONFIRMATION_TOKEN!r}"
            )
        if not preflight.ready:
            raise ValueError(
                "DEMO-001 preflight is not READY; supervised demo refused"
            )
        if gateway.flags.real_requested:
            raise ValueError("real trading is forbidden; gateway requests real mode")
        if max_orders is not None and max_orders < 0:
            raise ValueError("max_orders must be >= 0 (or None: policy-governed)")
        self._adapter = adapter
        self._pipeline = pipeline
        self._planner = planner
        self._gateway = gateway
        self._journal = journal
        self._symbol = symbol
        self._news_guard = news_guard
        self._kill_switch = kill_switch
        self._reconciler = reconciler or PositionReconciler()
        self._protection = protection or PositionProtectionManager()
        self._max_orders = max_orders
        self._profile_name = profile_name
        self._exposure = exposure_governor
        self._hard_max_trades = hard_max_trades
        self._hard_max_open = hard_max_open
        self._max_daily_loss = max_daily_loss
        self._max_weekly_loss = max_weekly_loss
        self._risk_pct = risk_pct
        self._loss_cooldown_losses = loss_cooldown_losses
        self._loss_cooldown_minutes = loss_cooldown_minutes
        self._exec_tf = exec_timeframe
        self._exec_count = exec_count
        self._h4_count = h4_count
        self._daily_count = daily_count
        self._risk_state = RiskStateTracker(journal)
        self._monotonic = monotonic
        self._sleep = sleep
        self._now = now
        # session counters
        self._events: List[SessionEvent] = []
        self._cycle_stats: List[CycleStat] = []
        self._orders_sent = 0
        self._orders_simulated = 0
        self._orders_rejected = 0
        self._stop_updates = 0
        self._entries_blocked = 0
        self._decisions_logged = 0
        self._violations = 0
        self._halted = False
        self._halt_reason = ""
        # last-cycle snapshots (filled by _cycle; consumed by run_cycle)
        self._last_bid = 0.0
        self._last_ask = 0.0
        self._last_positions: List[BrokerPosition] = []
        self._last_risk_state: Optional[RiskStateSnapshot] = None
        self._last_sent_ticket: Optional[int] = None
        # BROKER-EXECUTION-001: broker diagnostics of THIS cycle's send
        # attempt (surfaced in CycleStat.intel and the terminal).
        self._last_order_rejection: Optional[dict] = None
        # SMC-EXECUTION-001: MT5-verified accounting snapshot of THIS cycle.
        self._last_accounting: Optional[dict] = None

    # -- session loop --------------------------------------------------------
    def run(
        self,
        *,
        duration_seconds: float,
        poll_seconds: float,
        max_cycles: Optional[int] = None,
    ) -> DemoSessionReport:
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        if duration_seconds <= 0 or duration_seconds > _MAX_SESSION_SECONDS:
            raise ValueError(
                f"duration must be in (0, {_MAX_SESSION_SECONDS}] seconds"
            )
        started = self._now()
        t0 = self._monotonic()
        cycles = 0
        last_reconciliation: Optional[ReconciliationReport] = None

        while True:
            if self._kill_switch.engaged:
                self._halted = True
                self._halt_reason = "kill switch engaged"
                self._event("HALT", "kill switch engaged; session ends")
                break
            last_reconciliation = self._cycle()
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                break
            elapsed = self._monotonic() - t0
            if elapsed >= duration_seconds:
                break
            self._sleep(min(poll_seconds, duration_seconds - elapsed))

        ended = self._now()
        verdict = self._verdict(last_reconciliation)
        return DemoSessionReport(
            symbol=self._symbol,
            mode=(
                "DEMO_LIVE" if self._gateway.flags.demo_send_enabled else "DRY_RUN"
            ),
            started_at_utc=started,
            ended_at_utc=ended,
            cycles=cycles,
            decisions_logged=self._decisions_logged,
            entries_blocked=self._entries_blocked,
            orders_sent=self._orders_sent,
            orders_simulated=self._orders_simulated,
            orders_rejected=self._orders_rejected,
            stop_updates=self._stop_updates,
            violations=self._violations,
            verdict=verdict,
            halt_reason=self._halt_reason,
            final_reconciliation=(
                last_reconciliation.to_dict() if last_reconciliation else None
            ),
            profile=self._profile_name,
            max_orders=self._max_orders,
            events=tuple(self._events),
            cycle_stats=tuple(self._cycle_stats),
        )

    # -- public counters (read-only; used by the continuous service) ----------
    @property
    def orders_sent(self) -> int:
        return self._orders_sent

    @property
    def orders_simulated(self) -> int:
        return self._orders_simulated

    @property
    def orders_rejected(self) -> int:
        return self._orders_rejected

    @property
    def decisions_logged(self) -> int:
        return self._decisions_logged

    @property
    def violations(self) -> int:
        return self._violations

    # -- startup warmstart (OPERATIONAL-001) -----------------------------------
    def build_warmstart(self) -> dict:
        """Analyse FULL multi-timeframe history once at startup (read-only).

        Fetches the same real MT5 candle depth the live loop uses (D1/H4/H1/
        M15/M5/M1), runs one pipeline analysis, and returns the starting
        market context for the terminal report. Journals nothing, sends
        nothing.
        """
        now = self._now()
        exec_candles = self._adapter.fetch_candles(self._exec_tf, self._exec_count)
        daily = self._adapter.fetch_candles(Timeframe.D1, self._daily_count)
        h4 = self._adapter.fetch_candles(Timeframe.H4, self._h4_count)
        m15 = self._fetch_optional(Timeframe.M15, 200) or []
        h1 = self._fetch_optional(Timeframe.H1, 120) or []
        m1 = self._fetch_optional(Timeframe.M1, 60) or []
        tick = self._adapter.fetch_tick()
        broker = self._adapter.fetch_broker_state(now)
        result = self._pipeline.decide(PipelineInput(
            symbol=self._symbol, exec_candles=exec_candles,
            daily_candles=daily, h4_candles=h4,
            m15_candles=m15 or None, h1_candles=h1 or None,
            m1_candles=m1 or None,
            broker=broker, current_spread=round(tick.spread, 6),
            risk_pct=self._risk_pct, now=now,
        ))
        ctx = result.context
        chop = getattr(ctx, "chop", None) if ctx else None
        confluence = getattr(ctx, "confluence", None) if ctx else None
        if chop is not None:
            phase = chop.subtype.value
        elif ctx is not None and ctx.regime is not None:
            phase = ctx.regime.value
        else:
            phase = "UNKNOWN"
        decision = result.decision
        return {
            "candles": {"d1": len(daily), "h4": len(h4), "h1": len(h1),
                        "m15": len(m15), "m5": len(exec_candles),
                        "m1": len(m1)},
            "htf_bias": (ctx.htf_bias.value
                         if ctx is not None and ctx.htf_bias else None),
            "mtf": (ctx.mtf.to_dict()
                    if ctx is not None and ctx.mtf is not None else None),
            "regime": (ctx.regime.value
                       if ctx is not None and ctx.regime else None),
            "regime_reason": getattr(ctx, "regime_reason", ""),
            "market_phase": phase,
            "asian": (ctx.asian.to_dict()
                      if ctx is not None and ctx.asian is not None else None),
            "price_zone": (ctx.price_zone.value
                           if ctx is not None and ctx.price_zone else None),
            "volatility": (ctx.volatility.state.value
                           if ctx is not None and ctx.volatility else None),
            "displacement": getattr(ctx, "displacement_ratio", 0.0),
            "confluence": (confluence.score if confluence else None),
            "candidate": (
                confluence.direction.value
                if confluence and confluence.direction else None
            ),
            "thesis": (
                decision.thesis
                if decision is not None and decision.thesis else None
            ),
            "last_price": exec_candles[-1].close if exec_candles else None,
        }

    # -- one cycle (public: the continuous service drives this directly) ------
    def run_cycle(self) -> CycleOutcome:
        """Run ONE full cycle and return everything it produced.

        Same execution stack as run(): data -> close detection ->
        reconciliation -> pipeline -> stop protection -> planner -> gateway.
        The caller (continuous service) owns looping, pausing, and stopping.
        """
        events_before = len(self._events)
        self._last_sent_ticket = None
        reconciliation = self._cycle()
        return CycleOutcome(
            stat=self._cycle_stats[-1],
            bid=self._last_bid,
            ask=self._last_ask,
            positions=tuple(self._last_positions),
            reconciliation_clean=reconciliation.clean,
            risk=self._last_risk_state,
            events=tuple(self._events[events_before:]),
            orders_sent_total=self._orders_sent,
            orders_simulated_total=self._orders_simulated,
            violations_total=self._violations,
            decisions_total=self._decisions_logged,
            sent_ticket=self._last_sent_ticket,
        )

    def _cycle(self) -> ReconciliationReport:
        now = self._now()
        self._last_order_rejection = None
        exec_candles = self._adapter.fetch_candles(self._exec_tf, self._exec_count)
        daily = self._adapter.fetch_candles(Timeframe.D1, self._daily_count)
        h4 = self._adapter.fetch_candles(Timeframe.H4, self._h4_count)
        # TRUE multi-timeframe fetches (INTELLIGENCE-002); a failed fetch
        # degrades honestly to None (pipeline aggregates and labels it).
        m15 = self._fetch_optional(Timeframe.M15, 200)
        h1 = self._fetch_optional(Timeframe.H1, 120)
        m1 = self._fetch_optional(Timeframe.M1, 60)
        tick = self._adapter.fetch_tick()
        spread_price = round(tick.spread, 6)
        broker = self._adapter.fetch_broker_state(now)
        positions = self._adapter.fetch_positions()
        self._last_bid, self._last_ask = tick.bid, tick.ask
        self._last_positions = positions

        # Close detection BEFORE reconciliation: a stopped-out position is a
        # normal lifecycle event, not an orphan — IF its P&L is recoverable.
        self._detect_closes(positions, now)
        reconciliation = self._reconciler.reconcile(
            positions, self._journal.records()
        )
        if not reconciliation.clean:
            self._event("RECONCILE", f"NOT CLEAN: {reconciliation.detail}")

        risk_state = self._risk_state.snapshot(now, broker.balance)
        self._last_risk_state = risk_state
        # SMC-EXECUTION-001: MT5 is the ONLY source of truth for money facts.
        self._last_accounting = self._assess_accounting(
            now, broker, positions, risk_state
        )
        news = self._news_guard.assess(now)

        result = self._pipeline.decide(
            PipelineInput(
                symbol=self._symbol,
                exec_candles=exec_candles,
                daily_candles=daily,
                h4_candles=h4,
                m15_candles=m15,
                h1_candles=h1,
                m1_candles=m1,
                broker=broker,
                current_spread=spread_price,
                risk_pct=self._risk_pct,
                news_risk=news.known and news.risky,
                news_caution=getattr(news, "caution", False),
                daily_loss_pct=risk_state.daily_loss_pct,
                weekly_loss_pct=risk_state.weekly_loss_pct,
                trades_today=risk_state.trades_today,
                consecutive_losses=risk_state.consecutive_losses,
                open_symbols=risk_state.open_symbols,
                now=now,
            )
        )
        decision = self._as_decision(result, now)
        self._journal.log_decision(decision)
        self._decisions_logged += 1
        self._event(
            "DECISION",
            f"{decision.direction.value} stage={result.stage.value} "
            f"approved={result.approved} reason={result.reason}",
        )

        # Protect open positions (stop updates only via the gateway).
        self._manage_positions(positions, exec_candles)

        # Adaptive exposure (OPERATIONAL-001): condition-driven entry
        # allowance; tighten-only and entries-only (management continues).
        exposure = self._assess_exposure(result, news, risk_state, positions)

        # Entry path.
        entry_action, entry_detail = "NONE", ""
        if decision.direction in (Direction.LONG, Direction.SHORT) and result.approved:
            entry_action, entry_detail = self._try_entry(
                decision, result, broker, spread_price, positions,
                reconciliation, news, risk_state, now, exposure=exposure,
            )

        context = result.context
        chop = getattr(context, "chop", None) if context is not None else None
        mtf = getattr(context, "mtf", None) if context is not None else None
        confluence = (
            getattr(context, "confluence", None) if context is not None else None
        )
        adaptive = getattr(result, "adaptive_risk", None)
        self._cycle_stats.append(
            CycleStat(
                time_utc=now,
                stage=result.stage.value,
                direction=decision.direction.value,
                approved=bool(result.approved),
                reason=result.reason,
                spread_price=spread_price,
                confidence=(
                    result.confidence.confidence
                    if result.confidence is not None else None
                ),
                uncertainty=(
                    result.confidence.uncertainty
                    if result.confidence is not None else None
                ),
                regime=(
                    context.regime.value
                    if context is not None and context.regime is not None else None
                ),
                session=(
                    context.session.value
                    if context is not None and context.session is not None else None
                ),
                htf_bias=(
                    context.htf_bias.value
                    if context is not None and context.htf_bias is not None else None
                ),
                news_known=news.known,
                news_risky=news.risky,
                news_status=getattr(news, "status", ""),
                risk_action=(
                    result.risk.action.value if result.risk is not None else None
                ),
                entry_action=entry_action,
                entry_detail=entry_detail,
                regime_subtype=(chop.subtype.value if chop is not None else None),
                mtf_direction=(
                    mtf.direction.value
                    if mtf is not None and mtf.direction is not None else None
                ),
                mtf_score=(mtf.score if mtf is not None else None),
                confluence_score=(
                    confluence.score if confluence is not None else None
                ),
                risk_tier=(adaptive.tier.value if adaptive is not None else None),
                risk_pct=(adaptive.risk_pct if adaptive is not None else None),
                intel=self._record_accounting(
                    self._record_order_rejection(
                        self._record_challenge(
                            positions,
                            self._record_exposure(
                                exposure,
                                self._record_sizing(
                                    result, self._intel_of(context, adaptive)
                                ),
                            ),
                        ),
                    ),
                ),
            )
        )
        return reconciliation

    @staticmethod
    def _intel_of(context, adaptive) -> dict:
        """Full per-cycle reasoning detail (JSON-safe, credential-free)."""
        if context is None:
            return {}
        intel: dict = {
            "regime_reason": getattr(context, "regime_reason", ""),
            "setup_kind": getattr(context, "setup_kind", ""),
            "displacement_ratio": round(
                getattr(context, "displacement_ratio", 0.0), 3
            ),
        }
        chop = getattr(context, "chop", None)
        if chop is not None:
            intel["chop"] = chop.to_dict()
        mtf = getattr(context, "mtf", None)
        if mtf is not None:
            intel["mtf"] = mtf.to_dict()
        confluence = getattr(context, "confluence", None)
        if confluence is not None:
            intel["confluence"] = confluence.to_dict()
        price_zone = getattr(context, "price_zone", None)
        if price_zone is not None:
            intel["price_zone"] = price_zone.value
        volatility = getattr(context, "volatility", None)
        if volatility is not None:
            intel["volatility"] = volatility.to_dict()
        asian = getattr(context, "asian", None)
        if asian is not None:
            intel["asian"] = asian.to_dict()
        m1 = getattr(context, "m1", None)
        if m1 is not None:
            intel["m1"] = m1.to_dict()
        intel["macro_pressure"] = getattr(context, "macro_pressure",
                                          "UNAVAILABLE")
        if adaptive is not None:
            intel["adaptive_risk"] = adaptive.to_dict()
        # DEMO-CHALLENGE-001: momentum-profile reasoning (display/journal).
        challenge = getattr(context, "challenge", None)
        if challenge:
            intel["challenge"] = dict(challenge)
        return intel

    def _record_sizing(self, result, intel: dict) -> dict:
        lot_decision = getattr(result, "lot_decision", None)
        if lot_decision is not None:
            intel["sizing"] = lot_decision.to_dict()
        return intel

    @staticmethod
    def _record_exposure(exposure, intel: dict) -> dict:
        if exposure is not None:
            intel["exposure"] = exposure.to_dict()
        return intel

    def _record_order_rejection(self, intel: dict) -> dict:
        """BROKER-EXECUTION-001: broker send diagnostics for this cycle."""
        if self._last_order_rejection:
            intel["order_rejection"] = dict(self._last_order_rejection)
        return intel

    def _record_accounting(self, intel: dict) -> dict:
        if self._last_accounting:
            intel["accounting"] = dict(self._last_accounting)
        return intel

    # -- MT5-verified accounting (SMC-EXECUTION-001) -----------------------------
    _MILESTONES = {"PHASE_1": 10000, "PHASE_2": 15000, "PHASE_3": 25000,
                   "PHASE_4": None}

    def _assess_accounting(
        self,
        now: datetime,
        broker: BrokerState,
        positions: List[BrokerPosition],
        risk_state: "RiskStateSnapshot",
    ) -> dict:
        """Money facts straight from MT5; verified=False blocks new entries.

        - realized_daily_pnl comes from MT5 deal history (today's trade
          deals: profit + commission + swap), NEVER from internal points,
        - floating_pnl is the sum of the open positions' MT5 profit fields,
        - anything missing makes the snapshot UNVERIFIED (fail closed).
        """
        day_start = now.astimezone(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        realized = None
        fetch = getattr(self._adapter, "fetch_realized_pnl_since", None)
        if fetch is not None:
            try:
                realized = fetch(day_start, now=now)
            except Exception:  # noqa: BLE001 - unknown stays unknown
                realized = None
        floating_known = all(p.profit is not None for p in positions)
        floating = (
            round(sum(p.profit for p in positions), 2)
            if positions and floating_known else 0.0 if not positions else None
        )
        equity = broker.equity if broker.equity is not None else broker.balance
        verified = (
            broker.balance is not None
            and broker.equity is not None
            and realized is not None
            and floating_known
        )
        try:
            from src.risk.adaptive_risk import CapitalPhase
            phase = CapitalPhase.of(equity or 0.0).value
        except Exception:  # noqa: BLE001 - phase label must never crash a cycle
            phase = "UNKNOWN"
        return {
            "mt5_balance": broker.balance,
            "mt5_equity": broker.equity,
            "mt5_free_margin": broker.free_margin,
            "realized_daily_pnl": realized,
            "floating_pnl": floating,
            "consecutive_losses": risk_state.consecutive_losses,
            "verified": bool(verified),
            "capital_phase": phase,
            "next_milestone": self._MILESTONES.get(phase),
        }

    def _last_loss_close(self) -> Optional[datetime]:
        losses = [
            r.closed_at_utc
            for r in collapse_records(self._journal.records())
            if r.outcome is TradeOutcome.LOSS and r.closed_at_utc is not None
        ]
        return max(losses) if losses else None

    def _seconds_since_last_entry(self, now: datetime) -> Optional[float]:
        opens = [
            r.opened_at_utc
            for r in collapse_records(self._journal.records())
            if r.outcome is TradeOutcome.OPEN and r.opened_at_utc is not None
        ]
        if not opens:
            return None
        return max(0.0, (now - max(opens)).total_seconds())

    def _record_challenge(self, positions, intel: dict) -> dict:
        """DEMO-CHALLENGE-001: add the live first-trade/add-on view to the
        challenge reasoning (display only; the planner enforces the rules)."""
        challenge = intel.get("challenge")
        if not challenge:
            return intel
        if positions:
            first = min(positions, key=lambda p: p.ticket)
            profit = first.profit
            if profit is None:
                challenge["first_trade_profit_state"] = "UNKNOWN"
            elif profit > 0:
                challenge["first_trade_profit_state"] = f"IN_PROFIT({profit:+.2f})"
            else:
                challenge["first_trade_profit_state"] = (
                    f"NOT_IN_PROFIT({profit:+.2f})"
                )
            all_in_profit = all(
                p.profit is not None and p.profit > 0 for p in positions
            )
            challenge["add_on_allowed"] = (
                "yes" if all_in_profit and len(positions) < self._hard_max_open
                else "no"
            )
        else:
            challenge["first_trade_profit_state"] = "NO_OPEN_POSITION"
            challenge["add_on_allowed"] = "n/a (no position yet)"
        return intel

    def _assess_exposure(
        self, result, news, risk_state, positions
    ) -> Optional[ExposureDecision]:
        if self._exposure is None:
            return None
        context = result.context
        confluence = getattr(context, "confluence", None) if context else None
        mtf = getattr(context, "mtf", None) if context else None
        volatility = getattr(context, "volatility", None) if context else None
        session_type = (
            context.session.value
            if context is not None and context.session is not None else ""
        )
        return self._exposure.decide(ExposureInputs(
            confluence_score=(confluence.score if confluence else 0.0),
            mtf_score=(mtf.score if mtf else 0.0),
            session=session_type,
            volatility_dangerous=bool(volatility and volatility.dangerous),
            spread_ratio=0.0,  # spread blocking lives in governor/confluence
            news_blocked=(not news.known) or news.risky,
            news_caution=getattr(news, "caution", False),
            daily_loss_pct=risk_state.daily_loss_pct,
            weekly_loss_pct=risk_state.weekly_loss_pct,
            max_daily_loss=self._max_daily_loss,
            max_weekly_loss=self._max_weekly_loss,
            consecutive_losses=risk_state.consecutive_losses,
            trades_today=risk_state.trades_today,
            open_positions=len(positions),
            hard_max_trades=self._hard_max_trades,
            hard_max_open=self._hard_max_open,
        ))

    # -- close detection ---------------------------------------------------------
    def _detect_closes(self, positions: List[BrokerPosition], now: datetime) -> None:
        """Detect closed positions from MT5 DEAL HISTORY only.

        SMC-EXECUTION-001: the outcome is the sign of the MT5 net deal P&L
        (profit + commission + swap of the position's own trade deals). A
        negative MT5 close can never be journaled as WIN; an unverifiable
        close stays OPEN (fail-closed) and blocks via reconciliation.
        """
        open_tickets = {p.ticket for p in positions}
        latest = collapse_records(self._journal.records())
        for record in latest:
            if record.outcome is not TradeOutcome.OPEN:
                continue
            ticket = self._ticket_of(record)
            if ticket is None or ticket in open_tickets:
                continue
            closed = self._fetch_closed(ticket)
            if closed is None:
                self._violations += 1
                self._event(
                    "VIOLATION",
                    f"position {ticket} closed but MT5 history is "
                    f"unverifiable; record stays OPEN (fail-closed; resolve "
                    f"manually)",
                )
                continue
            net = closed.net_pnl
            outcome = (
                TradeOutcome.WIN if net > 0
                else TradeOutcome.LOSS if net < 0
                else TradeOutcome.BREAKEVEN
            )
            closed_at = closed.close_time_utc or now
            # A close can never precede its open (clock skew / partial
            # history protection; the schema enforces the same invariant).
            if record.opened_at_utc is not None and closed_at < record.opened_at_utc:
                closed_at = record.opened_at_utc
            self._journal.log_record(
                record.model_copy(update={
                    "outcome": outcome, "pnl": net,
                    "closed_at_utc": closed_at,
                    "exit_price": closed.close_price,
                })
            )
            self._event(
                "CLOSE_DETECTED",
                f"ticket={ticket} outcome={outcome.value} net_pnl={net:+.2f} "
                f"source=MT5_HISTORY close_price={closed.close_price} "
                f"reason={closed.close_reason} deals={closed.deal_count}",
            )

    def _fetch_closed(self, ticket: int):
        """Verified MT5 close info; None when unverifiable (never zero)."""
        fetch = getattr(self._adapter, "fetch_closed_position", None)
        if fetch is None:
            return None
        try:
            return fetch(ticket)
        except Exception:  # noqa: BLE001 - unknown stays unknown
            return None

    def _fetch_optional(self, timeframe: Timeframe, count: int):
        """Fetch one extra timeframe; None on failure (honest degradation)."""
        try:
            return self._adapter.fetch_candles(timeframe, count)
        except Exception:  # noqa: BLE001 - any fetch problem degrades, never crashes
            return None

    @staticmethod
    def _rr_of(decision: TradeDecision) -> str:
        """Expected R:R from the decision's stop/target (display only)."""
        if (
            decision.stop_loss is None or decision.entry_price is None
            or not decision.take_profits
        ):
            return "n/a"
        risk = abs(decision.entry_price - decision.stop_loss)
        if risk <= 0:
            return "n/a"
        reward = abs(decision.take_profits[0] - decision.entry_price)
        return f"{reward / risk:.1f}"

    @staticmethod
    def _ticket_of(record: TradeRecord) -> Optional[int]:
        if not record.notes:
            return None
        m = re.search(r"\bticket=(\d+)\b", record.notes)
        return int(m.group(1)) if m else None

    # -- stop protection -----------------------------------------------------------
    def _manage_positions(
        self, positions: List[BrokerPosition], exec_candles
    ) -> None:
        if not positions:
            return
        atr = self._atr(exec_candles)
        initial_stops = {}
        for record in collapse_records(self._journal.records()):
            ticket = self._ticket_of(record)
            if ticket is not None and record.stop_loss is not None:
                initial_stops[ticket] = record.stop_loss
        for proposal in self._protection.propose_all(
            positions, atr=atr, initial_stops=initial_stops
        ):
            if proposal.violation:
                self._violations += 1
                self._event("VIOLATION", proposal.reason)
                continue
            if not proposal.should_update:
                continue
            position = next(p for p in positions if p.ticket == proposal.ticket)
            result = self._gateway.modify_stop(
                ticket=position.ticket,
                symbol=position.symbol,  # exact broker case
                direction=Direction(position.direction),
                current_stop=position.stop_loss,
                new_stop=proposal.proposed_stop,
                take_profit=position.take_profit,
            )
            if result.status is ExecutionStatus.FILLED:
                self._stop_updates += 1
            self._event(
                "STOP_UPDATE",
                f"ticket {position.ticket} {proposal.method} -> "
                f"{proposal.proposed_stop} status={result.status.value} "
                f"({result.reason})",
            )

    # -- entry --------------------------------------------------------------------
    def _try_entry(
        self,
        decision: TradeDecision,
        result: PipelineResult,
        broker: BrokerState,
        spread_price: float,
        positions: List[BrokerPosition],
        reconciliation: ReconciliationReport,
        news,
        risk_state,
        now: datetime,
        exposure: Optional[ExposureDecision] = None,
    ) -> Tuple[str, str]:
        """Run the planner -> gateway entry path; returns (action, detail).

        The session-level cap applies only when max_orders is an integer
        (smoke runs). Real sends and dry-run simulations both count against
        it, so a dry-run rehearses the same cap behavior the live run has.
        """
        if exposure is not None:
            if not exposure.allows_entry:
                self._entries_blocked += 1
                detail = (
                    f"exposure governor {exposure.state}: {exposure.reason} "
                    f"(remaining={exposure.trades_remaining})"
                )
                self._event("ENTRY_BLOCKED", detail)
                return "EXPOSURE_BLOCKED", detail
            if len(positions) >= exposure.max_open:
                self._entries_blocked += 1
                detail = (
                    f"exposure governor {exposure.state}: open positions "
                    f"{len(positions)} >= allowed {exposure.max_open}"
                )
                self._event("ENTRY_BLOCKED", detail)
                return "EXPOSURE_BLOCKED", detail
        if (
            self._max_orders is not None
            and self._orders_sent + self._orders_simulated >= self._max_orders
        ):
            self._entries_blocked += 1
            detail = f"session max_orders={self._max_orders} reached; manage-only"
            self._event("ENTRY_BLOCKED", detail)
            return "CAP_REACHED", detail
        if broker.balance is None or broker.balance <= 0 or broker.leverage is None:
            self._entries_blocked += 1
            detail = "account balance/leverage unknown"
            self._event("ENTRY_BLOCKED", detail)
            return "ENTRY_BLOCKED", detail
        # SMC-EXECUTION-001: no new entry without VERIFIED MT5 accounting
        # (balance, equity, deal history, per-position P&L). Open positions
        # are still managed (the stop path ran earlier this cycle).
        accounting = self._last_accounting or {}
        if not accounting.get("verified", False):
            self._entries_blocked += 1
            detail = (
                "ACCOUNTING_UNVERIFIED_BLOCK_NEW_ENTRIES: MT5 balance/"
                "equity/deal history could not be verified this cycle; "
                "managing existing positions only"
            )
            self._event("ENTRY_BLOCKED", detail)
            return "ENTRY_BLOCKED", detail
        # Loss cooldown: after N consecutive MT5-verified losses, pause new
        # entries; never keep firing into a losing day.
        if risk_state.consecutive_losses >= self._loss_cooldown_losses:
            last_loss = self._last_loss_close()
            if last_loss is not None:
                elapsed = (now - last_loss).total_seconds()
                cooldown = self._loss_cooldown_minutes * 60.0
                if elapsed < cooldown:
                    self._entries_blocked += 1
                    detail = (
                        f"LOSS_COOLDOWN: {risk_state.consecutive_losses} "
                        f"consecutive MT5 losses; new entries paused another "
                        f"{(cooldown - elapsed) / 60:.0f} min (positions "
                        f"still managed)"
                    )
                    self._event("ENTRY_BLOCKED", detail)
                    return "ENTRY_BLOCKED", detail

        account = AccountSnapshot(
            balance=broker.balance,
            free_margin=(
                broker.free_margin if broker.free_margin is not None
                else broker.balance
            ),
            leverage=broker.leverage,
        )
        has_setup = bool(result.context and result.context.has_setup)
        # Adaptive risk budget (INTELLIGENCE-001): the evidence-driven budget
        # tightens the planner's hard cap; it can never loosen it.
        adaptive = getattr(result, "adaptive_risk", None)
        risk_budget = (
            account.balance * adaptive.risk_pct
            if adaptive is not None and adaptive.risk_pct > 0 else None
        )
        # SIZING-001: the phase ceiling authorizes min-lot promotion when the
        # contracted budget sizes below the broker minimum.
        risk_ceiling = (
            account.balance * getattr(adaptive, "ceiling_pct", 0.0)
            if adaptive is not None else None
        )
        plan = self._planner.plan(
            decision,
            result.confidence,
            broker=broker,
            account=account,
            spread_price=spread_price,
            open_positions=positions,
            reconciliation=reconciliation,
            news=news,
            risk_inputs={
                "daily_loss_pct": risk_state.daily_loss_pct,
                "weekly_loss_pct": risk_state.weekly_loss_pct,
                "trades_today": risk_state.trades_today,
                "consecutive_losses": risk_state.consecutive_losses,
                "open_symbols": risk_state.open_symbols,
                # SMC-EXECUTION-001 add-on spacing: never inside the same
                # M5 candle as the previous entry.
                "seconds_since_last_entry": self._seconds_since_last_entry(now),
            },
            fresh_setup=has_setup,
            continuation_supported=has_setup,
            risk_budget=risk_budget,
            risk_ceiling=risk_ceiling,
        )
        if not plan.approved:
            self._entries_blocked += 1
            detail = f"{[c.value for c in plan.failed_checks]}: {plan.reasons[0]}"
            self._event("PLAN_BLOCKED", detail)
            return "PLAN_BLOCKED", detail

        # The planner's lot already encodes tier + governor budget; the
        # gateway re-runs the governor with size_factor_hint=1.0 so the
        # reduction is not applied twice.
        context = RiskContext(
            broker=broker,
            current_spread=spread_price,
            lot_size=plan.lot_size,
            intended_risk_pct=plan.sizing.implied_risk_pct,
            daily_loss_pct=risk_state.daily_loss_pct,
            weekly_loss_pct=risk_state.weekly_loss_pct,
            trades_today=risk_state.trades_today,
            consecutive_losses=risk_state.consecutive_losses,
            open_symbols=risk_state.open_symbols,
            size_factor_hint=1.0,
            protected_addon=bool(
                plan.is_addon and plan.pyramid is not None and plan.pyramid.allowed
            ),
        )
        # BROKER-EXECUTION-001: every send attempt is journaled persistently
        # with the EXACT broker symbol case, so rejections are searchable
        # (kind=event, ORDER_ATTEMPTED/SENT/REJECTED/BLOCKED/ERROR).
        attempt = {
            "decision_id": decision.decision_id,
            "symbol": self._symbol,  # exact broker case (e.g. XAUUSDm)
            "direction": decision.direction.value,
            "volume": plan.lot_size,
            "sl": decision.stop_loss,
            "tp": decision.take_profits[0] if decision.take_profits else None,
            "mode": (
                "DEMO_LIVE" if self._gateway.flags.demo_send_enabled
                else "DRY_RUN"
            ),
        }
        self._journal.log_event("ORDER_ATTEMPTED", attempt)
        try:
            exec_result = self._gateway.execute(decision, context)
        except Exception as exc:  # noqa: BLE001 - journaled, never silent
            self._violations += 1
            detail = f"order execution raised {exc.__class__.__name__}: {exc}"
            self._journal.log_event(
                "ORDER_ERROR", {**attempt, "error": detail, "broker": "order_send"}
            )
            self._event("ORDER_ERROR", detail)
            return "ORDER_ERROR", detail

        if exec_result.status is ExecutionStatus.FILLED and exec_result.sent:
            self._orders_sent += 1
            self._last_sent_ticket = exec_result.order_ticket
            record = TradeRecord(
                record_id=f"T-{decision.decision_id}",
                created_at_utc=now,
                symbol=decision.symbol,
                direction=decision.direction,
                outcome=TradeOutcome.OPEN,
                decision_id=decision.decision_id,
                opened_at_utc=now,
                entry_price=decision.entry_price,
                stop_loss=decision.stop_loss,
                take_profit=(
                    decision.take_profits[0] if decision.take_profits else None
                ),
                lot_size=plan.lot_size,
                risk_amount=plan.sizing.implied_loss,
                risk_pct=plan.sizing.implied_risk_pct,
                confidence=decision.confidence,
                uncertainty=decision.uncertainty,
                thesis=decision.thesis,
                notes=_TICKET_NOTE.format(ticket=exec_result.order_ticket),
            )
            self._journal.log_record(record)
            self._journal.log_event("ORDER_SENT", {
                **attempt,
                "ticket": exec_result.order_ticket,
                "retcode": (exec_result.diagnostics or {}).get("retcode"),
                "broker": "order_send",
            })
            detail = (
                f"ticket={exec_result.order_ticket} lot={plan.lot_size} "
                f"tier={plan.tier.value} addon={plan.is_addon} "
                f"sl={decision.stop_loss} rr={self._rr_of(decision)}"
            )
            self._event("ORDER_SENT", detail)
            return "SENT", detail
        if exec_result.status is ExecutionStatus.DRY_RUN:
            self._orders_simulated += 1
            detail = (
                f"approved plan lot={plan.lot_size} tier={plan.tier.value}; "
                f"sending disabled (dry run)"
            )
            self._event("ORDER_SIMULATED", detail)
            return "SIMULATED", detail
        if exec_result.sent:
            # Broker rejected (or order_send failed): persist the FULL
            # diagnostics so the cause is provable from the journal alone.
            self._orders_rejected += 1
            diagnostics = exec_result.diagnostics or {}
            self._last_order_rejection = diagnostics
            self._journal.log_event("ORDER_REJECTED", {
                **attempt, "broker": "order_send", **diagnostics,
            })
            request = diagnostics.get("request") or {}
            detail = (
                f"{diagnostics.get('retcode_label', exec_result.reason)} "
                f"request_symbol={request.get('symbol')} "
                f"request_volume={request.get('volume')} "
                f"request_price={request.get('price')} "
                f"request_sl={request.get('sl')} request_tp={request.get('tp')}"
            )
            self._event("ORDER_REJECTED", detail)
            return "REJECTED", detail
        self._entries_blocked += 1
        detail = (
            f"gateway blocked: {[c.value for c in exec_result.failed_checks]} "
            f"({exec_result.reason})"
        )
        if any(c.value == "STOPS_LEVEL" for c in exec_result.failed_checks):
            self._journal.log_event("ORDER_BLOCKED", {
                **attempt, "broker": "stops_level", "reason": exec_result.reason,
            })
        self._event("ENTRY_BLOCKED", detail)
        return "ENTRY_BLOCKED", detail

    # -- helpers -----------------------------------------------------------------
    def _as_decision(self, result: PipelineResult, now: datetime) -> TradeDecision:
        if result.decision is not None:
            return result.decision
        return TradeDecision(
            decision_id=f"demo-{now.strftime('%Y%m%dT%H%M%S')}Z",
            time_utc=now,
            symbol=self._symbol,
            direction=Direction.NO_TRADE,
            status=DecisionStatus.NO_TRADE,
            reason=result.reason or "no decision produced",
        )

    @staticmethod
    def _atr(candles, period: int = 14) -> float:
        window = list(candles[-period:])
        if not window:
            return 0.0
        return sum(c.high - c.low for c in window) / len(window)

    def _verdict(self, reconciliation: Optional[ReconciliationReport]) -> str:
        if self._halted:
            return "HALTED_BY_KILL_SWITCH"
        if self._violations > 0:
            return "ATTENTION_REQUIRED"
        if reconciliation is not None and not reconciliation.clean:
            return "ATTENTION_REQUIRED"
        return "CLEAN"

    def _event(self, kind: str, detail: str) -> None:
        self._events.append(SessionEvent(self._now(), kind, detail))
