"""Core data schemas for the XAU/USD Adaptive Liquidity Intelligence System.

Task P1-001. These are pure data definitions: immutable, strictly validated
value objects. They contain NO broker credentials and perform NO trading.

Design rules (from the control pack):
- 06_DATA_POLICY.md: preserve both the broker timestamp and a normalized
  UTC timestamp; reject impossible OHLC values and inconsistent bid/ask.
- All models are frozen (immutable) and forbid unknown fields, so malformed
  payloads are rejected rather than silently accepted.
- No model carries login/password/server/token fields. Credentials never
  enter the data layer (CLAUDE.md Credentials Rule).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.data.enums import (
    BrokerConnectionStatus,
    DecisionStatus,
    Direction,
    SessionType,
    TradeOutcome,
)
from src.utils.time import ensure_aware, to_utc


class _BaseSchema(BaseModel):
    """Base for all core schemas: immutable and strict."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def _clean_symbol(value: str) -> str:
    """Normalize and validate a trading symbol (non-empty, upper-cased)."""
    if not isinstance(value, str):
        raise TypeError("symbol must be a string")
    cleaned = value.strip().upper()
    if not cleaned:
        raise ValueError("symbol must be a non-empty string")
    return cleaned


class Candle(_BaseSchema):
    """A single OHLCV bar for one symbol and timeframe."""

    symbol: str
    timeframe: str
    broker_time: datetime
    time_utc: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    tick_volume: int = Field(ge=0)
    real_volume: Optional[int] = Field(default=None, ge=0)
    spread: Optional[float] = Field(default=None, ge=0)

    @field_validator("symbol")
    @classmethod
    def _norm_symbol(cls, v: str) -> str:
        return _clean_symbol(v)

    @field_validator("broker_time")
    @classmethod
    def _broker_aware(cls, v: datetime) -> datetime:
        return ensure_aware(v, "broker_time")

    @field_validator("time_utc")
    @classmethod
    def _to_utc(cls, v: datetime) -> datetime:
        return to_utc(v, "time_utc")

    @model_validator(mode="after")
    def _check_ohlc(self) -> "Candle":
        # Impossible OHLC values must be rejected (06_DATA_POLICY.md).
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if self.high < max(self.open, self.close):
            raise ValueError("high must be >= open and close")
        if self.low > min(self.open, self.close):
            raise ValueError("low must be <= open and close")
        return self


class Tick(_BaseSchema):
    """A single bid/ask tick."""

    symbol: str
    broker_time: datetime
    time_utc: datetime
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    last: Optional[float] = Field(default=None, gt=0)
    volume: int = Field(default=0, ge=0)

    @field_validator("symbol")
    @classmethod
    def _norm_symbol(cls, v: str) -> str:
        return _clean_symbol(v)

    @field_validator("broker_time")
    @classmethod
    def _broker_aware(cls, v: datetime) -> datetime:
        return ensure_aware(v, "broker_time")

    @field_validator("time_utc")
    @classmethod
    def _to_utc(cls, v: datetime) -> datetime:
        return to_utc(v, "time_utc")

    @model_validator(mode="after")
    def _check_quote(self) -> "Tick":
        # Inconsistent bid/ask must be rejected (06_DATA_POLICY.md).
        if self.ask < self.bid:
            raise ValueError("ask must be >= bid")
        return self

    @property
    def spread(self) -> float:
        """Quoted spread in price terms."""
        return self.ask - self.bid


class SpreadSnapshot(_BaseSchema):
    """A point-in-time spread observation derived from bid/ask."""

    symbol: str
    time_utc: datetime
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    spread_points: Optional[float] = Field(default=None, ge=0)

    @field_validator("symbol")
    @classmethod
    def _norm_symbol(cls, v: str) -> str:
        return _clean_symbol(v)

    @field_validator("time_utc")
    @classmethod
    def _to_utc(cls, v: datetime) -> datetime:
        return to_utc(v, "time_utc")

    @model_validator(mode="after")
    def _check_quote(self) -> "SpreadSnapshot":
        if self.ask < self.bid:
            raise ValueError("ask must be >= bid")
        return self

    @property
    def spread_price(self) -> float:
        """Spread in price terms (ask - bid)."""
        return self.ask - self.bid


class SessionState(_BaseSchema):
    """Classification of the current trading session / kill-zone."""

    session: SessionType
    time_utc: datetime
    session_start_utc: datetime
    session_end_utc: datetime
    is_kill_zone: bool = False
    is_tradeable: bool = True
    session_high: Optional[float] = Field(default=None, gt=0)
    session_low: Optional[float] = Field(default=None, gt=0)

    @field_validator("time_utc", "session_start_utc", "session_end_utc")
    @classmethod
    def _to_utc(cls, v: datetime) -> datetime:
        return to_utc(v, "session timestamp")

    @model_validator(mode="after")
    def _check_window(self) -> "SessionState":
        if self.session_end_utc < self.session_start_utc:
            raise ValueError("session_end_utc must be >= session_start_utc")
        if (
            self.session_high is not None
            and self.session_low is not None
            and self.session_high < self.session_low
        ):
            raise ValueError("session_high must be >= session_low")
        return self


