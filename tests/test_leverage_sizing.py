"""Tests for RISK-001 leverage-aware, confidence-tiered position sizing.

Required (10_TASK_QUEUE.md RISK-001):
- 0.01, 0.05, and 0.10 lot XAU/USD scenarios,
- leverage/margin cannot bypass max-loss rules.
"""

from datetime import datetime, timezone

import pytest

from src.data.enums import DecisionStatus, Direction
from src.data.schemas import TradeDecision
from src.risk import (
    AccountSnapshot,
    ConfidenceTier,
    LeverageAwareSizer,
    LeverageSizingStatus,
    SymbolSpec,
    TradingMode,
)

UTC = timezone.utc
NOW = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)


def long_decision(entry: float, stop: float, **overrides) -> TradeDecision:
    kwargs = dict(
        decision_id="D-1",
        time_utc=NOW,
        symbol="XAUUSD",
        direction=Direction.LONG,
        status=DecisionStatus.PROPOSED,
        thesis="sweep reclaim with displacement",
        invalidation_price=stop,
        entry_price=entry,
        stop_loss=stop,
        take_profits=(entry + 10,),
    )
    kwargs.update(overrides)
    return TradeDecision(**kwargs)


def sizer() -> LeverageAwareSizer:
    # XAU defaults: contract 100, tick 0.01 worth $1.00 -> loss_per_lot = $ per
    # 1.0 lot = stop_distance * 100.
    return LeverageAwareSizer(SymbolSpec())


def account(balance: float = 10_000.0, free_margin: float = 10_000.0, leverage: int = 100):
    return AccountSnapshot(balance=balance, free_margin=free_margin, leverage=leverage)


# ---------------------------------------------------------------------------
# 0.01 / 0.05 / 0.10 lot scenarios (structural-stop sizing)
# ---------------------------------------------------------------------------

def test_normal_tier_sizes_001_lot():
    # NORMAL cap $40; stop $40 -> loss_per_lot $4000 -> 0.01 lot.
    r = sizer().size(long_decision(2300.0, 2260.0), account(), ConfidenceTier.NORMAL_SETUP)
    assert r.status is LeverageSizingStatus.OK
    assert r.lot_size == 0.01
    assert r.implied_loss == pytest.approx(40.0)
    assert r.implied_loss <= r.max_loss_cap + 1e-9


def test_normal_tier_sizes_005_lot():
    # NORMAL cap $40; stop $8 -> loss_per_lot $800 -> 0.05 lot.
    r = sizer().size(long_decision(2300.0, 2292.0), account(), ConfidenceTier.NORMAL_SETUP)
    assert r.status is LeverageSizingStatus.OK
    assert r.lot_size == 0.05
    assert r.implied_loss == pytest.approx(40.0)


def test_normal_tier_sizes_010_lot():
    # NORMAL cap $40; stop $4 -> loss_per_lot $400 -> 0.10 lot.
    r = sizer().size(long_decision(2300.0, 2296.0), account(), ConfidenceTier.NORMAL_SETUP)
    assert r.status is LeverageSizingStatus.OK
    assert r.lot_size == 0.10
    assert r.implied_loss == pytest.approx(40.0)


def test_tier_caps_scale_lot():
    # Same $8 stop: NORMAL $40 -> 0.05; HIGH $80 -> 0.10; ELITE $100 -> 0.12.
    d = long_decision(2300.0, 2292.0)
    assert sizer().size(d, account(), ConfidenceTier.NORMAL_SETUP).lot_size == 0.05
    assert sizer().size(d, account(), ConfidenceTier.HIGH_CONFLUENCE_SETUP).lot_size == 0.10
    assert sizer().size(d, account(), ConfidenceTier.ELITE_A_PLUS_SETUP).lot_size == 0.12


def test_no_trade_tier_blocks():
    r = sizer().size(long_decision(2300.0, 2292.0), account(), ConfidenceTier.NO_TRADE)
    assert r.status is LeverageSizingStatus.NO_TRADE_TIER
    assert r.lot_size == 0.0


def test_lot_snapped_down_never_exceeds_cap():
    # stop $8.50 -> loss_per_lot $850; $40/850 = 0.047 -> snaps down to 0.04.
    r = sizer().size(long_decision(2300.0, 2291.5), account(), ConfidenceTier.NORMAL_SETUP)
    assert r.status is LeverageSizingStatus.OK
    assert r.lot_size == 0.04
    assert r.implied_loss <= 40.0 + 1e-9


def test_stop_too_wide_blocks_min_lot_over_cap():
    # NORMAL cap $40; stop $50 -> loss_per_lot $5000; min 0.01 lot loses $50 > cap.
    r = sizer().size(long_decision(2300.0, 2250.0), account(), ConfidenceTier.NORMAL_SETUP)
    assert r.status is LeverageSizingStatus.STOP_TOO_WIDE
    assert r.lot_size == 0.0


# ---------------------------------------------------------------------------
# Leverage / margin cannot bypass max-loss rules
# ---------------------------------------------------------------------------

