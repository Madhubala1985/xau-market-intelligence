"""MT5 demo data adapter (Task P1-002).

DATA FETCH ONLY. This adapter connects to an MT5 demo terminal and reads
XAU/USD candle data. It must never place orders: it does not call
`order_send` (or any trade/order function) anywhere.

The real `MetaTrader5` package is Windows-only, so the MT5 client is injected
(or lazily imported). This keeps the adapter testable on any platform and lets
tests assert that no order function is ever invoked.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from src.broker.errors import (
    BrokerConnectionError,
    DataFetchError,
    WrongSymbolError,
)
from src.broker.mt5_settings import MT5Settings
from src.data.enums import BrokerConnectionStatus, Timeframe
from src.data.schemas import BrokerState, Candle, Tick

# Map our Timeframe enum to MetaTrader5 timeframe constant names. The constant
# is resolved from the injected client via getattr, so we never depend on the
# MetaTrader5 module being importable at import time.
_TIMEFRAME_ATTR = {
    Timeframe.M1: "TIMEFRAME_M1",
    Timeframe.M5: "TIMEFRAME_M5",
    Timeframe.M15: "TIMEFRAME_M15",
    Timeframe.H1: "TIMEFRAME_H1",
    Timeframe.H4: "TIMEFRAME_H4",
    Timeframe.D1: "TIMEFRAME_D1",
}


def _row_value(row: Any, key: str) -> Any:
    """Read a field from an MT5 rate row.

    Supports both numpy structured-array rows (`row['open']`) and mapping rows.
    """
    return row[key]


def _field(obj: Any, name: str, default: Any = None) -> Any:
    """Read a field from an MT5 named-tuple-like object or a mapping (attr or item)."""
    if obj is None:
        return default
    if hasattr(obj, name):
        return getattr(obj, name)
    try:
        return obj[name]
    except (KeyError, TypeError, IndexError):
        return default


def _pos_float(value: Any) -> Optional[float]:
    """Coerce to a non-negative float, or None if absent/invalid/negative."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out >= 0 else None


def _pos_int(value: Any) -> Optional[int]:
    """Coerce to a positive int, or None if absent/invalid/non-positive."""
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


# MT5 account trade modes (fallbacks when the client lacks the constants).
_TRADE_MODE_DEMO = 0
_TRADE_MODE_CONTEST = 1
_TRADE_MODE_REAL = 2


def verify_demo_account(client: Any) -> str:
    """Verify the logged-in account is non-real. Raises RuntimeError on REAL.

    Returns a short, credential-free label (DEMO / CONTEST). Readiness gate:
    REAL accounts stay refused until the real-money phase is manually
    approved (CLAUDE.md). Shared by every runner that touches the terminal.
    """
    info = client.account_info() if hasattr(client, "account_info") else None
    if info is None:
        raise RuntimeError(
            "account_info() returned no data; cannot verify demo account"
        )
    demo = getattr(client, "ACCOUNT_TRADE_MODE_DEMO", _TRADE_MODE_DEMO)
    contest = getattr(client, "ACCOUNT_TRADE_MODE_CONTEST", _TRADE_MODE_CONTEST)
    real = getattr(client, "ACCOUNT_TRADE_MODE_REAL", _TRADE_MODE_REAL)
    trade_mode = getattr(info, "trade_mode", None)
    if trade_mode == real:
        raise RuntimeError("account trade_mode is REAL — refused (demo only)")
    if trade_mode == demo:
        return "DEMO"
    if trade_mode == contest:
        return "CONTEST"
    raise RuntimeError(
        f"account trade_mode {trade_mode!r} is not a known non-real mode"
    )


@dataclass(frozen=True)
class BrokerPosition:
    """A read-only snapshot of one open MT5 position (no credentials).

    direction is "LONG"/"SHORT" mapped from the MT5 position type
    (POSITION_TYPE_BUY=0 / POSITION_TYPE_SELL=1).
    """

    ticket: int
    symbol: str            # exact broker case as reported by the terminal
    direction: str
    lot_size: float
    entry_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    current_price: Optional[float]
    profit: Optional[float]


