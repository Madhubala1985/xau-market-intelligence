"""Demo forward-test runner for research-lab setups (RESEARCH-LAB-001).

Forward-tests the (UNPROVEN) research setups on the DEMO account. It detects
signals on each newly-closed M5 bar, manages each as a pending mitigation entry,
and routes any fill through the existing ExecutionGateway so EVERY safety layer
applies unchanged: real-money refusal, kill switch, execution pre-checks, the
RiskGovernor (final authority), and the broker stops-level gate.

This is NOT a proven edge. There is no backtest behind these setups yet; this
runner exists purely to collect live DEMO behaviour while real history is
exported for proper backtesting. It is demo-locked: construction raises if the
execution flags request anything other than DEMO.

Fill model vs the backtest: the backtest fills a limit exactly; here we fire a
MARKET order through the gateway the moment a closed bar trades into the entry
zone (the gateway prices off the live tick). That is a conservative, slightly
adverse approximation of the limit fill — acceptable for forward observation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence

from research.setups.base import EntryIntent, MarketData, Setup
from src.data.enums import Direction, DecisionStatus, Timeframe
from src.data.schemas import Candle, TradeDecision
from src.execution.gateway import ExecutionGateway, ExecutionResult
from src.risk.governor import RiskContext
from src.risk.position_sizing import PositionSizer


def intent_to_decision(intent: EntryIntent, now: datetime, symbol: str) -> TradeDecision:
    """Convert a setup EntryIntent into a gateway TradeDecision (proposal only)."""
    return TradeDecision(
        decision_id=f"{intent.setup}-{intent.day.date().isoformat()}-{intent.arm_index}",
        time_utc=now,
        symbol=symbol,
        direction=intent.direction,
        status=DecisionStatus.PROPOSED,
        setup_type=intent.setup,
        thesis=f"[forward-test/{intent.version}] {intent.note}",
        invalidation_price=intent.invalidation_price,
        entry_price=intent.entry_price,
        stop_loss=intent.stop,
        take_profits=(intent.target,),
        reason="research-lab demo forward-test (unproven setup)",
    )


@dataclass
class _Pending:
    intent: EntryIntent
    expiry_bars: int
    bars_elapsed: int = 0


@dataclass
class StepEvent:
    """One thing that happened on a step (for monitoring / logging)."""

    kind: str            # SIGNAL_ARMED | INVALIDATED | EXPIRED | FILL_ATTEMPT
    setup: str
    detail: str
    direction: Optional[Direction] = None
    result: Optional[ExecutionResult] = None


class ResearchForwardRunner:
    """Drives research setups against a DEMO broker, one M5 bar at a time."""

    def __init__(
        self,
        *,
        setups: Sequence[Setup],
        adapter,                       # MT5DataAdapter (or any fetch_* provider)
        gateway: ExecutionGateway,
        sizer: Optional[PositionSizer] = None,
        symbol: str = "XAUUSD",
        risk_pct: float = 0.005,
        exec_count: int = 400,
        h1_count: int = 300,
        exec_tf: Timeframe = Timeframe.M5,
        on_event: Optional[Callable[[StepEvent], None]] = None,
    ) -> None:
        # DEMO LOCK: refuse to exist if anything real is requested.
        if gateway.flags.real_requested:
            raise RuntimeError(
                "ResearchForwardRunner is DEMO-ONLY; execution flags request real "
                "trading. Set TRADING_MODE=DEMO and ALLOW_REAL_ORDERS=false."
            )
        self._setups = list(setups)
        self._adapter = adapter
        self._gateway = gateway
        self._sizer = sizer or PositionSizer()
        self._symbol = symbol
        self._risk_pct = risk_pct
        self._exec_count = exec_count
        self._h1_count = h1_count
        self._exec_tf = exec_tf            # bar timeframe driving detection/fills
        self._on_event = on_event

        self._pending: Dict[str, _Pending] = {}
        self._handled: set = set()          # keys already armed/cancelled/fired
        self._last_bar_time: Optional[datetime] = None

    # -- public --------------------------------------------------------------
    def step(self, now: Optional[datetime] = None) -> List[StepEvent]:
        """Process one cycle. Returns events; no-op until a NEW M5 bar closes."""
        now = now or datetime.now(timezone.utc)
        exec_candles = list(self._adapter.fetch_candles(self._exec_tf, self._exec_count))
        if not exec_candles:
            return []
        last = exec_candles[-1]
        if last.time_utc == self._last_bar_time:
            return []                       # same bar; nothing new
        self._last_bar_time = last.time_utc

        by_tf = {self._exec_tf: exec_candles}
        if self._exec_tf != Timeframe.H1:   # M5 setups also need H1 context
            by_tf[Timeframe.H1] = list(self._adapter.fetch_candles(Timeframe.H1, self._h1_count))
        data = MarketData(by_tf=by_tf)

        events: List[StepEvent] = []
        # 1) Manage existing pending (LIMIT) intents against the just-closed bar.
        events.extend(self._process_pending(last, now, exec_candles))
        # 2) Detect new signals armed on THIS bar (fills begin next bar).
        events.extend(self._detect_new(data, last, now, exec_candles))
        # 3) Heartbeat on every newly-closed bar so the loop is visibly alive
        #    even through long quiet stretches (monitoring aid).
        if not events:
            events.append(StepEvent(
                "HEARTBEAT", "-",
                f"scanned {last.time_utc:%Y-%m-%d %H:%M} UTC bar @ {last.close:.2f}; "
                f"{len(self._pending)} pending; no signal",
            ))
        for e in events:
            if self._on_event:
                self._on_event(e)
        return events

    # -- internals -----------------------------------------------------------
    def _detect_new(self, data: MarketData, last: Candle, now: datetime,
                    exec_candles: Sequence[Candle]) -> List[StepEvent]:
        events: List[StepEvent] = []
        for setup in self._setups:
            for intent in setup.scan(data):
                if intent.arm_time != last.time_utc:
                    continue            # only fresh signals (ignore warm-up window)
                key = self._key(intent)
                if key in self._handled or key in self._pending:
                    continue
                self._handled.add(key)
                events.append(StepEvent(
                    "SIGNAL_ARMED", intent.setup,
                    f"{intent.direction.value} entry {intent.entry_price:.2f} "
                    f"SL {intent.stop:.2f} TP {intent.target:.2f}: {intent.note}",
                    direction=intent.direction,
                ))
                if intent.entry_type == "MARKET":
                    # Breakout/momentum: fire immediately (no pullback wait).
                    events.append(self._fire(intent, now, exec_candles))
                else:
                    self._pending[key] = _Pending(
                        intent=intent,
                        expiry_bars=max(1, intent.expiry_index - intent.arm_index),
                    )
        return events

    def _process_pending(self, bar: Candle, now: datetime,
                         m5: Sequence[Candle]) -> List[StepEvent]:
        events: List[StepEvent] = []
        for key, p in list(self._pending.items()):
            it = p.intent
            is_long = it.direction == Direction.LONG
            p.bars_elapsed += 1

            # invalidation FIRST (mirrors the backtest simulator).
            invalidated = (bar.low <= it.invalidation_price if is_long
                           else bar.high >= it.invalidation_price)
            if invalidated:
                del self._pending[key]
                events.append(StepEvent("INVALIDATED", it.setup,
                                        f"price hit invalidation {it.invalidation_price:.2f}"))
                continue

            if p.bars_elapsed > p.expiry_bars:
                del self._pending[key]
                events.append(StepEvent("EXPIRED", it.setup,
                                        "no mitigation within the window"))
                continue

            touched = (bar.low <= it.entry_price if is_long
                       else bar.high >= it.entry_price)
            if touched:
                del self._pending[key]
                events.append(self._fire(it, now, m5))
        return events

    def _fire(self, intent: EntryIntent, now: datetime,
              m5: Sequence[Candle]) -> StepEvent:
        decision = intent_to_decision(intent, now, self._symbol)

        broker = self._adapter.fetch_broker_state(now)
        balance = broker.equity or broker.balance or 0.0
        if balance <= 0:
            return StepEvent("FILL_ATTEMPT", intent.setup,
                             "skipped: account balance is 0/unavailable from broker",
                             direction=intent.direction)
        try:
            tick = self._adapter.fetch_tick()
            spread = max(0.0, tick.ask - tick.bid)
        except Exception:               # noqa: BLE001 - spread is best-effort
            spread = 0.0
        sizing = self._sizer.size(decision, balance, self._risk_pct, spread_price=spread)
        if not sizing.approved or sizing.lot_size <= 0:
            # Surface the EXACT sizing reason (e.g. RISK_TOO_HIGH, STOP_TOO_WIDE).
            return StepEvent(
                "FILL_ATTEMPT", intent.setup,
                f"skipped: sizing {sizing.status.value} — {sizing.reason} "
                f"(balance {balance:.0f}, risk {self._risk_pct:.2%})",
                direction=intent.direction)

        open_syms = frozenset({self._symbol}) if broker.open_positions else frozenset()
        ctx = RiskContext(
            broker=broker, current_spread=spread, lot_size=sizing.lot_size,
            intended_risk_pct=self._risk_pct, open_symbols=open_syms,
        )
        result = self._gateway.execute(decision, ctx)
        return StepEvent("FILL_ATTEMPT", intent.setup,
                         f"gateway: {result.status.value} ({result.reason}) "
                         f"lot {sizing.lot_size:g} @ risk {sizing.risk_pct:.2%}",
                         direction=intent.direction, result=result)

    @staticmethod
    def _key(intent: EntryIntent) -> str:
        return f"{intent.setup}:{intent.arm_time.isoformat()}"