def test_leverage_does_not_increase_lot_or_loss():
    d = long_decision(2300.0, 2292.0)  # $8 stop, NORMAL -> 0.05 lot
    low_lev = sizer().size(d, account(leverage=100), ConfidenceTier.NORMAL_SETUP)
    high_lev = sizer().size(d, account(leverage=2000), ConfidenceTier.NORMAL_SETUP)
    # Higher leverage does NOT enlarge the lot or the loss at stop.
    assert high_lev.lot_size == low_lev.lot_size == 0.05
    assert high_lev.implied_loss == low_lev.implied_loss == pytest.approx(40.0)
    # It only reduces the margin required.
    assert high_lev.margin_required < low_lev.margin_required


def test_insufficient_margin_blocks_does_not_resize():
    d = long_decision(2300.0, 2292.0)  # 0.05 lot; notional 0.05*100*2300 = 11_500
    # leverage 100 -> margin 115; free margin only 50 -> blocked, not resized.
    r = sizer().size(
        d, account(free_margin=50.0, leverage=100), ConfidenceTier.NORMAL_SETUP
    )
    assert r.status is LeverageSizingStatus.INSUFFICIENT_MARGIN
    assert r.lot_size == 0.0


# ---------------------------------------------------------------------------
# Fixed-lot assessment (0.01 / 0.05 / 0.10 only if within cap)
# ---------------------------------------------------------------------------

def test_fixed_lot_within_cap_allowed():
    # stop $4 -> loss_per_lot $400; 0.10 lot -> $40 == NORMAL cap.
    r = sizer().assess_fixed_lot(
        long_decision(2300.0, 2296.0), account(), ConfidenceTier.NORMAL_SETUP, 0.10
    )
    assert r.status is LeverageSizingStatus.OK
    assert r.lot_size == 0.10
    assert r.implied_loss == pytest.approx(40.0)


def test_fixed_lot_over_cap_blocked():
    # stop $8 -> loss_per_lot $800; 0.10 lot -> $80 > NORMAL cap $40.
    r = sizer().assess_fixed_lot(
        long_decision(2300.0, 2292.0), account(), ConfidenceTier.NORMAL_SETUP, 0.10
    )
    assert r.status is LeverageSizingStatus.FIXED_LOT_EXCEEDS_CAP
    assert r.lot_size == 0.0


def test_fixed_lot_over_cap_allowed_in_higher_tier():
    # Same 0.10 lot at $8 stop = $80, allowed under HIGH_CONFLUENCE cap $80.
    r = sizer().assess_fixed_lot(
        long_decision(2300.0, 2292.0), account(), ConfidenceTier.HIGH_CONFLUENCE_SETUP, 0.10
    )
    assert r.status is LeverageSizingStatus.OK
    assert r.implied_loss == pytest.approx(80.0)


def test_fixed_lot_invalid_step_blocked():
    r = sizer().assess_fixed_lot(
        long_decision(2300.0, 2296.0), account(), ConfidenceTier.NORMAL_SETUP, 0.013
    )
    assert r.status is LeverageSizingStatus.INVALID_LOT


def test_fixed_lot_leverage_cannot_bypass_cap():
    # Even with abundant margin via high leverage, an over-cap fixed lot is blocked.
    r = sizer().assess_fixed_lot(
        long_decision(2300.0, 2292.0),
        account(free_margin=1_000_000.0, leverage=2000),
        ConfidenceTier.NORMAL_SETUP,
        0.10,
    )
    assert r.status is LeverageSizingStatus.FIXED_LOT_EXCEEDS_CAP


# ---------------------------------------------------------------------------
# Real mode does not inherit demo tiers
# ---------------------------------------------------------------------------

def test_real_mode_uses_conservative_balance_risk_not_demo_tier():
    # Real cap = balance * real_risk_pct = 10_000 * 0.005 = $50 (NOT the $100 elite).
    sz = LeverageAwareSizer(SymbolSpec(), real_risk_pct=0.005)
    r = sz.size(
        long_decision(2300.0, 2295.0),  # $5 stop -> loss_per_lot $500
        account(),
        ConfidenceTier.ELITE_A_PLUS_SETUP,
        mode=TradingMode.REAL,
    )
    assert r.status is LeverageSizingStatus.OK
    assert r.max_loss_cap == pytest.approx(50.0)
    assert r.lot_size == 0.10  # 50 / 500
    assert r.implied_loss <= 50.0 + 1e-9


def test_real_cap_is_lower_than_demo_cap_same_setup():
    d = long_decision(2300.0, 2295.0)
    sz = LeverageAwareSizer(SymbolSpec(), real_risk_pct=0.001)  # very conservative
    demo = sz.size(d, account(), ConfidenceTier.ELITE_A_PLUS_SETUP, mode=TradingMode.DEMO)
    real = sz.size(d, account(), ConfidenceTier.ELITE_A_PLUS_SETUP, mode=TradingMode.REAL)
    assert real.max_loss_cap < demo.max_loss_cap
    assert real.lot_size <= demo.lot_size


# ---------------------------------------------------------------------------
# Invalid input
# ---------------------------------------------------------------------------

def test_missing_stop_invalid():
    d = TradeDecision(
        decision_id="D-x", time_utc=NOW, symbol="XAUUSD",
        direction=Direction.NO_TRADE, status=DecisionStatus.NO_TRADE,
    )
    r = sizer().size(d, account(), ConfidenceTier.NORMAL_SETUP)
    assert r.status is LeverageSizingStatus.INVALID_INPUT


def test_sizer_has_no_order_method():
    sz = sizer()
    for attr in ("execute", "order_send", "send", "place_order", "buy", "sell"):
        assert not hasattr(sz, attr)
