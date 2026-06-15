"""Tests for the post-trade attribution + learning store (GOLD-ALPHA-001)."""

from src.strategy.trade_attribution import (
    LossReason,
    PerformanceStore,
    TradeContext,
    classify_outcome,
)


def _ctx(**kw) -> TradeContext:
    base = dict(setup_type="TREND_CONTINUATION", regime="TREND_DAY",
                direction="LONG", entry=3300.0, stop=3295.0, target=3315.0,
                score=0.4, p_win=0.45, displacement=1.4, spread_ratio=0.3,
                confirmation=0.7, stop_beyond_pool=True, extended=False)
    base.update(kw)
    return TradeContext(**base)


def test_win_is_attributed_as_win():
    assert classify_outcome(_ctx(), won=True, r_multiple=2.0) is LossReason.WIN


def test_stop_hunt_is_a_liquidity_trap():
    r = classify_outcome(_ctx(stop_beyond_pool=False), won=False,
                         r_multiple=-1.0, swept_then_reversed=True)
    assert r is LossReason.LIQUIDITY_TRAP


def test_naked_stop_loss_is_bad_sl_placement():
    r = classify_outcome(_ctx(stop_beyond_pool=False), won=False, r_multiple=-1.0)
    assert r is LossReason.BAD_SL_PLACEMENT


def test_chop_regime_loss_is_wrong_regime():
    r = classify_outcome(_ctx(regime="POST_SPIKE_CHOP"), won=False, r_multiple=-1.0)
    assert r is LossReason.WRONG_REGIME


def test_high_spread_loss_is_spread_volatility():
    r = classify_outcome(_ctx(spread_ratio=0.9), won=False, r_multiple=-1.0)
    assert r is LossReason.SPREAD_VOLATILITY


def test_weak_confirmation_loss():
    r = classify_outcome(_ctx(confirmation=0.3), won=False, r_multiple=-1.0)
    assert r is LossReason.WEAK_CONFIRMATION


def test_store_downweights_a_repeatedly_losing_setup():
    store = PerformanceStore()
    ctx = _ctx()
    # no adjustment before the minimum sample
    assert store.p_win_adjustment("TREND_CONTINUATION", "TREND_DAY") == 0.0
    for _ in range(5):
        store.record(ctx, won=False, r_multiple=-1.0,
                     reason=LossReason.WRONG_REGIME)
    adj = store.p_win_adjustment("TREND_CONTINUATION", "TREND_DAY")
    assert adj < 0  # recent failures lower the next p_win estimate


def test_store_keeps_a_winning_setup_neutral_or_better():
    store = PerformanceStore()
    ctx = _ctx()
    for _ in range(6):
        store.record(ctx, won=True, r_multiple=2.0, reason=LossReason.WIN)
    assert store.p_win_adjustment("TREND_CONTINUATION", "TREND_DAY") == 0.0
    assert "wr=100%" in store.summary("TREND_CONTINUATION", "TREND_DAY")