class BrokerState(_BaseSchema):
    """Snapshot of broker/account health.

    Contains NO credentials (no login, password, server, or token). Defaults
    are chosen so an unverified state is non-tradeable (safe by default).
    """

    time_utc: datetime
    connection_status: BrokerConnectionStatus = BrokerConnectionStatus.UNKNOWN
    symbol: Optional[str] = None
    account_currency: Optional[str] = None
    balance: Optional[float] = Field(default=None, ge=0)
    equity: Optional[float] = Field(default=None, ge=0)
    margin: Optional[float] = Field(default=None, ge=0)
    free_margin: Optional[float] = None
    margin_level: Optional[float] = Field(default=None, ge=0)
    leverage: Optional[int] = Field(default=None, gt=0)
    open_positions: int = Field(default=0, ge=0)
    trade_allowed: bool = False

    @field_validator("symbol")
    @classmethod
    def _norm_symbol(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else _clean_symbol(v)

    @field_validator("time_utc")
    @classmethod
    def _to_utc(cls, v: datetime) -> datetime:
        return to_utc(v, "time_utc")


class TradeDecision(_BaseSchema):
    """A proposed trade decision from the intelligence brain.

    Enforces the policy guardrails (10_TASK_QUEUE.md P6-001):
    no thesis = no trade, no invalidation = no trade. The Risk Governor still
    has final authority over execution; this is only a proposal object.
    """

    decision_id: str
    time_utc: datetime
    symbol: str
    direction: Direction
    status: DecisionStatus = DecisionStatus.PROPOSED
    setup_type: Optional[str] = None
    thesis: Optional[str] = None
    invalidation_price: Optional[float] = Field(default=None, gt=0)
    entry_price: Optional[float] = Field(default=None, gt=0)
    stop_loss: Optional[float] = Field(default=None, gt=0)
    take_profits: tuple[float, ...] = ()
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    uncertainty: Optional[float] = Field(default=None, ge=0, le=1)
    reason: Optional[str] = None

    @field_validator("symbol")
    @classmethod
    def _norm_symbol(cls, v: str) -> str:
        return _clean_symbol(v)

    @field_validator("time_utc")
    @classmethod
    def _to_utc(cls, v: datetime) -> datetime:
        return to_utc(v, "time_utc")

    @field_validator("take_profits")
    @classmethod
    def _positive_targets(cls, v: tuple[float, ...]) -> tuple[float, ...]:
        if any(tp <= 0 for tp in v):
            raise ValueError("all take_profits must be > 0")
        return v

    @field_validator("decision_id")
    @classmethod
    def _non_empty_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("decision_id must be a non-empty string")
        return v

    @model_validator(mode="after")
    def _check_actionable(self) -> "TradeDecision":
        actionable = self.direction in (Direction.LONG, Direction.SHORT)
        if actionable:
            # No thesis = no trade; no invalidation = no trade (P6-001).
            if not (self.thesis and self.thesis.strip()):
                raise ValueError("actionable direction requires a non-empty thesis")
            if self.invalidation_price is None:
                raise ValueError("actionable direction requires an invalidation_price")
            # Stop must be on the correct side of entry when both are present.
            if self.entry_price is not None and self.stop_loss is not None:
                if self.direction is Direction.LONG and self.stop_loss >= self.entry_price:
                    raise ValueError("LONG stop_loss must be below entry_price")
                if self.direction is Direction.SHORT and self.stop_loss <= self.entry_price:
                    raise ValueError("SHORT stop_loss must be above entry_price")
        return self


class TradeRecord(_BaseSchema):
    """A journaled trade or no-trade decision (10_TASK_QUEUE.md P9-001)."""

    record_id: str
    created_at_utc: datetime
    symbol: str
    direction: Direction
    outcome: TradeOutcome = TradeOutcome.NO_TRADE
    decision_id: Optional[str] = None
    opened_at_utc: Optional[datetime] = None
    closed_at_utc: Optional[datetime] = None
    entry_price: Optional[float] = Field(default=None, gt=0)
    exit_price: Optional[float] = Field(default=None, gt=0)
    stop_loss: Optional[float] = Field(default=None, gt=0)
    take_profit: Optional[float] = Field(default=None, gt=0)
    lot_size: Optional[float] = Field(default=None, gt=0)
    risk_amount: Optional[float] = Field(default=None, ge=0)
    risk_pct: Optional[float] = Field(default=None, ge=0)
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    session: Optional[SessionType] = None
    regime: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    uncertainty: Optional[float] = Field(default=None, ge=0, le=1)
    thesis: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("symbol")
    @classmethod
    def _norm_symbol(cls, v: str) -> str:
        return _clean_symbol(v)

    @field_validator("record_id")
    @classmethod
    def _non_empty_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("record_id must be a non-empty string")
        return v

    @field_validator("created_at_utc")
    @classmethod
    def _created_utc(cls, v: datetime) -> datetime:
        return to_utc(v, "created_at_utc")

    @field_validator("opened_at_utc", "closed_at_utc")
    @classmethod
    def _optional_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        return None if v is None else to_utc(v, "trade timestamp")

    @model_validator(mode="after")
    def _check_times(self) -> "TradeRecord":
        if (
            self.opened_at_utc is not None
            and self.closed_at_utc is not None
            and self.closed_at_utc < self.opened_at_utc
        ):
            raise ValueError("closed_at_utc must be >= opened_at_utc")
        return self