class MT5DataAdapter:
    """Read-only MT5 data adapter for XAU/USD candles."""

    def __init__(self, settings: MT5Settings, client: Optional[Any] = None) -> None:
        self._settings = settings
        self._client = client
        self._connected = False

    # -- client resolution -------------------------------------------------
    @property
    def _mt5(self) -> Any:
        if self._client is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except ImportError as exc:  # pragma: no cover - platform dependent
                raise BrokerConnectionError(
                    "MetaTrader5 package is not available; inject a client or "
                    "install it on a supported platform"
                ) from exc
            self._client = mt5
        return self._client

    # -- connection --------------------------------------------------------
    def connect(self) -> bool:
        """Initialize and log in to the MT5 demo terminal (read-only use).

        Credentials are passed to the MT5 client but never logged or printed.
        """
        mt5 = self._mt5

        init_kwargs: dict[str, Any] = {
            "login": self._settings.login,
            "password": self._settings.password,
            "server": self._settings.server,
        }
        if self._settings.path:
            initialized = mt5.initialize(self._settings.path, **init_kwargs)
        else:
            initialized = mt5.initialize(**init_kwargs)

        if not initialized:
            raise BrokerConnectionError(
                f"MT5 initialize failed: {self._safe_last_error()}"
            )

        # Some terminals require an explicit login after initialize.
        if hasattr(mt5, "login"):
            logged_in = mt5.login(
                self._settings.login,
                password=self._settings.password,
                server=self._settings.server,
            )
            if not logged_in:
                raise BrokerConnectionError(
                    f"MT5 login failed: {self._safe_last_error()}"
                )

        self._connected = True
        return True

    def shutdown(self) -> None:
        """Shut down the MT5 connection if supported."""
        mt5 = self._client
        if mt5 is not None and hasattr(mt5, "shutdown"):
            mt5.shutdown()
        self._connected = False

    def _safe_last_error(self) -> str:
        """Return the broker's last_error description without leaking secrets."""
        mt5 = self._client
        if mt5 is not None and hasattr(mt5, "last_error"):
            try:
                return str(mt5.last_error())
            except Exception:  # pragma: no cover - defensive
                return "unknown error"
        return "unknown error"

    # -- symbol handling ---------------------------------------------------
    def _resolve_symbol(self, symbol: Optional[str]) -> str:
        """Validate the requested symbol and return the EXACT broker symbol.

        Comparison is case-insensitive (canonical), so a caller may pass
        "xauusd"/"XAUUSD". The returned value is always the configured broker
        symbol with its case PRESERVED (e.g. Exness "XAUUSDm"), because that is
        what MT5 symbol_select / copy_rates calls require.
        """
        configured = self._settings.symbol.strip()
        if symbol is None:
            return configured
        requested = symbol.strip()
        if requested.upper() != configured.upper():
            raise WrongSymbolError(
                f"Unexpected symbol {requested!r}; this adapter only serves "
                f"{configured!r}"
            )
        return configured

    # -- data fetch --------------------------------------------------------
    def fetch_candles(
        self,
        timeframe: Timeframe,
        count: int = 500,
        symbol: Optional[str] = None,
        start_pos: int = 0,
    ) -> List[Candle]:
        """Fetch recent XAU/USD candles and convert them to Candle schema objects.

        Args:
            timeframe: one of the supported aggregation timeframes.
            count: number of candles to fetch (must be positive).
            symbol: optional symbol; must match the configured XAU/USD symbol.
            start_pos: starting bar position (0 == most recent).

        Raises:
            WrongSymbolError: a non-XAUUSD symbol was requested.
            DataFetchError: no/invalid data returned.
            BrokerConnectionError: adapter is not connected.
        """
        if not self._connected:
            raise BrokerConnectionError("adapter is not connected; call connect() first")
        if count <= 0:
            raise DataFetchError("count must be a positive integer")
        if timeframe not in _TIMEFRAME_ATTR:
            raise DataFetchError(f"unsupported timeframe for candles: {timeframe}")

        resolved_symbol = self._resolve_symbol(symbol)
        mt5 = self._mt5

        # Ensure the symbol is selected/visible in Market Watch.
        if hasattr(mt5, "symbol_select"):
            if not mt5.symbol_select(resolved_symbol, True):
                raise WrongSymbolError(
                    f"symbol {resolved_symbol!r} could not be selected on the terminal"
                )

        mt5_timeframe = getattr(mt5, _TIMEFRAME_ATTR[timeframe])
        rates = mt5.copy_rates_from_pos(resolved_symbol, mt5_timeframe, start_pos, count)

        if rates is None:
            raise DataFetchError(
                f"no candle data returned for {resolved_symbol}: {self._safe_last_error()}"
            )
        if len(rates) == 0:
            raise DataFetchError(f"empty candle data returned for {resolved_symbol}")

        return [self._to_candle(row, timeframe, resolved_symbol) for row in rates]

    def fetch_tick(self, symbol: Optional[str] = None) -> Tick:
        """Read the latest bid/ask tick (read-only). Used to derive live spread.

        Raises:
            WrongSymbolError: a non-XAUUSD symbol was requested / not selectable.
            DataFetchError: no/invalid tick returned.
            BrokerConnectionError: adapter is not connected.
        """
        if not self._connected:
            raise BrokerConnectionError("adapter is not connected; call connect() first")
        resolved_symbol = self._resolve_symbol(symbol)
        mt5 = self._mt5

        if hasattr(mt5, "symbol_select"):
            if not mt5.symbol_select(resolved_symbol, True):
                raise WrongSymbolError(
                    f"symbol {resolved_symbol!r} could not be selected on the terminal"
                )

        raw = mt5.symbol_info_tick(resolved_symbol) if hasattr(mt5, "symbol_info_tick") else None
        if raw is None:
            raise DataFetchError(
                f"no tick returned for {resolved_symbol}: {self._safe_last_error()}"
            )
        bid = _field(raw, "bid")
        ask = _field(raw, "ask")
        if bid is None or ask is None:
            raise DataFetchError(f"tick for {resolved_symbol} is missing bid/ask")

        epoch = _field(raw, "time")
        if epoch is not None:
            broker_time, time_utc = self._epoch_to_times(int(epoch))
        else:  # pragma: no cover - defensive; real ticks carry a time
            time_utc = datetime.now(timezone.utc)
            broker_time = time_utc

        last = _field(raw, "last")
        return Tick(
            symbol=resolved_symbol,
            broker_time=broker_time,
            time_utc=time_utc,
            bid=float(bid),
            ask=float(ask),
            last=float(last) if last not in (None, 0) else None,
            volume=int(_field(raw, "volume", 0) or 0),
        )

    def fetch_broker_state(self, now: datetime) -> BrokerState:
        """Read a read-only account/broker health snapshot (no credentials).

        Reads account_info() and positions_total() if available. Never reads or
        stores login/password/server, and never calls any trade function.
        """
        if not self._connected:
            raise BrokerConnectionError("adapter is not connected; call connect() first")
        mt5 = self._mt5
        info = mt5.account_info() if hasattr(mt5, "account_info") else None
        connected = info is not None

        open_positions = 0
        if hasattr(mt5, "positions_total"):
            try:
                open_positions = int(mt5.positions_total() or 0)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                open_positions = 0

        return BrokerState(
            time_utc=now,
            connection_status=(
                BrokerConnectionStatus.CONNECTED if connected
                else BrokerConnectionStatus.DISCONNECTED
            ),
            symbol=self._settings.symbol,
            account_currency=_field(info, "currency"),
            balance=_pos_float(_field(info, "balance")),
            equity=_pos_float(_field(info, "equity")),
            margin=_pos_float(_field(info, "margin")),
            free_margin=(
                float(_field(info, "margin_free"))
                if _field(info, "margin_free") is not None else None
            ),
            margin_level=_pos_float(_field(info, "margin_level")),
            leverage=_pos_int(_field(info, "leverage")),
            open_positions=max(0, open_positions),
            trade_allowed=bool(_field(info, "trade_allowed", False)) and connected,
        )

    def fetch_positions(self, symbol: Optional[str] = None) -> List[BrokerPosition]:
        """Read open positions for the configured symbol (READ-ONLY).

        Uses positions_get with the exact broker symbol case. Never modifies,
        closes, or opens anything. Returns an empty list when the terminal
        reports none.
        """
        if not self._connected:
            raise BrokerConnectionError("adapter is not connected; call connect() first")
        resolved_symbol = self._resolve_symbol(symbol)
        mt5 = self._mt5
        if not hasattr(mt5, "positions_get"):
            raise DataFetchError("client does not expose positions_get")
        raw = mt5.positions_get(symbol=resolved_symbol)
        if raw is None:
            return []

        sell_type = getattr(mt5, "POSITION_TYPE_SELL", 1)
        out: List[BrokerPosition] = []
        for p in raw:
            direction = "SHORT" if _field(p, "type") == sell_type else "LONG"
            sl = _pos_float(_field(p, "sl"))
            tp = _pos_float(_field(p, "tp"))
            out.append(
                BrokerPosition(
                    ticket=int(_field(p, "ticket", 0) or 0),
                    symbol=str(_field(p, "symbol", resolved_symbol)),
                    direction=direction,
                    lot_size=float(_field(p, "volume", 0.0) or 0.0),
                    entry_price=float(_field(p, "price_open", 0.0) or 0.0),
                    stop_loss=sl if sl else None,        # MT5 reports 0.0 for unset
                    take_profit=tp if tp else None,
                    current_price=_pos_float(_field(p, "price_current")),
                    profit=(
                        float(_field(p, "profit"))
                        if _field(p, "profit") is not None else None
                    ),
                )
            )
        return out

    def fetch_position_profit(
        self, ticket: int, *, lookback_days: int = 7
    ) -> Optional[float]:
        """Realized P&L of a CLOSED position from deal history (READ-ONLY).

        Sums profit + commission + swap over all deals belonging to the
        position ticket (history_deals_get). Returns None when history is
        unavailable or no deals are found — callers must treat None as
        "unknown", never as zero.
        """
        if not self._connected:
            raise BrokerConnectionError("adapter is not connected; call connect() first")
        mt5 = self._mt5
        if not hasattr(mt5, "history_deals_get"):
            return None
        now = datetime.now(timezone.utc)
        deals = mt5.history_deals_get(
            now - timedelta(days=lookback_days), now, position=ticket
        )
        if not deals:
            return None
        total = 0.0
        for d in deals:
            total += float(_field(d, "profit", 0.0) or 0.0)
            total += float(_field(d, "commission", 0.0) or 0.0)
            total += float(_field(d, "swap", 0.0) or 0.0)
        return round(total, 2)

    def _to_candle(self, row: Any, timeframe: Timeframe, symbol: str) -> Candle:
        """Convert a single MT5 rate row into a validated Candle."""
        broker_time, time_utc = self._epoch_to_times(int(_row_value(row, "time")))

        # Optional fields are present on MT5 rate rows but defensively handled.
        try:
            real_volume = int(_row_value(row, "real_volume"))
        except (KeyError, ValueError, TypeError):
            real_volume = None
        try:
            spread = float(_row_value(row, "spread"))
        except (KeyError, ValueError, TypeError):
            spread = None

        return Candle(
            symbol=symbol,
            timeframe=timeframe.value,
            broker_time=broker_time,
            time_utc=time_utc,
            open=float(_row_value(row, "open")),
            high=float(_row_value(row, "high")),
            low=float(_row_value(row, "low")),
            close=float(_row_value(row, "close")),
            tick_volume=int(_row_value(row, "tick_volume")),
            real_volume=real_volume,
            spread=spread,
        )

    def _epoch_to_times(self, epoch_seconds: int) -> tuple[datetime, datetime]:
        """Convert an MT5 server epoch into (broker_time, normalized UTC time).

        MT5 encodes the server wall-clock as a Unix timestamp. We attach the
        configured server offset to obtain the broker timestamp, then normalize
        to UTC. With the default offset of 0 the epoch is treated as UTC.
        """
        offset = self._settings.server_utc_offset_minutes
        server_tz = timezone(timedelta(minutes=offset))
        # Interpret the epoch's wall-clock digits as server-local time.
        wall_clock = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).replace(
            tzinfo=server_tz
        )
        time_utc = wall_clock.astimezone(timezone.utc)
        return wall_clock, time_utc
