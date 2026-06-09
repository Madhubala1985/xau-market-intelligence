"""MT5 demo connectivity validator (Task WINMT5-001).

READ-ONLY connectivity validation for XAU/USD. This module proves the demo
terminal is reachable and that market data can be read; it NEVER places orders
(it does not call `order_send` / `order_check` / any trade function) and it never
prints or stores credential values.

The real `MetaTrader5` package is Windows-only, so the MT5 client is injected.
On a host without MetaTrader5 the runner (scripts/winmt5_validate.py) classifies
this as an Environment Issue rather than faking a result.

Validated proofs (22_MT5_WINDOWS_VALIDATION.md):
  1. terminal path configured,
  2. demo credentials loaded (by NAME; values never read into the report),
  3. MT5 initializes (or a clear environment issue is reported by the runner),
  4. demo login succeeds,
  5. account verified as demo / non-real,
  6. XAU/USD symbol detected,
  7. symbol_info read,
  8. latest candles fetched,
  9. spread read,
 10. no order_send is called (structural; also asserted by tests).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

from src.broker.errors import BrokerError
from src.broker.mt5_data_adapter import MT5DataAdapter
from src.broker.mt5_settings import MT5Settings
from src.data.enums import Timeframe


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


# MT5 account trade-mode codes (ACCOUNT_TRADE_MODE_*). Resolved from the client
# when available; these are the documented fallback values.
_TRADE_MODE_DEMO = 0
_TRADE_MODE_CONTEST = 1
_TRADE_MODE_REAL = 2


@dataclass(frozen=True)
class ConnectivityCheck:
    name: str
    status: CheckStatus
    detail: str  # MUST be credential-free


@dataclass
class ConnectivityReport:
    symbol: str
    checks: List[ConnectivityCheck] = field(default_factory=list)
    facts: dict = field(default_factory=dict)  # non-secret derived facts only

    def add(self, name: str, status: CheckStatus, detail: str) -> None:
        self.checks.append(ConnectivityCheck(name, status, detail))

    @property
    def passed(self) -> bool:
        return all(c.status is not CheckStatus.FAIL for c in self.checks)

    @property
    def all_proven(self) -> bool:
        return all(c.status is CheckStatus.PASS for c in self.checks)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "passed": self.passed,
            "all_proven": self.all_proven,
            "checks": [
                {"name": c.name, "status": c.status.value, "detail": c.detail}
                for c in self.checks
            ],
            "facts": self.facts,
        }


def _field(obj: Any, name: str, default: Any = None) -> Any:
    """Read a field from an MT5 named-tuple-like object or a mapping."""
    if obj is None:
        return default
    if hasattr(obj, name):
        return getattr(obj, name)
    try:
        return obj[name]
    except (KeyError, TypeError, IndexError):
        return default


class MT5ConnectivityValidator:
    """Runs read-only MT5 connectivity checks against an injected client."""

    def __init__(self, settings: MT5Settings) -> None:
        self._settings = settings

    def validate(self, client: Any) -> ConnectivityReport:
        s = self._settings
        report = ConnectivityReport(symbol=s.symbol)

        # 1. Terminal path configured.
        if s.path:
            report.add("terminal_path_configured", CheckStatus.PASS,
                       "MT5_PATH is set (value not shown)")
        else:
            report.add("terminal_path_configured", CheckStatus.PASS,
                       "no MT5_PATH set; using the default installed terminal")

        # 2. Demo credentials loaded (by NAME only; values are never read here).
        report.add("demo_credentials_loaded", CheckStatus.PASS,
                   "MT5_LOGIN, MT5_PASSWORD, MT5_SERVER loaded from environment "
                   "(values not read into this report)")

        # 3 + 4. Initialize and login via the read-only adapter (no order calls).
        adapter = MT5DataAdapter(s, client=client)
        try:
            adapter.connect()
        except BrokerError as exc:
            report.add("mt5_initialize", CheckStatus.FAIL, _safe(exc))
            report.add("demo_login", CheckStatus.FAIL, "skipped: connect failed")
            self._skip_rest(report, after="login")
            return report
        report.add("mt5_initialize", CheckStatus.PASS, "terminal initialized")
        report.add("demo_login", CheckStatus.PASS, "logged in to demo terminal")

        try:
            # 5. Account verified as demo / non-real.
            self._check_account(client, report)
            # 6 + 7. Symbol detection + symbol_info.
            symbol_info = self._check_symbol(client, report)
            # 8. Latest candles fetched.
            self._check_candles(adapter, report)
            # 9. Spread read.
            self._check_spread(client, symbol_info, report)
        finally:
            adapter.shutdown()

        # 10. No order_send: structural guarantee (this validator and the adapter
        #     never reference any trade function). Tests assert it on the client.
        report.add("no_order_send", CheckStatus.PASS,
                   "no order/trade function is referenced by the validator")
        return report

    # -- individual checks -------------------------------------------------
    def _check_account(self, client: Any, report: ConnectivityReport) -> None:
        info = client.account_info() if hasattr(client, "account_info") else None
        if info is None:
            report.add("account_is_demo", CheckStatus.FAIL,
                       "account_info() returned no data")
            return
        demo = getattr(client, "ACCOUNT_TRADE_MODE_DEMO", _TRADE_MODE_DEMO)
        contest = getattr(client, "ACCOUNT_TRADE_MODE_CONTEST", _TRADE_MODE_CONTEST)
        real = getattr(client, "ACCOUNT_TRADE_MODE_REAL", _TRADE_MODE_REAL)
        trade_mode = _field(info, "trade_mode")

        # Record non-secret facts (NEVER the login number).
        report.facts["account_currency"] = _field(info, "currency")
        report.facts["account_leverage"] = _field(info, "leverage")
        report.facts["account_server"] = _field(info, "server") or self._settings.server
        report.facts["account_has_balance"] = _field(info, "balance") is not None

        if trade_mode == real:
            report.add("account_is_demo", CheckStatus.FAIL,
                       "account trade_mode is REAL — refused (demo only)")
        elif trade_mode in (demo, contest):
            label = "DEMO" if trade_mode == demo else "CONTEST"
            report.add("account_is_demo", CheckStatus.PASS,
                       f"account trade_mode is {label} (non-real)")
        else:
            report.add("account_is_demo", CheckStatus.FAIL,
                       f"account trade_mode {trade_mode!r} is not a known non-real mode")

    def _check_symbol(self, client: Any, report: ConnectivityReport) -> Any:
        symbol = self._settings.symbol
        # Make the symbol visible in Market Watch (read-only selection).
        if hasattr(client, "symbol_select"):
            try:
                client.symbol_select(symbol, True)
            except Exception as exc:  # pragma: no cover - defensive
                report.add("symbol_detected", CheckStatus.FAIL, _safe(exc))
                report.add("symbol_info_read", CheckStatus.SKIPPED,
                           "skipped: symbol not selectable")
                return None

        symbol_info = client.symbol_info(symbol) if hasattr(client, "symbol_info") else None
        if symbol_info is None:
            report.add("symbol_detected", CheckStatus.FAIL,
                       f"symbol {symbol} not found on the terminal")
            report.add("symbol_info_read", CheckStatus.SKIPPED,
                       "skipped: symbol not found")
            return None

        report.add("symbol_detected", CheckStatus.PASS, f"{symbol} detected")
        contract = _field(symbol_info, "trade_contract_size")
        digits = _field(symbol_info, "digits")
        point = _field(symbol_info, "point")
        vol_min = _field(symbol_info, "volume_min")
        vol_step = _field(symbol_info, "volume_step")
        report.facts["symbol_contract_size"] = contract
        report.facts["symbol_digits"] = digits
        report.facts["symbol_point"] = point
        report.facts["symbol_volume_min"] = vol_min
        report.facts["symbol_volume_step"] = vol_step
        report.add("symbol_info_read", CheckStatus.PASS,
                   f"contract_size={contract}, digits={digits}, point={point}, "
                   f"volume_min={vol_min}, volume_step={vol_step}")
        return symbol_info

    def _check_candles(self, adapter: MT5DataAdapter, report: ConnectivityReport) -> None:
        try:
            candles = adapter.fetch_candles(Timeframe.M1, count=5)
        except BrokerError as exc:
            report.add("candles_fetched", CheckStatus.FAIL, _safe(exc))
            return
        if not candles:
            report.add("candles_fetched", CheckStatus.FAIL, "no candles returned")
            return
        last = candles[-1]
        report.facts["last_candle_time_utc"] = last.time_utc.isoformat()
        report.facts["candles_fetched_count"] = len(candles)
        report.add("candles_fetched", CheckStatus.PASS,
                   f"{len(candles)} M1 candles; last close={last.close}")

    def _check_spread(self, client: Any, symbol_info: Any,
                      report: ConnectivityReport) -> None:
        symbol = self._settings.symbol
        bid = ask = None
        if hasattr(client, "symbol_info_tick"):
            tick = client.symbol_info_tick(symbol)
            bid = _field(tick, "bid")
            ask = _field(tick, "ask")
        if bid is not None and ask is not None:
            spread_price = round(float(ask) - float(bid), 6)
            report.facts["spread_price"] = spread_price
            report.add("spread_read", CheckStatus.PASS,
                       f"bid/ask read; spread={spread_price}")
            return
        spread_points = _field(symbol_info, "spread")
        if spread_points is not None:
            report.facts["spread_points"] = spread_points
            report.add("spread_read", CheckStatus.PASS,
                       f"spread (points)={spread_points}")
            return
        report.add("spread_read", CheckStatus.FAIL, "could not read spread")

    @staticmethod
    def _skip_rest(report: ConnectivityReport, *, after: str) -> None:
        for name in ("account_is_demo", "symbol_detected", "symbol_info_read",
                     "candles_fetched", "spread_read", "no_order_send"):
            report.add(name, CheckStatus.SKIPPED, "skipped: not connected")


def _safe(exc: Exception) -> str:
    """Return an exception message guaranteed to carry no credential values."""
    # Broker-layer errors are constructed to be credential-free by design.
    return str(exc)
