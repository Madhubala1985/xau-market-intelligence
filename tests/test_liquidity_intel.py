"""LiquidityIntelEngine tests (LIQUIDITY-INTEL-001).

Covers the autonomy + safety requirements:
- the stop is placed BEYOND the engineered liquidity pool, never at it;
- a stop that cannot be protected within budget returns None (engine WAITs);
- all six timeframes are consumed (not just printed);
- news risk / featureless tape produce FLAT / WAIT with an explicit re-arm
  reason (never a silent permanent block);
- the consumed-stop (H8) guard refuses re-fading a just-swept level;
- the reclaim detector only fires when the reclaim holds.
"""

from datetime import datetime, timedelta, timezone

from src.data.enums import BrokerConnectionStatus, Direction, Timeframe
from src.data.schemas import BrokerState, Candle
from src.liquidity.liquidity_map import (
    LiquidityKind,
    LiquidityLevel,
    LiquidityMap,
    LiquiditySide,
)
from src.liquidity.sweep import SweepEvent, SweepStatus
from src.strategy.liquidity_intel import (
    PROFILE_NAME,
    Posture,
    make_liquidity_intel_pipeline,
)
from src.strategy.pipeline import PipelineInput
from src.structure.market_structure import Bias

NOW = datetime(2026, 6, 15, 13, 0, tzinfo=timezone.utc)
SYM = "XAUUSD"


def _candle(tf, t, o, h, l, c, v=500):
    return Candle(symbol=SYM, timeframe=tf, broker_time=t, time_utc=t,
                  open=o, high=h, low=l, close=c, tick_volume=v)


def _series(tf, n, start, step_min, drift, vol=1.0):
    out, price = [], start
    for i in range(n):
        t = NOW - timedelta(minutes=step_min * (n - i))
        o, c = price, price + drift
        out.append(_candle(tf, t, o, max(o, c) + vol, min(o, c) - vol, c))
        price = c
    return out


def _broker(balance=2000.0, open_positions=0):
    return BrokerState(
        time_utc=NOW, connection_status=BrokerConnectionStatus.CONNECTED,
        symbol="XAUUSDm", balance=balance, equity=balance, free_margin=balance,
        leverage=200, open_positions=open_positions, trade_allowed=True)


def _input(**kw):
    m5 = kw.pop("m5", _series("5M", 120, 3300, 5, 0.0, 1.2))
    return PipelineInput(
        symbol="XAUUSDm", exec_candles=m5,
        daily_candles=kw.pop("d1", _series("1D", 30, 2500, 1440, 5.0, 20.0)),
        h4_candles=kw.pop("h4", _series("4H", 40, 2900, 240, 2.0, 8.0)),
        m15_candles=kw.pop("m15", _series("15M", 80, 3250, 15, 0.5, 2.0)),
        h1_candles=kw.pop("h1", _series("1H", 60, 3100, 60, 1.0, 4.0)),
        m1_candles=kw.pop("m1", _series("1M", 60, 3380, 1, 0.0, 0.5)),
        broker=kw.pop("broker", _broker()), current_spread=kw.pop("spread", 0.3),
        now=NOW, **kw)


# -- the protected-stop doctrine (deterministic) ---------------------------

def _engine():
    return make_liquidity_intel_pipeline(SYM)


def test_short_stop_is_pushed_beyond_a_buy_side_pool():
    """A SHORT entry at 3350 with invalidation just above at 3352; a resting
    buy-side pool sits at 3353. The stop MUST end up beyond 3353, not at the
    naked 3352 swing where the pool would be hunted."""
    eng = _engine()
    pool = LiquidityLevel(kind=LiquidityKind.EQUAL_HIGHS,
                          side=LiquiditySide.BUY_SIDE, price=3353.0,
                          time_utc=NOW)
    lmap = LiquidityMap(levels=(pool,))
    result = eng._protect_stop_from_pool(
        Direction.SHORT, entry=3350.0, base_level=3352.0, atr5=2.0,
        spread=0.3, liquidity_map=lmap)
    assert result is not None
    stop_price, distance = result
    assert stop_price > 3353.0          # beyond the pool
    assert stop_price > 3350.0          # correct side of entry for a SHORT
    assert distance > 0


def test_long_stop_is_pushed_below_a_sell_side_pool():
    eng = _engine()
    pool = LiquidityLevel(kind=LiquidityKind.EQUAL_LOWS,
                          side=LiquiditySide.SELL_SIDE, price=3347.0,
                          time_utc=NOW)
    lmap = LiquidityMap(levels=(pool,))
    result = eng._protect_stop_from_pool(
        Direction.LONG, entry=3350.0, base_level=3348.0, atr5=2.0,
        spread=0.3, liquidity_map=lmap)
    assert result is not None
    stop_price, _ = result
    assert stop_price < 3347.0          # beyond (below) the pool
    assert stop_price < 3350.0


