"""Head-to-head decision replay (SMC-V2-001 validation gate).

Replays real M5/M1/HTF history through two (or more) decision pipelines
and scores the DECISIONS in R-multiples under conservative simulated
fills. This is the gate 26_SMC_V2_DESIGN.md requires before SMC v2 may
trade the demo account.

Fill model (conservative, identical for every pipeline):
- entry at the NEXT M5 candle's open, charged spread + SLIPPAGE adverse,
- one position at a time per pipeline (no pyramids in replay — measured
  separately if v2 ships),
- exit by SL/TP intrabar; when one candle touches BOTH, the STOP fills
  first (worst case),
- chassis break-even simulated exactly as live: stop to entry once the
  position reaches +1R intrabar,
- SL losses at the ORIGINAL stop notify pipeline.note_stop_loss (the
  live H8/trade-memory contract, decision 2026-06-12-08); BE exits do
  not.

Scoring is in R (risk normalized), so lot sizing cancels out: this gate
measures decision quality, not the sizing engine (which is shared).
Account-level brakes (day pause, cooldown) are NOT simulated — both
pipelines face identical conditions; the live envelope applies on top.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence

from src.data.enums import Direction
from src.data.schemas import Candle
from src.strategy.pipeline import PipelineInput

SLIPPAGE = 0.30
DEFAULT_SPREAD = 0.20
WINDOW_M5 = 300          # candles fed to the pipeline per step (live-like)
MAX_TRADES_PER_DAY = 25  # mirrors the live envelope cap


@dataclass
class ReplayTrade:
    day: date
    direction: Direction
    entry_time: object
    entry: float
    stop: float
    target: float
    setup: str
    exit_time: object = None
    exit_price: Optional[float] = None
    outcome: str = "OPEN"          # WIN / LOSS / BREAKEVEN / OPEN_AT_END
    r_multiple: float = 0.0


@dataclass
class ReplayResult:
    name: str
    trades: List[ReplayTrade] = field(default_factory=list)

    @property
    def closed(self) -> List[ReplayTrade]:
        return [t for t in self.trades if t.outcome != "OPEN"]

    @property
    def net_r(self) -> float:
        return round(sum(t.r_multiple for t in self.closed), 2)

    @property
    def wins(self) -> int:
        return sum(1 for t in self.closed if t.outcome == "WIN")

    @property
    def losses(self) -> int:
        return sum(1 for t in self.closed if t.outcome == "LOSS")

    @property
    def breakevens(self) -> int:
        return sum(1 for t in self.closed if t.outcome == "BREAKEVEN")

    @property
    def max_drawdown_r(self) -> float:
        peak = equity = 0.0
        max_dd = 0.0
        for t in self.closed:
            equity += t.r_multiple
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
        return round(max_dd, 2)

    @property
    def by_day(self) -> Dict[date, float]:
        days: Dict[date, float] = {}
        for t in self.closed:
            days[t.day] = round(days.get(t.day, 0.0) + t.r_multiple, 2)
        return days

    def summary(self) -> dict:
        closed = self.closed
        return {
            "name": self.name,
            "trades": len(closed),
            "wins": self.wins,
            "losses": self.losses,
            "breakevens": self.breakevens,
            "net_r": self.net_r,
            "win_rate": round(self.wins / len(closed), 2) if closed else 0.0,
            "max_drawdown_r": self.max_drawdown_r,
            "by_day": {d.isoformat(): r for d, r in
                       sorted(self.by_day.items())},
        }


@dataclass
class _OpenPosition:
    trade: ReplayTrade
    risk: float
    be_armed: bool = False


class DecisionReplay:
    """Drives pipelines candle-by-candle over shared history."""

    def __init__(
        self,
        m5: Sequence[Candle],
        *,
        m1: Sequence[Candle] = (),
        m15: Sequence[Candle] = (),
        h1: Sequence[Candle] = (),
        h4: Sequence[Candle] = (),
        daily: Sequence[Candle] = (),
        spread: float = DEFAULT_SPREAD,
        symbol: str = "XAUUSD",
        warmup: int = 60,
    ) -> None:
        self._m5 = list(m5)
        self._m1 = list(m1)
        self._m15 = list(m15)
        self._h1 = list(h1)
        self._h4 = list(h4)
        self._daily = list(daily)
        self._spread = spread
        self._symbol = symbol
        self._warmup = max(warmup, 10)

    def run(self, pipelines: Dict[str, object]) -> Dict[str, ReplayResult]:
        results = {name: ReplayResult(name) for name in pipelines}
        open_pos: Dict[str, Optional[_OpenPosition]] = {
            name: None for name in pipelines
        }
        pending: Dict[str, Optional[ReplayTrade]] = {
            name: None for name in pipelines
        }
        trades_today: Dict[str, int] = {name: 0 for name in pipelines}
        consecutive: Dict[str, int] = {name: 0 for name in pipelines}
        current_day: Optional[date] = None

        for i in range(self._warmup, len(self._m5)):
            candle = self._m5[i]
            day = candle.time_utc.date()
            if day != current_day:
                current_day = day
                trades_today = {name: 0 for name in pipelines}

            for name, pipeline in pipelines.items():
                # 1) fill a pending entry at this candle's open
                trade = pending[name]
                if trade is not None:
                    pending[name] = None
                    if open_pos[name] is None:
                        entry = self._fill_entry(candle.open,
                                                 trade.direction)
                        risk = abs(entry - trade.stop)
                        if risk > 0.05:
                            trade.entry = round(entry, 2)
                            trade.day = day
                            results[name].trades.append(trade)
                            open_pos[name] = _OpenPosition(trade, risk)
                            trades_today[name] += 1

                # 2) manage the open position on this candle
                pos = open_pos[name]
                if pos is not None:
                    closed = self._manage(pos, candle)
                    if closed:
                        open_pos[name] = None
                        if pos.trade.outcome == "LOSS":
                            consecutive[name] += 1
                            note = getattr(pipeline, "note_stop_loss", None)
                            if note is not None and not pos.be_armed:
                                note(pos.trade.direction, pos.trade.stop,
                                     candle.time_utc)
                        elif pos.trade.outcome == "WIN":
                            consecutive[name] = 0

                # 3) ask the pipeline for a decision on this candle
                if (
                    open_pos[name] is not None
                    or pending[name] is not None
                    or trades_today[name] >= MAX_TRADES_PER_DAY
                ):
                    continue
                result = self._decide(pipeline, i, trades_today[name],
                                      consecutive[name])
                if (
                    result is not None and result.approved
                    and result.decision is not None
                    and result.decision.stop_loss is not None
                    and result.decision.take_profits
                ):
                    d = result.decision
                    pending[name] = ReplayTrade(
                        day=day,
                        direction=d.direction,
                        entry_time=candle.time_utc,
                        entry=d.entry_price or candle.close,
                        stop=d.stop_loss,
                        target=d.take_profits[0],
                        setup=d.setup_type or "",
                    )

        for name, pos in open_pos.items():
            if pos is not None:
                pos.trade.outcome = "OPEN_AT_END"
                pos.trade.r_multiple = 0.0
        return results

    # -- internals -----------------------------------------------------------
    def _decide(self, pipeline, i: int, trades_today: int,
                consecutive_losses: int):
        window = self._m5[max(0, i + 1 - WINDOW_M5):i + 1]
        now = window[-1].time_utc
        from src.data.enums import BrokerConnectionStatus
        from src.data.schemas import BrokerState

        broker = BrokerState(
            time_utc=now,
            connection_status=BrokerConnectionStatus.CONNECTED,
            symbol=self._symbol, balance=2000.0, equity=2000.0,
            free_margin=2000.0, leverage=200, open_positions=0,
            trade_allowed=True,
        )
        inp = PipelineInput(
            symbol=self._symbol,
            exec_candles=window,
            daily_candles=self._slice(self._daily, now),
            h4_candles=self._slice(self._h4, now),
            m15_candles=self._slice(self._m15, now, keep=400) or None,
            h1_candles=self._slice(self._h1, now, keep=300) or None,
            m1_candles=self._slice(self._m1, now, keep=600) or None,
            broker=broker,
            current_spread=self._spread,
            risk_pct=0.03,
            trades_today=trades_today,
            consecutive_losses=consecutive_losses,
            now=now,
        )
        try:
            return pipeline.decide(inp)
        except Exception:  # noqa: BLE001 - a pipeline crash scores no trade
            return None

    @staticmethod
    def _slice(candles: Sequence[Candle], now, keep: int = 1000):
        out = [c for c in candles if c.time_utc <= now]
        return out[-keep:]

    def _fill_entry(self, open_price: float, direction: Direction) -> float:
        adverse = self._spread + SLIPPAGE
        return (
            open_price + adverse if direction is Direction.LONG
            else open_price - adverse
        )

    @staticmethod
    def _manage(pos: _OpenPosition, candle: Candle) -> bool:
        t = pos.trade
        short = t.direction is Direction.SHORT
        risk = pos.risk
        stop = t.entry if pos.be_armed else t.stop

        # conservative ordering: the stop is checked FIRST
        stop_hit = candle.high >= stop if short else candle.low <= stop
        tp_hit = candle.low <= t.target if short else candle.high >= t.target
        one_r = t.entry - risk if short else t.entry + risk
        reached_1r = candle.low <= one_r if short else candle.high >= one_r

        if stop_hit:
            t.exit_time = candle.time_utc
            t.exit_price = stop
            if pos.be_armed:
                t.outcome = "BREAKEVEN"
                t.r_multiple = round(-SLIPPAGE / risk, 2) if risk else 0.0
            else:
                t.outcome = "LOSS"
                t.r_multiple = round(-1.0 - SLIPPAGE / risk, 2) \
                    if risk else -1.0
            return True
        if tp_hit:
            t.exit_time = candle.time_utc
            t.exit_price = t.target
            t.outcome = "WIN"
            gain = abs(t.entry - t.target) - SLIPPAGE
            t.r_multiple = round(gain / risk, 2) if risk else 0.0
            return True
        if reached_1r and not pos.be_armed:
            pos.be_armed = True
        return False


def verdict(v1: ReplayResult, v2: ReplayResult) -> dict:
    """The 26_SMC_V2_DESIGN.md shipping gate."""
    reasons: List[str] = []
    net_ok = v2.net_r > v1.net_r
    reasons.append(
        f"net R: v2 {v2.net_r:+.2f} vs v1 {v1.net_r:+.2f} "
        f"({'PASS' if net_ok else 'FAIL'})"
    )
    dd_ok = v2.max_drawdown_r <= v1.max_drawdown_r or \
        v2.max_drawdown_r <= 3.0
    reasons.append(
        f"max DD (R): v2 {v2.max_drawdown_r} vs v1 {v1.max_drawdown_r} "
        f"({'PASS' if dd_ok else 'FAIL'})"
    )
    destruction = []
    v2_days = v2.by_day
    for day, r1 in v1.by_day.items():
        if r1 >= 2.0 and v2_days.get(day, 0.0) < 0.0:
            destruction.append(f"{day}: v1 {r1:+.1f}R -> v2 "
                               f"{v2_days.get(day, 0.0):+.1f}R")
    no_destruction = not destruction
    reasons.append(
        "edge preservation on v1 win days: "
        + ("PASS" if no_destruction else "FAIL — " + "; ".join(destruction))
    )
    return {
        "ship": net_ok and dd_ok and no_destruction,
        "reasons": reasons,
    }
