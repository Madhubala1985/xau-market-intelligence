"""MT5 demo data adapter (Task P1-002).

DATA FETCH ONLY. This adapter connects to an MT5 demo terminal and reads
XAU/USD candle data. It must never place orders: it does not call
`order_send` (or any trade/order function) anywhere.

The real `MetaTrader5` package is Windows-only, so the MT5 client is injected
(or lazily imported). This keeps the adapter testable on any platform and lets
tests assert that no order function is ever invoked.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from src.broker.errors import (
    BrokerConnectionError,
    DataFetchError,
    WrongSymbolError,
)
from src.broker.mt5_settings import MT5Settings
from src.data.enums import Timeframe
from src.data.schemas import Candle

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
        """Validate the requested symbol against the configured XAU/USD symbol."""
        requested = (symbol or self._settings.symbol).strip().upper()
        expected = self._settings.symbol.strip().upper()
        if requested != expected:
            raise WrongSymbolError(
                f"Unexpected symbol {requested!r}; this adapter only serves "
                f"{expected!r}"
            )
        return requested

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
