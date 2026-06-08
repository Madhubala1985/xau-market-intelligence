"""Broker layer: MT5 demo connection settings and read-only data adapter."""

from src.broker.errors import (
    BrokerConnectionError,
    BrokerError,
    DataFetchError,
    InvalidCredentialsError,
    MissingCredentialsError,
    RealTradingForbiddenError,
    WrongSymbolError,
)
from src.broker.mt5_data_adapter import MT5DataAdapter
from src.broker.mt5_settings import (
    MT5Settings,
    load_dotenv_file,
    load_mt5_settings,
)

__all__ = [
    # errors
    "BrokerError",
    "BrokerConnectionError",
    "DataFetchError",
    "InvalidCredentialsError",
    "MissingCredentialsError",
    "RealTradingForbiddenError",
    "WrongSymbolError",
    # settings
    "MT5Settings",
    "load_mt5_settings",
    "load_dotenv_file",
    # adapter
    "MT5DataAdapter",
]
