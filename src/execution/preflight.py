"""Demo execution preflight (Task DEMO-001).

Verifies EVERY gate that must hold before demo order sending may be allowed —
WITHOUT placing any order. order_send is never called: the functional gateway
checks use decisions that are blocked before the order path, on a gateway whose
flags keep sending disabled anyway.

Gates (10_TASK_QUEUE.md DEMO-001 + 23_DEMO_TRADING_RUNBOOK.md):
  1. TRADING_MODE=DEMO
  2. REAL_TRADING_ENABLED=false
  3. ALLOW_REAL_ORDERS=false
  4. ALLOW_DEMO_ORDERS=true
  5. ALLOW_MT5_ORDER_SEND=true
  6. account verified demo / non-real (via injected MT5 client)
  7. broker symbol verified on the terminal (exact case, e.g. XAUUSDm)
  8. Risk Governor present and blocks an unsafe (no stop-loss) decision
  9. ExecutionGateway enforces mandatory stop-loss (blocks, sends nothing)
 10. journal writable (probe entry round-trips)
 11. state persistence healthy (probe journal reloads after reopen)
 12. manual kill switch available (engage/release works; gateway honors it)

The report is credential-free. A REAL account fails gate 6 outright.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, List, Mapping, Optional, Tuple, Union

from src.data.enums import (
    BrokerConnectionStatus,
    DecisionStatus,
    Direction,
)
from src.data.schemas import BrokerState, TradeDecision
from src.execution.gateway import (
    ExecutionCheck,
    ExecutionFlags,
    ExecutionGateway,
    load_execution_flags,
)
from src.execution.kill_switch import KillSwitch
from src.journal.journal import TradeJournal
from src.risk.governor import RiskContext, RiskGovernor, RiskLimits

# MT5 ACCOUNT_TRADE_MODE_* fallback values (documented constants).
_TRADE_MODE_DEMO = 0
_TRADE_MODE_CONTEST = 1
_TRADE_MODE_REAL = 2


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"  # cannot be evaluated on this host (no MT5 client)


@dataclass(frozen=True)
class GateResult:
    name: str
    status: GateStatus
    detail: str  # MUST be credential-free


@dataclass
class PreflightReport:
    symbol: str
    gates: List[GateResult] = field(default_factory=list)

    def add(self, name: str, status: GateStatus, detail: str) -> None:
        self.gates.append(GateResult(name, status, detail))

    @property
    def ready(self) -> bool:
        """READY only when every gate is PASS (a SKIPPED gate blocks readiness)."""
        return bool(self.gates) and all(g.status is GateStatus.PASS for g in self.gates)

    def to_dict(self) -> dict:
        return {
            "task": "DEMO-001",
            "symbol": self.symbol,
            "ready": self.ready,
            "gates": [
                {"name": g.name, "status": g.status.value, "detail": g.detail}
                for g in self.gates
            ],
        }


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if hasattr(obj, name):
        return getattr(obj, name)
    try:
        return obj[name]
    except (KeyError, TypeError, IndexError):
        return default


class DemoPreflight:
    """Runs the DEMO-001 gates. Never calls order_send."""

    def __init__(
        self,
        *,
        env: Mapping[str, str],
        broker_symbol: str,
        client: Optional[Any] = None,
        journal_probe_path: Union[str, Path] = "logs/demo_preflight_probe.jsonl",
        kill_switch: Optional[KillSwitch] = None,
    ) -> None:
        self._env = env
        self._symbol = broker_symbol.strip()  # exact broker case (e.g. XAUUSDm)
        self._client = client
        self._journal_probe_path = Path(journal_probe_path)
        self._kill_switch = kill_switch or KillSwitch()

    @property
    def canonical_symbol(self) -> str:
        return self._symbol.upper()

    def run(self) -> PreflightReport:
        report = PreflightReport(symbol=self._symbol)
        self._check_env_flags(report)
        self._check_account_demo(report)
        self._check_symbol(report)
        self._check_risk_governor(report)
        self._check_gateway_stop_loss(report)
        self._check_journal(report)
        self._check_kill_switch(report)
        return report

    # -- gates 1-5: environment flags ---------------------------------------
    def _check_env_flags(self, report: PreflightReport) -> None:
        flags = load_execution_flags(self._env)
        mode = flags.trading_mode.strip().upper()
        report.add(
            "env_trading_mode_demo",
            GateStatus.PASS if mode == "DEMO" else GateStatus.FAIL,
            f"TRADING_MODE={mode}",
        )
        report.add(
            "env_real_trading_disabled",
            GateStatus.FAIL if flags.real_trading_enabled else GateStatus.PASS,
            f"REAL_TRADING_ENABLED={str(flags.real_trading_enabled).lower()}",
        )
        report.add(
            "env_real_orders_disabled",
            GateStatus.FAIL if flags.allow_real_orders else GateStatus.PASS,
            f"ALLOW_REAL_ORDERS={str(flags.allow_real_orders).lower()}",
        )
        report.add(
            "env_demo_orders_enabled",
            GateStatus.PASS if flags.allow_demo_orders else GateStatus.FAIL,
            f"ALLOW_DEMO_ORDERS={str(flags.allow_demo_orders).lower()}",
        )
        report.add(
            "env_mt5_order_send_enabled",
            GateStatus.PASS if flags.allow_mt5_order_send else GateStatus.FAIL,
            f"ALLOW_MT5_ORDER_SEND={str(flags.allow_mt5_order_send).lower()}",
        )

    # -- gate 6: demo account ------------------------------------------------
    def _check_account_demo(self, report: PreflightReport) -> None:
        client = self._client
        if client is None:
            report.add("account_is_demo", GateStatus.SKIPPED,
                       "no MT5 client on this host; run on the Windows MT5 host")
            return
        info = client.account_info() if hasattr(client, "account_info") else None
        if info is None:
            report.add("account_is_demo", GateStatus.FAIL,
                       "account_info() returned no data")
            return
        demo = getattr(client, "ACCOUNT_TRADE_MODE_DEMO", _TRADE_MODE_DEMO)
        contest = getattr(client, "ACCOUNT_TRADE_MODE_CONTEST", _TRADE_MODE_CONTEST)
        real = getattr(client, "ACCOUNT_TRADE_MODE_REAL", _TRADE_MODE_REAL)
        trade_mode = _attr(info, "trade_mode")
        if trade_mode == real:
            report.add("account_is_demo", GateStatus.FAIL,
                       "account trade_mode is REAL — demo trading refused")
        elif trade_mode in (demo, contest):
            label = "DEMO" if trade_mode == demo else "CONTEST"
            report.add("account_is_demo", GateStatus.PASS,
                       f"account trade_mode is {label} (non-real)")
        else:
            report.add("account_is_demo", GateStatus.FAIL,
                       f"account trade_mode {trade_mode!r} is not a known non-real mode")

    # -- gate 7: broker symbol -----------------------------------------------
    def _check_symbol(self, report: PreflightReport) -> None:
        client = self._client
        if client is None:
            report.add("symbol_verified", GateStatus.SKIPPED,
                       "no MT5 client on this host; run on the Windows MT5 host")
            return
        # Exact broker case is passed to the MT5 API (WINMT5-001 case fix).
        if hasattr(client, "symbol_select"):
            client.symbol_select(self._symbol, True)
        info = client.symbol_info(self._symbol) if hasattr(client, "symbol_info") else None
        if info is None:
            report.add("symbol_verified", GateStatus.FAIL,
                       f"symbol {self._symbol} not found on the terminal")
            return
        report.add("symbol_verified", GateStatus.PASS,
                   f"{self._symbol} detected (volume_min="
                   f"{_attr(info, 'volume_min')}, volume_step={_attr(info, 'volume_step')})")

    # -- gates 8-9: governor + gateway stop-loss enforcement ------------------
    def _probe_decision_without_stop(self, now: datetime) -> TradeDecision:
        """An actionable decision deliberately missing its stop-loss."""
        return TradeDecision(
            decision_id="preflight-no-sl-probe",
            time_utc=now,
            symbol=self.canonical_symbol,
            direction=Direction.LONG,
            status=DecisionStatus.PROPOSED,
            thesis="preflight probe (must be blocked)",
            invalidation_price=2300.0,
            entry_price=2310.0,
            stop_loss=None,  # the violation under test
            take_profits=(2330.0,),
        )

    def _probe_context(self, now: datetime) -> RiskContext:
        broker = BrokerState(
            time_utc=now,
            connection_status=BrokerConnectionStatus.CONNECTED,
            symbol=self.canonical_symbol,
            balance=1000.0, equity=1000.0, open_positions=0, trade_allowed=True,
        )
        return RiskContext(
            broker=broker, current_spread=0.2, lot_size=0.01,
            intended_risk_pct=0.004,
        )

    def _check_risk_governor(self, report: PreflightReport) -> None:
        now = datetime.now(timezone.utc)
        governor = RiskGovernor(RiskLimits(expected_symbol=self.canonical_symbol))
        verdict = governor.evaluate(
            self._probe_decision_without_stop(now), self._probe_context(now)
        )
        if verdict.is_blocked:
            report.add("risk_governor_blocks_unsafe", GateStatus.PASS,
                       "governor blocked a no-stop-loss decision")
        else:
            report.add("risk_governor_blocks_unsafe", GateStatus.FAIL,
                       "governor APPROVED a no-stop-loss decision — unsafe")

    def _check_gateway_stop_loss(self, report: PreflightReport) -> None:
        now = datetime.now(timezone.utc)
        # Default flags: sending disabled. The probe is blocked before any
        # order path; no client is attached, so order_send cannot exist here.
        # No kill switch here: this gate must verify the stop-loss check in
        # isolation, even if the user currently has the kill switch engaged.
        gateway = ExecutionGateway(
            RiskGovernor(RiskLimits(expected_symbol=self.canonical_symbol)),
            ExecutionFlags(),
            client=None,
            expected_symbol=self.canonical_symbol,
        )
        result = gateway.execute(
            self._probe_decision_without_stop(now), self._probe_context(now)
        )
        if result.sent:
            report.add("stop_loss_mandatory", GateStatus.FAIL,
                       "gateway SENT a no-stop-loss order — critical violation")
            return
        if ExecutionCheck.NO_STOP_LOSS in result.failed_checks:
            report.add("stop_loss_mandatory", GateStatus.PASS,
                       "gateway blocked a no-stop-loss decision (nothing sent)")
        else:
            report.add("stop_loss_mandatory", GateStatus.FAIL,
                       f"gateway did not flag the missing stop-loss "
                       f"(failed_checks={[c.value for c in result.failed_checks]})")

    # -- gates 10-11: journal / state persistence -----------------------------
    def _check_journal(self, report: PreflightReport) -> None:
        now = datetime.now(timezone.utc)
        probe = TradeDecision(
            decision_id=f"preflight-journal-probe-{now.strftime('%Y%m%dT%H%M%S')}",
            time_utc=now,
            symbol=self.canonical_symbol,
            direction=Direction.NO_TRADE,
            status=DecisionStatus.NO_TRADE,
            reason="DEMO-001 journal probe",
        )
        try:
            journal = TradeJournal(self._journal_probe_path)
            journal.log_decision(probe)
            report.add("journal_writable", GateStatus.PASS,
                       f"probe entry written to {self._journal_probe_path}")
        except OSError as exc:
            report.add("journal_writable", GateStatus.FAIL, f"journal write failed: {exc}")
            report.add("state_persistence", GateStatus.FAIL,
                       "skipped: journal not writable")
            return
        # Restart-safety: a fresh instance on the same path must reload it.
        reloaded = TradeJournal(self._journal_probe_path).decisions()
        if any(d.decision_id == probe.decision_id for d in reloaded):
            report.add("state_persistence", GateStatus.PASS,
                       "probe entry reloaded by a fresh journal instance")
        else:
            report.add("state_persistence", GateStatus.FAIL,
                       "probe entry did not survive a journal reload")

    # -- gate 12: manual kill switch -------------------------------------------
    def _check_kill_switch(self, report: PreflightReport) -> None:
        ks = self._kill_switch
        was_engaged = ks.engaged
        try:
            ks.engage("DEMO-001 preflight probe")
            if not ks.engaged:
                report.add("kill_switch_available", GateStatus.FAIL,
                           "kill switch did not engage")
                return
            # The gateway must honor an engaged kill switch.
            now = datetime.now(timezone.utc)
            gateway = ExecutionGateway(
                RiskGovernor(RiskLimits(expected_symbol=self.canonical_symbol)),
                ExecutionFlags(),
                client=None,
                expected_symbol=self.canonical_symbol,
                kill_switch=ks,
            )
            result = gateway.execute(
                self._probe_decision_without_stop(now), self._probe_context(now)
            )
            honored = (
                not result.sent and ExecutionCheck.KILL_SWITCH in result.failed_checks
            )
        finally:
            if not was_engaged:
                ks.release()
        if not honored:
            report.add("kill_switch_available", GateStatus.FAIL,
                       "gateway did not honor the engaged kill switch")
            return
        if ks.engaged and not was_engaged:
            report.add("kill_switch_available", GateStatus.FAIL,
                       "kill switch did not release")
            return
        report.add(
            "kill_switch_available", GateStatus.PASS,
            f"engage/release verified; gateway blocks while engaged "
            f"(file: {ks.path})",
        )
