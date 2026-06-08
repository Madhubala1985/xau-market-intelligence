"""Tests for P1-001 core data schemas.

Covers the four required test categories from 12_HANDOFF.md:
- schema validation (valid data is accepted),
- invalid data rejection,
- timestamp handling (broker time preserved, normalized time is UTC),
- no credential printing / no credential fields.
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.data import (
    BrokerConnectionStatus,
    BrokerState,
    Candle,
    DecisionStatus,
    Direction,
    SessionState,
    SessionType,
    SpreadSnapshot,
    Tick,
    TradeDecision,
    TradeOutcome,
    TradeRecord,
)

UTC = timezone.utc
# A fixed broker timezone (UTC+2, typical MT5 server offset) for tests.
BROKER_TZ = timezone(timedelta(hours=2))
NOW_UTC = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Schema validation: valid data is accepted
# ---------------------------------------------------------------------------

def test_valid_candle_is_accepted():
    candle = Candle(
        symbol="xauusd",
        timeframe="1H",
        broker_time=NOW_UTC.astimezone(BROKER_TZ),
        time_utc=NOW_UTC,
        open=2300.0,
        high=2310.5,
        low=2299.0,
        close=2305.0,
        tick_volume=1500,
    )
    assert candle.symbol == "XAUUSD"  # normalized to upper-case
    assert candle.high >= candle.close >= candle.low


def test_valid_tick_spread_property():
    tick = Tick(
        symbol="XAUUSD",
        broker_time=NOW_UTC.astimezone(BROKER_TZ),
        time_utc=NOW_UTC,
        bid=2300.0,
        ask=2300.4,
    )
    assert tick.spread == pytest.approx(0.4)


def test_valid_spread_snapshot_property():
    snap = SpreadSnapshot(symbol="XAUUSD", time_utc=NOW_UTC, bid=2300.0, ask=2300.6)
    assert snap.spread_price == pytest.approx(0.6)


def test_valid_session_state():
    state = SessionState(
        session=SessionType.LONDON,
        time_utc=NOW_UTC,
        session_start_utc=NOW_UTC - timedelta(hours=1),
        session_end_utc=NOW_UTC + timedelta(hours=2),
        is_kill_zone=True,
    )
    assert state.is_tradeable is True


def test_valid_long_trade_decision():
    decision = TradeDecision(
        decision_id="D-1",
        time_utc=NOW_UTC,
        symbol="XAUUSD",
        direction=Direction.LONG,
        thesis="Sweep of Asian low then reclaim into London.",
        invalidation_price=2295.0,
        entry_price=2301.0,
        stop_loss=2296.0,
        take_profits=(2310.0, 2320.0),
        confidence=0.6,
        uncertainty=0.3,
    )
    assert decision.status is DecisionStatus.PROPOSED
    assert decision.direction is Direction.LONG


def test_no_trade_decision_needs_no_thesis():
    decision = TradeDecision(
        decision_id="D-2",
        time_utc=NOW_UTC,
        symbol="XAUUSD",
        direction=Direction.NO_TRADE,
    )
    assert decision.direction is Direction.NO_TRADE


def test_valid_trade_record():
    record = TradeRecord(
        record_id="R-1",
        created_at_utc=NOW_UTC,
        symbol="XAUUSD",
        direction=Direction.SHORT,
        outcome=TradeOutcome.WIN,
        opened_at_utc=NOW_UTC,
        closed_at_utc=NOW_UTC + timedelta(hours=3),
        entry_price=2305.0,
        exit_price=2295.0,
        pnl=100.0,
    )
    assert record.outcome is TradeOutcome.WIN


# ---------------------------------------------------------------------------
# Invalid data rejection
# ---------------------------------------------------------------------------

def test_candle_rejects_impossible_high():
    with pytest.raises(ValidationError):
        Candle(
            symbol="XAUUSD",
            timeframe="1H",
            broker_time=NOW_UTC,
            time_utc=NOW_UTC,
            open=2300.0,
            high=2299.0,  # high below open/close
            low=2298.0,
            close=2301.0,
            tick_volume=10,
        )


def test_candle_rejects_negative_price():
    with pytest.raises(ValidationError):
        Candle(
            symbol="XAUUSD",
            timeframe="1H",
            broker_time=NOW_UTC,
            time_utc=NOW_UTC,
            open=-1.0,
            high=2310.0,
            low=2290.0,
            close=2305.0,
            tick_volume=10,
        )


def test_candle_rejects_unknown_field():
    with pytest.raises(ValidationError):
        Candle(
            symbol="XAUUSD",
            timeframe="1H",
            broker_time=NOW_UTC,
            time_utc=NOW_UTC,
            open=2300.0,
            high=2310.0,
            low=2290.0,
            close=2305.0,
            tick_volume=10,
            injected_field="oops",
        )


def test_tick_rejects_inconsistent_quote():
    with pytest.raises(ValidationError):
        Tick(
            symbol="XAUUSD",
            broker_time=NOW_UTC,
            time_utc=NOW_UTC,
            bid=2300.5,
            ask=2300.0,  # ask below bid
        )


def test_empty_symbol_rejected():
    with pytest.raises(ValidationError):
        SpreadSnapshot(symbol="   ", time_utc=NOW_UTC, bid=2300.0, ask=2300.5)


def test_session_state_rejects_inverted_window():
    with pytest.raises(ValidationError):
        SessionState(
            session=SessionType.NEW_YORK,
            time_utc=NOW_UTC,
            session_start_utc=NOW_UTC,
            session_end_utc=NOW_UTC - timedelta(hours=1),
        )


def test_long_decision_requires_thesis_and_invalidation():
    with pytest.raises(ValidationError):
        TradeDecision(
            decision_id="D-3",
            time_utc=NOW_UTC,
            symbol="XAUUSD",
            direction=Direction.LONG,  # no thesis, no invalidation
        )


def test_long_decision_rejects_stop_above_entry():
    with pytest.raises(ValidationError):
        TradeDecision(
            decision_id="D-4",
            time_utc=NOW_UTC,
            symbol="XAUUSD",
            direction=Direction.LONG,
            thesis="valid thesis",
            invalidation_price=2295.0,
            entry_price=2300.0,
            stop_loss=2305.0,  # wrong side for a long
        )


def test_confidence_out_of_range_rejected():
    with pytest.raises(ValidationError):
        TradeDecision(
            decision_id="D-5",
            time_utc=NOW_UTC,
            symbol="XAUUSD",
            direction=Direction.WAIT,
            confidence=1.5,
        )


def test_trade_record_rejects_close_before_open():
    with pytest.raises(ValidationError):
        TradeRecord(
            record_id="R-2",
            created_at_utc=NOW_UTC,
            symbol="XAUUSD",
            direction=Direction.LONG,
            opened_at_utc=NOW_UTC,
            closed_at_utc=NOW_UTC - timedelta(minutes=5),
        )


def test_empty_decision_id_rejected():
    with pytest.raises(ValidationError):
        TradeDecision(
            decision_id="  ",
            time_utc=NOW_UTC,
            symbol="XAUUSD",
            direction=Direction.NO_TRADE,
        )


# ---------------------------------------------------------------------------
# Timestamp handling
# ---------------------------------------------------------------------------

def test_naive_timestamp_rejected():
    with pytest.raises(ValidationError):
        Candle(
            symbol="XAUUSD",
            timeframe="1H",
            broker_time=datetime(2026, 6, 8, 14, 0),  # naive -> rejected
            time_utc=NOW_UTC,
            open=2300.0,
            high=2310.0,
            low=2290.0,
            close=2305.0,
            tick_volume=10,
        )


def test_time_utc_normalized_to_utc():
    broker_ts = NOW_UTC.astimezone(BROKER_TZ)  # same instant, +02:00 offset
    candle = Candle(
        symbol="XAUUSD",
        timeframe="5M",
        broker_time=broker_ts,
        time_utc=broker_ts,  # provided in broker tz, must normalize to UTC
        open=2300.0,
        high=2310.0,
        low=2290.0,
        close=2305.0,
        tick_volume=10,
    )
    # Normalized timestamp is UTC...
    assert candle.time_utc.utcoffset() == timedelta(0)
    # ...and the broker timestamp is preserved with its original offset.
    assert candle.broker_time.utcoffset() == timedelta(hours=2)
    # Both represent the same instant.
    assert candle.time_utc == candle.broker_time


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------

def test_schemas_are_frozen():
    snap = SpreadSnapshot(symbol="XAUUSD", time_utc=NOW_UTC, bid=2300.0, ask=2300.5)
    with pytest.raises(ValidationError):
        snap.bid = 2400.0


# ---------------------------------------------------------------------------
# No credentials in the data layer
# ---------------------------------------------------------------------------

CREDENTIAL_TOKENS = ("login", "password", "passwd", "secret", "token", "server", "apikey", "api_key")


@pytest.mark.parametrize(
    "model",
    [Candle, Tick, SpreadSnapshot, SessionState, BrokerState, TradeDecision, TradeRecord],
)
def test_no_credential_fields(model):
    for field_name in model.model_fields:
        lowered = field_name.lower()
        assert not any(token in lowered for token in CREDENTIAL_TOKENS), (
            f"{model.__name__} exposes credential-like field '{field_name}'"
        )


def test_broker_state_safe_defaults_and_no_credential_leak():
    state = BrokerState(time_utc=NOW_UTC)
    # Safe by default: unknown connection, trading not allowed.
    assert state.connection_status is BrokerConnectionStatus.UNKNOWN
    assert state.trade_allowed is False
    # repr / serialization must not contain credential tokens.
    dumped = (repr(state) + " " + state.model_dump_json()).lower()
    for token in CREDENTIAL_TOKENS:
        assert token not in dumped
