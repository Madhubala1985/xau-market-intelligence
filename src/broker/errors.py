"""Broker-layer exceptions.

Error messages must never contain secret credential values (CLAUDE.md
Credentials Rule). They may reference environment-variable NAMES only.
"""

from __future__ import annotations


class BrokerError(Exception):
    """Base class for broker-layer errors."""


class MissingCredentialsError(BrokerError):
    """A required MT5 environment variable is missing or empty.

    Carries the missing variable NAMES only — never their values.
    """

    def __init__(self, missing: list[str]) -> None:
        self.missing = list(missing)
        names = ", ".join(self.missing)
        super().__init__(f"Missing required environment variables: {names}")


class InvalidCredentialsError(BrokerError):
    """A credential variable is present but malformed (e.g. non-integer login).

    Must not echo the offending value.
    """


class RealTradingForbiddenError(BrokerError):
    """Configuration does not represent a safe demo-only setup."""


class BrokerConnectionError(BrokerError):
    """MT5 initialize/login failed, or the terminal is unavailable."""


class WrongSymbolError(BrokerError):
    """A non-XAUUSD / unexpected symbol was requested."""


class DataFetchError(BrokerError):
    """Candle data could not be fetched or was empty/malformed."""