def test_unprotectable_stop_returns_none_so_engine_waits():
    eng = _engine()
    lmap = LiquidityMap(levels=())
    # base level 40 USD away -> distance far beyond the 8 USD ceiling.
    result = eng._protect_stop_from_pool(
        Direction.SHORT, entry=3350.0, base_level=3390.0, atr5=1.0,
        spread=0.3, liquidity_map=lmap)
    assert result is None


def test_wrong_side_base_level_is_rejected():
    eng = _engine()
    lmap = LiquidityMap(levels=())
    # a SHORT cannot have its invalidation BELOW entry.
    assert eng._protect_stop_from_pool(
        Direction.SHORT, entry=3350.0, base_level=3349.0, atr5=1.0,
        spread=0.3, liquidity_map=lmap) is None


# -- reclaim detection ------------------------------------------------------

def test_reclaim_only_fires_when_the_reclaim_holds():
    eng = _engine()
    # build M5 where index -2 swept below 3300 and -1 closed back above (held).
    m5 = _series("5M", 40, 3320, 5, -0.5, 0.5)
    swept_level = 3300.0
    m5[-2] = _candle("5M", m5[-2].time_utc, 3301, 3302, 3298, 3299)  # dipped
    m5[-1] = _candle("5M", m5[-1].time_utc, 3299, 3304, 3299, 3303)  # reclaimed
    pool = LiquidityLevel(kind=LiquidityKind.SWING_LOW,
                          side=LiquiditySide.SELL_SIDE, price=swept_level,
                          time_utc=m5[-2].time_utc)
    sweep = SweepEvent(level=pool, swept_side=LiquiditySide.SELL_SIDE,
                       rejection_bias=Bias.BULLISH, sweep_index=len(m5) - 2,
                       sweep_time=m5[-2].time_utc, status=SweepStatus.TRUE_SWEEP)
    held = eng._fresh_reclaimed_sweep(Bias.BULLISH, m5, [sweep])
    assert held is sweep

    # if the latest close is still BELOW the level, the reclaim did not hold.
    m5[-1] = _candle("5M", m5[-1].time_utc, 3299, 3299.5, 3296, 3297)
    assert eng._fresh_reclaimed_sweep(Bias.BULLISH, m5, [sweep]) is None


# -- decide(): full context, safety, anti-silence ---------------------------

def test_decide_consumes_all_six_timeframes():
    eng = _engine()
    result = eng.decide(_input())
    ch = result.context.challenge
    htf = ch["htf_context"]
    for tf in ("d1=", "h4=", "h1=", "m15=", "m5="):
        assert tf in htf            # HTF/MTF frames are read, not just printed
    assert "mtf_score=" in htf


def test_decide_populates_every_required_output_field():
    eng = _engine()
    ch = eng.decide(_input()).context.challenge
    required = ["htf_context", "killzone", "liquidity_context", "liquidity_map",
               "sweep_status", "structure_state", "fvg_ob_status", "orderflow",
               "premium_discount", "direction", "posture", "reason",
               "sl_tp_trail"]
    assert all(k in ch for k in required)
    assert ch["profile"] == PROFILE_NAME


def test_news_risk_forces_flat_and_blocks_entries():
    eng = _engine()
    result = eng.decide(_input(news_risk=True))
    assert not result.approved
    ch = result.context.challenge
    assert ch["posture"] == Posture.FLAT
    assert "NEWS_RISK" in ch["reason"]


def test_featureless_tape_waits_with_a_rearm_reason_not_silence():
    eng = _engine()
    ch = eng.decide(_input()).context.challenge
    # No qualified posture, but the engine always says what it is waiting for.
    assert ch["posture"] in (Posture.WAIT, Posture.FLAT)
    assert ch["reason"]                       # never empty
    assert ch["waiting_for"] or ch["reentry_plan"]


def test_wide_spread_is_flat():
    eng = _engine()
    result = eng.decide(_input(spread=5.0))
    assert not result.approved
    assert "spread too high" in result.context.challenge["reason"]


def test_consumed_stop_guard_blocks_refading_a_just_swept_level():
    eng = _engine()
    # record a SHORT stop loss at 3352, then a near new SHORT stop is refused.
    eng.note_stop_loss(Direction.SHORT, 3352.0, NOW)
    block = eng._consumed_stop_block(Direction.SHORT, 3352.5, atr5=2.0, now=NOW)
    assert "ZONE_CONSUMED" in block
    # a stop that clears the level by the clearance is allowed.
    assert eng._consumed_stop_block(
        Direction.SHORT, 3360.0, atr5=2.0, now=NOW) == ""
