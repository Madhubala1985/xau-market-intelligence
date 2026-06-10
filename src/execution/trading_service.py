"""Continuous MT5 trading service (Task CONTINUOUS-001).

ONE long-running service around the existing execution stack:

    MT5 data -> DecisionPipeline -> DemoTradePlanner (sizer + pyramiding)
      -> RiskGovernor -> ExecutionGateway -> the MT5 account configured in .env
      -> journal / state / reports

The service owns the OUTER loop only; every cycle is executed by
SupervisedDemoSession.run_cycle() — the same code path as bounded sessions,
so there is no demo-only or live-only duplicate logic. Which account it
trades is decided by .env (currently an Exness DEMO account, so orders are
demo orders); whether orders are actually SENT is decided by the execution
flags (.env) and the gateway — a dry-run service runs the identical loop with
sending disabled.

Loop behavior:
- starts once and keeps running: no fixed duration, no artificial order cap
  (the risk policy governs trade frequency),
- pauses while the market is closed (schedule + tick staleness), heartbeats,
  and resumes when it opens — it never crashes on a closed market,
- manages stops / break-even / trailing continuously (inside the cycle),
- reconciles MT5 positions against the journal every cycle (fail-closed),
- detects closed trades from MT5 deal history with real P&L,
- writes daily evaluation + reflection reports at UTC day rollover,
- stops cleanly on: kill switch, risk shutdown (weekly loss limit),
  operator Ctrl+C, or a fatal error. Daily loss limit does NOT stop the
  service: the governor blocks entries until the next UTC day while open
  positions remain managed (printed as DAY_PAUSED).

Terminal observability: a startup banner and per-cycle progress lines are
printed through ProgressPrinter so the operator always sees the service is
alive. Nothing printed, journaled, or reported ever contains credentials;
the account login is masked.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, IO, List, Optional

from src.execution.demo_session import CycleOutcome, SupervisedDemoSession
from src.execution.kill_switch import KillSwitch
from src.execution.market_hours import MarketSchedule, MarketState
from src.execution.session_profiles import SessionProfile
from src.journal.journal import TradeJournal
from src.reflection.demo_evaluation import (
    SessionEvaluator,
    build_reflection,
    render_evaluation_markdown,
    render_reflection_markdown,
)
from src.reflection.opportunity_audit import (
    build_opportunity_audit,
    render_opportunity_audit_markdown,
)
from src.risk.state_tracker import collapse_records

SERVICE_NAME = "XAU/USD Adaptive Liquidity Intelligence — Continuous MT5 Service"

_TICK_STALE_SECONDS = 300.0  # frozen feed during nominal hours == not tradeable


class StopReason:
    KILL_SWITCH = "KILL_SWITCH"
    RISK_SHUTDOWN = "RISK_SHUTDOWN"
    OPERATOR_INTERRUPT = "OPERATOR_INTERRUPT"
    MAX_CYCLES = "MAX_CYCLES"
    FATAL_ERROR = "FATAL_ERROR"


def mask_login(login: object) -> str:
    """Mask an account login for display: only the last two digits remain."""
    text = str(login)
    if len(text) <= 2:
        return "*" * len(text)
    return "*" * (len(text) - 2) + text[-2:]


@dataclass(frozen=True)
class BannerInfo:
    """Credential-free startup banner content (built by the runner)."""

    profile: str
    execution_mode: str          # "EXECUTION (orders WILL be sent)" | "DRY_RUN ..."
    account_login_masked: str
    account_type: str            # e.g. "DEMO" (verified non-real)
    server: str
    symbol: str
    risk_summary: str
    news_status: str
    kill_switch_status: str
    journal_path: str
    report_dir: str


@dataclass(frozen=True)
class ServiceReport:
    """Summary of one continuous service run (credential-free)."""

    started_at_utc: datetime
    ended_at_utc: datetime
    cycles: int
    market_closed_checks: int
    decisions: int
    orders_sent: int
    orders_simulated: int
    violations: int
    stop_reason: str
    detail: str

    def to_dict(self) -> dict:
        return {
            "task": "CONTINUOUS-001",
            "service": SERVICE_NAME,
            "started_at_utc": self.started_at_utc.isoformat(),
            "ended_at_utc": self.ended_at_utc.isoformat(),
            "cycles": self.cycles,
            "market_closed_checks": self.market_closed_checks,
            "decisions": self.decisions,
            "orders_sent": self.orders_sent,
            "orders_simulated": self.orders_simulated,
            "violations": self.violations,
            "stop_reason": self.stop_reason,
            "detail": self.detail,
        }


class ProgressPrinter:
    """Live terminal output. Writes only credential-free strings."""

    def __init__(self, stream: Optional[IO[str]] = None, enabled: bool = True):
        import sys
        self._stream = stream if stream is not None else sys.stdout
        self._enabled = enabled

    def _line(self, text: str = "") -> None:
        if self._enabled:
            self._stream.write(text + "\n")
            self._stream.flush()

    # -- startup banner ------------------------------------------------------
    def banner(self, info: BannerInfo) -> None:
        bar = "=" * 78
        self._line(bar)
        self._line(SERVICE_NAME)
        self._line(bar)
        self._line(f"  profile:      {info.profile}")
        self._line(f"  mode:         {info.execution_mode}")
        self._line(f"  account:      login={info.account_login_masked} "
                   f"type={info.account_type}")
        self._line(f"  server:       {info.server}")
        self._line(f"  symbol:       {info.symbol}")
        self._line(f"  risk limits:  {info.risk_summary}")
        self._line(f"  news:         {info.news_status}")
        self._line(f"  kill switch:  {info.kill_switch_status}")
        self._line(f"  journal:      {info.journal_path}")
        self._line(f"  reports:      {info.report_dir}")
        self._line("  stop safely:  create control\\KILL_SWITCH "
                   "(or press Ctrl+C); resume: delete it and restart")
        self._line(bar)
        self._line("Service is ALIVE. Real trading is FORBIDDEN; this service "
                   "trades the account configured in .env.")
        self._line()

    # -- per-cycle progress ----------------------------------------------------
    def cycle(
        self,
        cycle_no: int,
        outcome: CycleOutcome,
        *,
        decision_label: str,
        market_state: str,
        daily_pnl: float,
        risk_label: str,
        news_label: str,
        kill_label: str,
        next_poll_seconds: float,
    ) -> None:
        s = outcome.stat
        conf = f"{s.confidence:.2f}" if s.confidence is not None else "n/a"
        unc = f"{s.uncertainty:.2f}" if s.uncertainty is not None else "n/a"
        self._line(
            f"[cycle {cycle_no}] {s.time_utc.isoformat()} market={market_state} "
            f"bid={outcome.bid:.2f} ask={outcome.ask:.2f} "
            f"spread={s.spread_price:.3f}"
        )
        self._line(
            f"  regime={s.regime or 'n/a'} bias={s.htf_bias or 'n/a'} "
            f"session={s.session or 'n/a'} conf={conf} unc={unc}"
        )
        self._intel_lines(s)
        self._line(f"  decision={decision_label} reason: {s.reason}")
        if s.entry_action not in ("NONE",):
            self._line(f"  entry: {s.entry_action} — {s.entry_detail}")
        if outcome.sent_ticket is not None:
            self._line(
                f"  >> ORDER SENT ticket={outcome.sent_ticket} — it should now "
                f"appear in the MT5 Toolbox/Trade tab"
            )
        for p in outcome.positions:
            pnl = f"{p.profit:+.2f}" if p.profit is not None else "n/a"
            price = f"{p.current_price:.2f}" if p.current_price is not None else "n/a"
            sl = f"{p.stop_loss:.2f}" if p.stop_loss is not None else "NONE"
            self._line(
                f"  pos {p.ticket} {p.direction} {p.lot_size} @{p.entry_price:.2f} "
                f"now={price} sl={sl} pnl={pnl}"
            )
        for e in outcome.events:
            if e.kind in ("STOP_UPDATE", "CLOSE_DETECTED", "VIOLATION",
                          "RECONCILE"):
                self._line(f"  {e.kind}: {e.detail}")
        self._line(
            f"  positions={len(outcome.positions)} "
            f"sent={outcome.orders_sent_total} "
            f"simulated={outcome.orders_simulated_total} "
            f"trades_today={outcome.risk.trades_today} "
            f"daily_pnl={daily_pnl:+.2f} risk={risk_label} news={news_label} "
            f"kill={kill_label} next_poll={next_poll_seconds:.0f}s"
        )
        self._line()

    def _intel_lines(self, s) -> None:
        """Per-cycle reasoning: what the model is actually thinking."""
        intel = getattr(s, "intel", None) or {}
        mtf = intel.get("mtf")
        if mtf:
            tf = lambda k: mtf.get(k) or "-"  # noqa: E731
            self._line(
                f"  MTF d1={tf('d1')} h4={tf('h4')} h1={tf('h1')} "
                f"m15={tf('m15')} m5={tf('m5')} score={mtf.get('score', 0):.2f} "
                f"-> {mtf.get('direction') or 'NO_TRADE'}"
            )
        confluence = intel.get("confluence")
        if confluence:
            st = confluence.get("statuses", {})
            self._line(
                f"  intel sweep={st.get('sweep', '-')} "
                f"bos={st.get('bos_choch', '-')} fvg={st.get('fvg', '-')} "
                f"ob={st.get('order_block', '-')} "
                f"pd={st.get('premium_discount', '-')} "
                f"disp={st.get('displacement', '-')} "
                f"flow={st.get('orderflow', '-')}"
            )
            regime_reason = intel.get("regime_reason", "")
            subtype = s.regime_subtype or "-"
            risk_tier = s.risk_tier or "-"
            risk_pct = (
                f"{s.risk_pct:.2%}" if s.risk_pct is not None else "-"
            )
            self._line(
                f"  confluence={confluence.get('score', 0):.2f} "
                f"risk={risk_tier} {risk_pct} subtype={subtype} "
                f"regime_why: {regime_reason}"
            )
            missing = confluence.get("missing") or []
            if missing and s.entry_action in ("NONE", "PLAN_BLOCKED",
                                              "ENTRY_BLOCKED"):
                self._line(
                    "  needed: stronger " + ", ".join(missing)
                    + " (these scored < 0.5 this cycle)"
                )

    def market_closed(self, now: datetime, state: str, next_open: datetime,
                      check_seconds: float) -> None:
        self._line(
            f"[{now.isoformat()}] MARKET CLOSED ({state}) — waiting; "
            f"next scheduled open {next_open.isoformat()}; "
            f"rechecking in {check_seconds:.0f}s"
        )

    def waiting_feed(self, now: datetime, age_seconds: float,
                     check_seconds: float) -> None:
        self._line(
            f"[{now.isoformat()}] FEED STALE (last tick {age_seconds:.0f}s old) "
            f"— treating as not tradeable; rechecking in {check_seconds:.0f}s"
        )

    def day_paused(self, now: datetime) -> None:
        self._line(
            f"[{now.isoformat()}] DAY_PAUSED — daily loss limit reached; the "
            f"governor blocks new entries until the next UTC day; open "
            f"positions remain managed"
        )

    def opportunity_audit(self, now: datetime, verdict: str, detail: str,
                          filename: str) -> None:
        self._line(
            f"[{now.isoformat()}] OPPORTUNITY AUDIT: {verdict} — {detail} "
            f"(reports/runtime/{filename})"
        )

    def stopped(self, reason: str, detail: str) -> None:
        self._line(f"SERVICE STOPPED: {reason} — {detail}")


class TradingService:
    """Continuous outer loop around SupervisedDemoSession.run_cycle()."""

    def __init__(
        self,
        *,
        session: SupervisedDemoSession,
        journal: TradeJournal,
        kill_switch: KillSwitch,
        profile: SessionProfile,
        printer: ProgressPrinter,
        banner: BannerInfo,
        report_dir: Path,
        heartbeat_path: Optional[Path] = None,
        schedule: Optional[MarketSchedule] = None,
        tick_age: Optional[Callable[[datetime], Optional[float]]] = None,
        closed_poll_seconds: float = 60.0,
        max_cycles: Optional[int] = None,
        opportunity_audit_cycles: int = 60,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._session = session
        self._journal = journal
        self._kill_switch = kill_switch
        self._profile = profile
        self._printer = printer
        self._banner = banner
        self._report_dir = Path(report_dir)
        self._heartbeat_path = heartbeat_path
        self._schedule = schedule or MarketSchedule()
        # Optional feed-staleness probe: seconds since the last tick, or None
        # when unavailable. Runner wires this to the read-only adapter.
        self._tick_age = tick_age
        self._closed_poll = closed_poll_seconds
        self._max_cycles = max_cycles
        self._now = now
        self._sleep = sleep
        self._evaluator = SessionEvaluator()
        # per-day accumulation for the daily reports
        self._day_stats: List[dict] = []
        self._day_events: List[dict] = []
        self._current_day = None
        self._closed_checks = 0
        # Long no-trade opportunity audit (INTELLIGENCE-001): after this many
        # consecutive ACTIVE-session cycles without an entry, audit whether
        # no-trade was correct and write a classified report.
        self._audit_cycles = opportunity_audit_cycles
        self._no_trade_streak = 0
        self._audits_written = 0

    # -- main loop ---------------------------------------------------------------
    def run(self) -> ServiceReport:
        started = self._now()
        self._current_day = started.date()
        self._printer.banner(self._banner)
        cycles = 0
        stop_reason = StopReason.MAX_CYCLES
        detail = ""
        try:
            while True:
                now = self._now()

                if self._kill_switch.engaged:
                    stop_reason = StopReason.KILL_SWITCH
                    detail = "manual kill switch engaged; stopped cleanly"
                    break

                self._maybe_rollover(now)

                # Market state: schedule first, then feed staleness.
                state = self._schedule.state(now)
                if state != MarketState.OPEN:
                    self._wait_market_closed(now, state)
                    continue
                age = self._tick_age(now) if self._tick_age else None
                if age is not None and age > _TICK_STALE_SECONDS:
                    self._wait_feed_stale(now, age)
                    continue

                outcome = self._session.run_cycle()
                cycles += 1
                self._accumulate(outcome)
                self._print_cycle(cycles, outcome, now)
                self._track_opportunity(outcome, now)

                # Risk shutdown: the WEEKLY loss limit stops the service
                # (03_RISK_POLICY shutdown rule). The DAILY limit pauses
                # entries via the governor until UTC rollover.
                if outcome.risk.weekly_loss_pct >= self._profile.max_weekly_loss:
                    stop_reason = StopReason.RISK_SHUTDOWN
                    detail = (
                        f"weekly loss {outcome.risk.weekly_loss_pct:.4f} >= "
                        f"limit {self._profile.max_weekly_loss}; stopped cleanly"
                    )
                    break
                if outcome.risk.daily_loss_pct >= self._profile.max_daily_loss:
                    self._printer.day_paused(now)

                if self._max_cycles is not None and cycles >= self._max_cycles:
                    stop_reason = StopReason.MAX_CYCLES
                    detail = f"max_cycles={self._max_cycles} reached"
                    break
                self._sleep(self._profile.poll_seconds)
        except KeyboardInterrupt:
            stop_reason = StopReason.OPERATOR_INTERRUPT
            detail = "operator interrupt (Ctrl+C); stopped cleanly"
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed silently
            stop_reason = StopReason.FATAL_ERROR
            detail = f"{exc.__class__.__name__}: {exc}"

        ended = self._now()
        self._write_day_reports(self._current_day)
        report = ServiceReport(
            started_at_utc=started,
            ended_at_utc=ended,
            cycles=cycles,
            market_closed_checks=self._closed_checks,
            decisions=self._session.decisions_logged,
            orders_sent=self._session.orders_sent,
            orders_simulated=self._session.orders_simulated,
            violations=self._session.violations,
            stop_reason=stop_reason,
            detail=detail,
        )
        self._write_service_report(report)
        self._printer.stopped(stop_reason, detail)
        return report

    # -- closed/waiting states ------------------------------------------------
    def _wait_market_closed(self, now: datetime, state: str) -> None:
        self._closed_checks += 1
        next_open = self._schedule.next_open(now)
        self._printer.market_closed(now, state, next_open, self._closed_poll)
        self._heartbeat({"time_utc": now.isoformat(), "state": state,
                         "next_open_utc": next_open.isoformat()})
        self._sleep(self._closed_poll)

    def _wait_feed_stale(self, now: datetime, age: float) -> None:
        self._closed_checks += 1
        self._printer.waiting_feed(now, age, self._closed_poll)
        self._heartbeat({"time_utc": now.isoformat(), "state": "FEED_STALE",
                         "tick_age_seconds": round(age, 1)})
        self._sleep(self._closed_poll)

    def _heartbeat(self, payload: dict) -> None:
        if self._heartbeat_path is None:
            return
        self._heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        with self._heartbeat_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")

    # -- per-cycle bookkeeping ---------------------------------------------------
    def _accumulate(self, outcome: CycleOutcome) -> None:
        self._day_stats.append(outcome.stat.to_dict())
        self._day_events.extend(e.to_dict() for e in outcome.events)

    def _print_cycle(self, cycle_no: int, outcome: CycleOutcome,
                     now: datetime) -> None:
        s = outcome.stat
        if s.entry_action == "SENT":
            decision = "TRADE"
        elif s.entry_action == "SIMULATED":
            decision = "TRADE_SIMULATED"
        elif s.entry_action in ("PLAN_BLOCKED", "ENTRY_BLOCKED",
                                "CAP_REACHED", "REJECTED"):
            decision = "BLOCKED"
        elif outcome.positions:
            decision = "MANAGE_POSITION"
        else:
            decision = "NO_TRADE"

        risk = outcome.risk
        if risk.weekly_loss_pct >= self._profile.max_weekly_loss:
            risk_label = "WEEKLY_LIMIT"
        elif risk.daily_loss_pct >= self._profile.max_daily_loss:
            risk_label = "DAY_PAUSED"
        else:
            risk_label = (
                f"OK(d={risk.daily_loss_pct:.3f},w={risk.weekly_loss_pct:.3f})"
            )
        if not s.news_known:
            news_label = "UNKNOWN(blocks)"
        elif s.news_risky:
            news_label = "BLOCKED"
        else:
            news_label = "CLEAR"
        self._printer.cycle(
            cycle_no, outcome,
            decision_label=decision,
            market_state="OPEN",
            daily_pnl=self._daily_pnl(now),
            risk_label=risk_label,
            news_label=news_label,
            kill_label="on" if self._kill_switch.engaged else "off",
            next_poll_seconds=self._profile.poll_seconds,
        )

    def _daily_pnl(self, now: datetime) -> float:
        day_start = now.astimezone(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        total = 0.0
        for r in collapse_records(self._journal.records()):
            if r.closed_at_utc is not None and r.pnl is not None \
                    and day_start <= r.closed_at_utc <= now:
                total += r.pnl
        return total

    # -- opportunity audit (INTELLIGENCE-001) -----------------------------------
    def _track_opportunity(self, outcome: CycleOutcome, now: datetime) -> None:
        s = outcome.stat
        if s.entry_action in ("SENT", "SIMULATED"):
            self._no_trade_streak = 0
            return
        if (s.session or "") not in ("LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"):
            return  # quiet sessions do not accuse the gates of passivity
        self._no_trade_streak += 1
        if self._no_trade_streak < self._audit_cycles:
            return
        window = self._day_stats[-self._audit_cycles:]
        audit = build_opportunity_audit(window)
        stamp = now.strftime("%Y%m%dT%H%M")
        self._report_dir.mkdir(parents=True, exist_ok=True)
        (self._report_dir / f"opportunity_audit_{stamp}.md").write_text(
            render_opportunity_audit_markdown(audit), encoding="utf-8"
        )
        (self._report_dir / f"opportunity_audit_{stamp}.json").write_text(
            json.dumps(audit.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
        self._audits_written += 1
        self._printer.opportunity_audit(now, audit.verdict, audit.detail,
                                        f"opportunity_audit_{stamp}.md")
        self._no_trade_streak = 0  # re-arm for the next stretch

    # -- daily rollover + reports ---------------------------------------------
    def _maybe_rollover(self, now: datetime) -> None:
        today = now.date()
        if self._current_day is not None and today != self._current_day:
            self._write_day_reports(self._current_day)
            self._day_stats = []
            self._day_events = []
            self._current_day = today

    def _day_payload(self, day) -> dict:
        stats = self._day_stats
        return {
            "report": {
                "symbol": self._banner.symbol,
                "mode": (
                    "DEMO_LIVE"
                    if "EXECUTION" in self._banner.execution_mode else "DRY_RUN"
                ),
                "profile": self._profile.name,
                "verdict": "",
                "started_at_utc": f"{day.isoformat()}T00:00:00+00:00",
                "ended_at_utc": f"{day.isoformat()}T23:59:59+00:00",
                "cycles": len(stats),
                "decisions_logged": len(stats),
                "orders_sent": sum(
                    1 for s in stats if s.get("entry_action") == "SENT"
                ),
                "orders_simulated": sum(
                    1 for s in stats if s.get("entry_action") == "SIMULATED"
                ),
                "orders_rejected": sum(
                    1 for s in stats if s.get("entry_action") == "REJECTED"
                ),
                "entries_blocked": sum(
                    1 for s in stats
                    if s.get("entry_action") in ("PLAN_BLOCKED", "ENTRY_BLOCKED",
                                                 "CAP_REACHED")
                ),
                "stop_updates": sum(
                    1 for e in self._day_events if e.get("kind") == "STOP_UPDATE"
                ),
                "violations": sum(
                    1 for e in self._day_events if e.get("kind") == "VIOLATION"
                ),
                "cycle_stats": stats,
            }
        }

    def _write_day_reports(self, day) -> None:
        if day is None or not self._day_stats:
            return
        stamp = day.strftime("%Y%m%d")
        payload = self._day_payload(day)
        evaluation = self._evaluator.evaluate(
            payload, self._journal.records(), self._journal.decisions()
        )
        reflection = build_reflection(evaluation)
        self._report_dir.mkdir(parents=True, exist_ok=True)
        (self._report_dir / f"service_eval_{stamp}.md").write_text(
            render_evaluation_markdown(evaluation), encoding="utf-8"
        )
        (self._report_dir / f"service_eval_{stamp}.json").write_text(
            json.dumps(evaluation.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
        (self._report_dir / f"service_reflection_{stamp}.md").write_text(
            render_reflection_markdown(reflection), encoding="utf-8"
        )
        (self._report_dir / f"service_reflection_{stamp}.json").write_text(
            json.dumps(reflection.to_dict(), indent=2) + "\n", encoding="utf-8"
        )

    def _write_service_report(self, report: ServiceReport) -> None:
        self._report_dir.mkdir(parents=True, exist_ok=True)
        payload = report.to_dict()
        (self._report_dir / "trading_service.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        lines = ["# Continuous Trading Service (CONTINUOUS-001)", ""]
        lines += [f"- {k}: {v}" for k, v in payload.items() if k != "task"]
        (self._report_dir / "trading_service.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
