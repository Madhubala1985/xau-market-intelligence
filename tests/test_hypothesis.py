"""Tests for P6-001 trade hypothesis engine.

Required gates:
- no thesis = no trade,
- no invalidation = no trade.
"""

from datetime import datetime, timezone

from src.data.enums import DecisionStatus, Direction
from src.regime import HtfBias, Regime
from src.strategy import HypothesisInput, TradeHypothesisEngine

UTC = timezone.utc
NOW = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)


def base(**overrides) -> HypothesisInput:
    kwargs = dict(
        symbol="XAUUSD",
        time_utc=NOW,
        current_price=2300.0,
        htf_bias=HtfBias.BULLISH,
        regime=Regime.TREND,
        thesis_reason="sell-side sweep reclaimed with bullish displacement",
        invalidation_price=2295.0,
        target_price=2315.0,
    )
    kwargs.update(overrides)
    return HypothesisInput(**kwargs)


def engine() -> TradeHypothesisEngine:
    return TradeHypothesisEngine()


# ---------------------------------------------------------------------------
# Valid actionable hypotheses
# ---------------------------------------------------------------------------

def test_valid_long_hypothesis():
    d = engine().generate(base())
    assert d.direction is Direction.LONG
    assert d.status is DecisionStatus.PROPOSED
    assert d.thesis and d.thesis.strip()
    assert d.invalidation_price == 2295.0
    assert d.entry_price == 2300.0
    assert d.stop_loss == 2295.0          # stop below entry (correct side)
    assert d.take_profits == (2315.0,)    # explicit target used


def test_valid_short_hypothesis():
    d = engine().generate(
        base(
            htf_bias=HtfBias.BEARISH,
            current_price=2300.0,
            invalidation_price=2305.0,     # above entry for a short
            target_price=2285.0,
        )
    )
    assert d.direction is Direction.SHORT
    assert d.stop_loss == 2305.0          # stop above entry
    assert d.take_profits == (2285.0,)


def test_default_risk_reward_target_when_none_given():
    d = engine().generate(base(target_price=None))
    # risk = 2300 - 2295 = 5; default 2R -> 2300 + 10 = 2310.
    assert d.take_profits == (2310.0,)


# ---------------------------------------------------------------------------
# No thesis = no trade
# ---------------------------------------------------------------------------

def test_no_thesis_is_no_trade():
    d = engine().generate(base(thesis_reason=None))
    assert d.direction is Direction.NO_TRADE
    assert d.status is DecisionStatus.NO_TRADE
    assert "thesis" in d.reason


def test_blank_thesis_is_no_trade():
    d = engine().generate(base(thesis_reason="   "))
    assert d.direction is Direction.NO_TRADE


# ---------------------------------------------------------------------------
# No invalidation = no trade
# ---------------------------------------------------------------------------

def test_no_invalidation_is_no_trade():
    d = engine().generate(base(invalidation_price=None))
    assert d.direction is Direction.NO_TRADE
    assert "invalidation" in d.reason


def test_invalidation_wrong_side_is_no_trade():
    # LONG but invalidation above entry -> rejected.
    d = engine().generate(base(invalidation_price=2305.0))
    assert d.direction is Direction.NO_TRADE
    assert "wrong side" in d.reason


# ---------------------------------------------------------------------------
# Gates: bias and regime
# ---------------------------------------------------------------------------

def test_neutral_bias_is_wait():
    d = engine().generate(base(htf_bias=HtfBias.NEUTRAL))
    assert d.direction is Direction.WAIT
    assert d.status is DecisionStatus.PROPOSED


def test_no_trade_bias_is_no_trade():
    d = engine().generate(base(htf_bias=HtfBias.NO_TRADE))
    assert d.direction is Direction.NO_TRADE


def test_blocking_regime_is_no_trade():
    for regime in (Regime.NO_TRADE, Regime.NEWS_RISK, Regime.CHOPPY):
        d = engine().generate(base(regime=regime))
        assert d.direction is Direction.NO_TRADE, regime


# ---------------------------------------------------------------------------
# Hypotheses are proposals only (risk governor decides later)
# ---------------------------------------------------------------------------

def test_actionable_hypothesis_is_only_proposed():
    d = engine().generate(base())
    assert d.status is DecisionStatus.PROPOSED  # never APPROVED here
