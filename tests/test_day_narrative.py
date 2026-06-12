"""Tests for the SMC v2 day-narrative engine (SMC-V2-001).

Each scenario constructs a full M5 day and asserts the narrative state,
allowed playbooks/directions, and conviction sign. The engine must be a
pure function of the candles (replay == live), so every test calls
narrate() twice and asserts identical output.
"""

from datetime import datetime, timedelta, timezone

from src.data.enums import Direction
from src.data.session_levels import AsianRangeContext
from src.strategy.day_narrative import (
    CONVICTION_ENTRY_MIN,
    DayNarrativeEngine,
    DayState,
    PB_RANGE_FADE,
    PB_SWEEP_RECLAIM,
    PB_TREND_CONTINUATION,
)
from tests.test_demo_challenge import make_candles

DAY = datetime(2026, 6, 12, 0, 5, tzinfo=timezone.utc)


def asian(high=3402.0, low=3398.0):
    return AsianRangeContext(known=True, high=high, low=low)


def flat_day(n=60, base=3400.0, amp=0.3):
    closes = [base + (amp if i % 2 else -amp) for i in range(n)]
    return make_candles(closes, start=DAY)


def trend_up_day():
    """Quiet open, then repeated strong up-legs expanding past the range."""
    closes = [3400.0 + (0.2 if i % 2 else -0.2) for i in range(30)]
    px = 3400.0
    for i in range(40):
        px += 1.6 if i % 4 != 3 else -0.4   # 3 strong up candles, tiny dip
        closes.append(px)
    return make_candles(closes, start=DAY)


def range_day():
    """Wick rejections of the developing extremes on both sides: each poke
    candle's HIGH/LOW exceeds the prior extreme while its close stays
    inside (sweep-and-fail), escalating so every poke is a new extreme."""
    from src.data.schemas import Candle
    from tests.test_demo_challenge import SYMBOL

    candles, t = [], DAY
    for cycle in range(6):
        poke = 1.0 + 0.4 * cycle
        bars = [
            # (open, high, low, close)
            (3400.0, 3400.4, 3399.6, 3400.1),
            (3400.1, 3401.0 + poke, 3399.9, 3400.3),   # upper rejection
            (3400.3, 3400.6, 3399.7, 3400.0),
            (3400.0, 3400.3, 3399.0 - poke, 3399.9),   # lower rejection
            (3399.9, 3400.4, 3399.6, 3400.1),
        ]
        for o, h, lo, c in bars:
            candles.append(Candle(
                symbol=SYMBOL, timeframe="M5", broker_time=t, time_utc=t,
                open=o, high=h, low=lo, close=c, tick_volume=100,
            ))
            t += timedelta(minutes=5)
    return candles


def spike_day():
    closes = [3400.0 + (0.2 if i % 2 else -0.2) for i in range(50)]
    closes += [3414.0]          # one violent 14-USD candle
    closes += [3413.5, 3414.2]  # no acceptance yet
    return make_candles(closes, start=DAY)


def engine():
    return DayNarrativeEngine()


def test_pure_function_replay_equals_live():
    m5 = trend_up_day()
    a, b = engine().narrate(m5, asian=asian()), engine().narrate(
        m5, asian=asian())
    assert a == b


def test_opening_with_too_few_candles():
    n = engine().narrate(flat_day(n=4), asian=asian())
    assert n.state is DayState.OPENING
    assert not n.tradeable
    assert n.rearm_condition


def test_trend_day_allows_continuation_with_the_trend_only():
    n = engine().narrate(trend_up_day(), asian=asian())
    assert n.state is DayState.TREND_DAY
    assert n.direction is Direction.LONG
    assert PB_TREND_CONTINUATION in n.allowed_playbooks
    assert n.allowed_directions == (Direction.LONG,)
    assert n.pyramids_allowed
    assert n.conviction > 0


def test_trend_day_conviction_can_carry_entries():
    n = engine().narrate(trend_up_day(), asian=asian(),
                         htf_direction=Direction.LONG)
    assert n.conviction >= CONVICTION_ENTRY_MIN


def test_range_day_allows_fades_only_no_pyramids():
    n = engine().narrate(range_day(), asian=asian(3401.0, 3399.0))
    assert n.state is DayState.RANGE_DAY
    assert n.allowed_playbooks == (PB_RANGE_FADE,)
    assert not n.pyramids_allowed


def test_spike_without_acceptance_stands_down():
    n = engine().narrate(spike_day(), asian=asian())
    assert n.state is DayState.POST_SPIKE_CHOP
    assert not n.tradeable
    assert "stand down" in n.rearm_condition


def test_spike_with_held_reclaim_allows_only_sweep_reclaim():
    n = engine().narrate(
        spike_day(), asian=asian(),
        swept_levels=[(3414.0, Direction.SHORT)], reclaim_held=True,
    )
    assert n.state is DayState.POST_SPIKE_CHOP
    assert n.allowed_playbooks == (PB_SWEEP_RECLAIM,)
    assert n.allowed_directions == (Direction.SHORT,)


def test_trap_reversal_after_held_sweep_with_reversal_leg():
    closes = [3400.0 + 0.3 * i for i in range(30)]        # drift up
    closes += [3409.0, 3406.0, 3403.0, 3400.0, 3397.0]    # reversal legs
    m5 = make_candles(closes, start=DAY)
    n = engine().narrate(
        m5, asian=asian(3408.0, 3396.0),
        swept_levels=[(3409.0, Direction.SHORT)], reclaim_held=True,
    )
    assert n.state is DayState.TRAP_REVERSAL
    assert n.direction is Direction.SHORT
    assert n.allowed_directions == (Direction.SHORT,)
    assert PB_SWEEP_RECLAIM in n.allowed_playbooks
    assert n.conviction < 0


def test_counter_trend_is_never_in_allowed_directions_on_a_trend_day():
    n = engine().narrate(trend_up_day(), asian=asian())
    assert Direction.SHORT not in n.allowed_directions


def test_undeveloped_day_is_not_tradeable():
    n = engine().narrate(flat_day(), asian=None)
    assert n.state in (DayState.OPENING, DayState.ASIAN_RANGE)
    assert not n.tradeable
    assert n.rearm_condition
