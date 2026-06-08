"""Shared enumerations for core data schemas.

Values mirror the vocabulary used across the control pack
(02_ARCHITECTURE.md, 06_DATA_POLICY.md, 14_SESSION_KILLZONE_POLICY.md).
"""

from __future__ import annotations

from enum import Enum


class Timeframe(str, Enum):
    """Supported timeframes (06_DATA_POLICY.md)."""

    TICK = "TICK"
    M1 = "1M"
    M5 = "5M"
    M15 = "15M"
    H1 = "1H"
    H4 = "4H"
    D1 = "1D"


class Direction(str, Enum):
    """Trade direction / hypothesis type (10_TASK_QUEUE.md P6-001)."""

    LONG = "LONG"
    SHORT = "SHORT"
    WAIT = "WAIT"
    NO_TRADE = "NO_TRADE"


class DecisionStatus(str, Enum):
    """Lifecycle status of a trade decision.

    The Risk Governor (03_RISK_POLICY.md) has final authority; a decision
    starts as PROPOSED and only the governor may move it to APPROVED.
    """

    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NO_TRADE = "NO_TRADE"


class SessionType(str, Enum):
    """Session / kill-zone classification (02_ARCHITECTURE.md section 3)."""

    ASIAN = "ASIAN"
    LONDON = "LONDON"
    NEW_YORK = "NEW_YORK"
    LONDON_NY_OVERLAP = "LONDON_NY_OVERLAP"
    ROLLOVER = "ROLLOVER"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    CLOSED = "CLOSED"


class BrokerConnectionStatus(str, Enum):
    """Broker feed connection status.

    Defaults to UNKNOWN so that an unverified broker state blocks trading
    (07_TEST_POLICY.md: "broker state unknown = blocked").
    """

    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    UNKNOWN = "UNKNOWN"


class TradeOutcome(str, Enum):
    """Outcome of a journaled trade or no-trade decision (P9-001)."""

    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    OPEN = "OPEN"
    CANCELLED = "CANCELLED"
    NO_TRADE = "NO_TRADE"
