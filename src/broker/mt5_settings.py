"""MT5 demo connection settings loaded from environment variables.

Security rules (CLAUDE.md):
- Credentials are read from the environment (populated from a local .env that
  is never committed).
- The password is never printed: repr/str of MT5Settings masks it.
- Missing variables are reported by NAME only, never by value.
- This loader enforces a DEMO-only configuration; a non-demo / real-trading
  setup is rejected before any connection is attempted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Optional

from src.broker.errors import (
    InvalidCredentialsError,
    MissingCredentialsError,
    RealTradingForbiddenError,
)

# Required broker credential / connection variables.
REQUIRED_VARS = ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER")

# Default XAU/USD symbol if MT5_SYMBOL is not provided.
DEFAULT_SYMBOL = "XAUUSD"

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _as_bool(value: Optional[str], *, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in _TRUE_VALUES


@dataclass(frozen=True)
class MT5Settings:
    """Validated MT5 demo connection settings.

    The password is stored but excluded from the default repr; a custom
    __repr__ masks both login and password so the object is safe to log.
    """

    login: int = field(repr=False)
    password: str = field(repr=False)
    server: str
    symbol: str = DEFAULT_SYMBOL
    path: Optional[str] = None
    # Optional server-clock offset from UTC, in minutes (default 0 == treat
    # broker epoch as UTC). Used to normalize candle timestamps.
    server_utc_offset_minutes: int = 0

    def __repr__(self) -> str:  # pragma: no cover - exercised via tests
        return (
            "MT5Settings(login=***masked***, password=***masked***, "
            f"server={self.server!r}, symbol={self.symbol!r}, "
            f"path={'set' if self.path else None}, "
            f"server_utc_offset_minutes={self.server_utc_offset_minutes})"
        )

    __str__ = __repr__


def load_dotenv_file(dotenv_path: str = ".env") -> None:
    """Load variables from a local .env into os.environ, if present.

    Uses python-dotenv. Does not print any values. Safe to call when the file
    is absent (no-op).
    """
    from dotenv import load_dotenv

    load_dotenv(dotenv_path, override=False)


def load_mt5_settings(env: Optional[Mapping[str, str]] = None) -> MT5Settings:
    """Build MT5Settings from an environment mapping (defaults to os.environ).

    Raises:
        MissingCredentialsError: a required variable is missing/empty.
        InvalidCredentialsError: MT5_LOGIN is not an integer.
        RealTradingForbiddenError: the configuration is not demo-only.
    """
    source: Mapping[str, str] = os.environ if env is None else env

    # 1. Required variables present and non-empty.
    missing = [name for name in REQUIRED_VARS if not str(source.get(name, "")).strip()]
    if missing:
        raise MissingCredentialsError(missing)

    # 2. Demo-only safety gate (Trading Safety Rule). P1-002 is data-only and
    #    must never run against a real-trading configuration.
    trading_mode = str(source.get("TRADING_MODE", "")).strip().upper()
    account_type = str(source.get("MT5_ACCOUNT_TYPE", "")).strip().upper()
    real_enabled = _as_bool(source.get("REAL_TRADING_ENABLED"), default=False)
    if real_enabled:
        raise RealTradingForbiddenError("REAL_TRADING_ENABLED must be false for P1-002")
    if trading_mode and trading_mode != "DEMO":
        raise RealTradingForbiddenError("TRADING_MODE must be DEMO")
    if account_type and account_type != "DEMO":
        raise RealTradingForbiddenError("MT5_ACCOUNT_TYPE must be DEMO")

    # 3. Parse login as an integer without echoing its value.
    raw_login = str(source.get("MT5_LOGIN", "")).strip()
    try:
        login = int(raw_login)
    except ValueError as exc:
        raise InvalidCredentialsError("MT5_LOGIN must be an integer") from exc

    # 4. Symbol must be a XAU/USD symbol (system trades XAU/USD only).
    symbol = str(source.get("MT5_SYMBOL", "") or DEFAULT_SYMBOL).strip().upper()
    if "XAU" not in symbol:
        raise RealTradingForbiddenError(
            "MT5_SYMBOL must be a XAU/USD symbol (system trades XAU/USD only)"
        )

    # 5. Optional, non-secret settings.
    raw_path = str(source.get("MT5_PATH", "")).strip()
    path = raw_path or None

    raw_offset = str(source.get("MT5_SERVER_UTC_OFFSET_MINUTES", "")).strip()
    try:
        offset = int(raw_offset) if raw_offset else 0
    except ValueError as exc:
        raise InvalidCredentialsError(
            "MT5_SERVER_UTC_OFFSET_MINUTES must be an integer number of minutes"
        ) from exc

    return MT5Settings(
        login=login,
        password=str(source["MT5_PASSWORD"]),
        server=str(source["MT5_SERVER"]).strip(),
        symbol=symbol,
        path=path,
        server_utc_offset_minutes=offset,
    )
