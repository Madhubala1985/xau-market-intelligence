"""Tests for P3-001 swing & market-structure engine (fixed candle examples)."""

from datetime import datetime, timedelta, timezone

from src.data.schemas import Candle
from src.structure import (
    Bias,
    MarketStructureEngine,
    StructureEventType,
    SwingType,
)

UTC = timezone.utc
T0 = datetime(2026, 6, 9, 0, 0, tzinfo=UTC)


def c(i: int, high: float, low: float, close: float) -> Candle:
    """Candle i (hourly) with open inside the range."""
    open_ = max(low, min(high, close))  # keep schema-valid
    return Candle(
        symbol="XAUUSD",
        timeframe="1H",
        broker_time=T0 + i * timedelta(hours=1),
        time_utc=T0 + i * timedelta(hours=1),
        open=open_,
        high=high,
        low=low,
        close=close,
        tick_volume=100,
    )


# A fixed narrative (strength=1):
#  - idx1 swing high (11.0), idx2 swing low (8.5)
#  - idx3 close 12.2 breaks 11.0          -> BOS bullish (establishes trend)
#  - idx3 swing high (12.5), idx4 swing low (10.0, higher low)
#  - idx5 close 13.8 breaks 12.5          -> BOS bullish (continuation)
#  - idx5 swing high (14.0)
#  - idx7 close 9.5 breaks the higher low 10.0 -> CHOCH bearish
NARRATIVE = [
    c(0, 10.0, 9.0, 9.5),
    c(1, 11.0, 9.5, 10.5),
    c(2, 10.5, 8.5, 9.0),
    c(3, 12.5, 11.0, 12.2),
    c(4, 12.0, 10.0, 11.0),
    c(5, 14.0, 11.0, 13.8),
    c(6, 13.5, 12.0, 12.5),
    c(7, 12.0, 9.0, 9.5),
]


# ---------------------------------------------------------------------------
# Swing detection
# ---------------------------------------------------------------------------

def test_find_swings_simple_peak_and_trough():
    candles = [
        c(0, 10, 8, 9),
        c(1, 12, 9, 11),   # swing high
        c(2, 11, 7, 8),    # swing low
        c(3, 13, 8, 12),
    ]
    swings = MarketStructureEngine(strength=1).find_swings(candles)
    highs = [s for s in swings if s.swing_type is SwingType.HIGH]
    lows = [s for s in swings if s.swing_type is SwingType.LOW]
    assert any(s.index == 1 and s.price == 12 for s in highs)
    assert any(s.index == 2 and s.price == 7 for s in lows)


def test_swing_confirmed_index_lags_by_strength():
    swings = MarketStructureEngine(strength=2).find_swings(
        [c(i, 10 + (i == 3) * 5, 5 - (i == 3) * 0, 8) for i in range(7)]
    )
    # The peak at index 3 is only confirmed at index 5 (3 + strength 2).
    peak = next(s for s in swings if s.index == 3 and s.swing_type is SwingType.HIGH)
    assert peak.confirmed_index == 5


def test_equal_highs_produce_no_strict_swing():
    candles = [c(0, 10, 8, 9), c(1, 12, 9, 11), c(2, 12, 9, 11), c(3, 10, 8, 9)]
    swings = MarketStructureEngine(strength=1).find_swings(candles)
    assert all(s.swing_type is not SwingType.HIGH for s in swings)


# ---------------------------------------------------------------------------
# BOS / CHOCH
# ---------------------------------------------------------------------------

def test_full_narrative_events():
    result = MarketStructureEngine(strength=1).analyze(NARRATIVE)
    events = result.events
    assert len(events) == 3

    assert events[0].event_type is StructureEventType.BOS
    assert events[0].bias is Bias.BULLISH
    assert events[0].index == 3
    assert events[0].price == 11.0

    assert events[1].event_type is StructureEventType.BOS
    assert events[1].bias is Bias.BULLISH
    assert events[1].index == 5
    assert events[1].price == 12.5

    assert events[2].event_type is StructureEventType.CHOCH
    assert events[2].bias is Bias.BEARISH
    assert events[2].index == 7
    assert events[2].price == 10.0

    assert result.final_bias is Bias.BEARISH


def test_ranging_market_has_no_events():
    candles = [
        c(0, 10.0, 9.0, 9.5),
        c(1, 10.2, 9.1, 9.6),
        c(2, 10.1, 9.0, 9.5),
        c(3, 10.2, 9.1, 9.6),
        c(4, 10.1, 9.0, 9.5),
    ]
    result = MarketStructureEngine(strength=1).analyze(candles)
    assert result.events == ()
    assert result.final_bias is Bias.NEUTRAL


def test_too_short_series_is_safe():
    result = MarketStructureEngine(strength=2).analyze([c(0, 10, 9, 9.5)])
    assert result.swings == ()
    assert result.events == ()
    assert result.final_bias is Bias.NEUTRAL


# ---------------------------------------------------------------------------
# No look-ahead (prefix stability)
# ---------------------------------------------------------------------------

def test_no_lookahead_prefix_stability():
    engine = MarketStructureEngine(strength=1)
    full = engine.analyze(NARRATIVE)

    # Events detected on a prefix must match the same events on the full series.
    for cut in range(1, len(NARRATIVE) + 1):
        prefix = engine.analyze(NARRATIVE[:cut])
        # Every prefix event equals the corresponding full-series event.
        for i, ev in enumerate(prefix.events):
            assert ev.index == full.events[i].index
            assert ev.event_type is full.events[i].event_type
            assert ev.bias is full.events[i].bias
            assert ev.price == full.events[i].price


def test_events_only_appear_after_their_candle():
    engine = MarketStructureEngine(strength=1)
    # Before idx3, no break has happened yet.
    assert engine.analyze(NARRATIVE[:3]).events == ()
    # Through idx3, exactly the first BOS exists.
    assert len(engine.analyze(NARRATIVE[:4]).events) == 1
    # Through idx5, the first two events exist.
    assert len(engine.analyze(NARRATIVE[:6]).events) == 2
