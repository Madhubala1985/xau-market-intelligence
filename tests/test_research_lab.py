"""End-to-end test of the research lab on synthetic candles.

Proves the pipeline works WITHOUT MT5 or stored data:
  - the Setup-1 detector arms on a hand-built sweep->reclaim->displacement->FVG,
  - the forward simulator scores a known WIN and a known LOSS correctly,
  - causality holds (no fill before the arm bar; invalidation cancels),
  - metrics + classification behave (tiny sample => Insufficient Data).
"""

from datetime import datetime, timedelta, timezone

import pytest

from research.harness import CostModel, run_setup, simulate
from research.metrics import (
    Classification,
    ExitReason,
    TradeResult,
    classify,
    compute_metrics,
)
from research.setups.base import MarketData
from research.setups.london_sweep_reclaim import LondonSweepReclaimLong
from src.data.enums import Direction, Timeframe, TradeOutcome
from src.data.schemas import Candle

UTC = timezone.utc
NO_COST = CostModel(spread=0.0, slippage=0.0, label="none")


def _c(day: datetime, minute_offset: int, o, h, l, c) -> Candle:
    t = day + timedelta(minutes=minute_offset)
    return Candle(
        symbol="XAUUSD", timeframe="5M", broker_time=t, time_utc=t,
        open=o, high=h, low=l, close=c, tick_volume=100,
    )


def _asian_block(day: datetime, low: float, high: float) -> list[Candle]:
    """12 calm Asian M5 candles (00:00-07:00 has plenty of room; we use 00:00+)."""
    out = []
    mid = (low + high) / 2
    for i in range(14):
        # alternate touching the low and high so range == high-low
        lo = low if i % 2 == 0 else mid
        hi = high if i % 2 == 1 else mid
        out.append(_c(day, i * 5, mid, hi, lo, mid))
    return out


def _build_winning_day(day_date: datetime):
    """Asian range [1990,2000]; London sweeps to 1988, reclaims, displaces up,
    leaves an FVG, mitigates, then runs to target (a 2R win)."""
    day = day_date.replace(hour=0, minute=0)
    candles = _asian_block(day, 1990.0, 2000.0)
    london = day.replace(hour=7)  # 07:00 UTC == minute offset 420

    def L(off, o, h, l, c):
        return _c(london, off, o, h, l, c)

    seq = [
        L(0, 1991, 1992, 1988, 1989),     # sweep: low 1988 < asian low 1990
        L(5, 1989, 1995, 1989, 1994),     # reclaim: close 1994 > 1990
        # displacement candle (idx d): big bullish range vs ~baseline
        L(10, 1994, 2010, 1994, 2009),    # range 16 >> baseline
        L(15, 2009, 2012, 2006, 2008),    # d+1: low 2006 > d-1.high(1995) -> FVG [1995,2006]
        L(20, 2008, 2009, 1996, 1997),    # retrace into FVG top 2006 -> FILL @2006
        L(25, 1997, 2025, 1997, 2024),    # rip up: target = 2006 + 2*(2006-1987.9)=~2042? see note
    ]
    # Note: stop = sweep_low(1988) - 0.10 = 1987.90; risk = 2006-1987.90 = 18.10;
    # target = 2006 + 2*18.10 = 2042.20. Add a candle that reaches it.
    seq.append(L(30, 2024, 2045, 2024, 2044))  # hits target 2042.20 -> WIN +2R
    return candles + seq


def _build_losing_day(day_date: datetime):
    """Same structure but after filling the FVG, price falls to the stop (a -1R loss)."""
    day = day_date.replace(hour=0, minute=0)
    candles = _asian_block(day, 1990.0, 2000.0)
    london = day.replace(hour=7)

    def L(off, o, h, l, c):
        return _c(london, off, o, h, l, c)

    seq = [
        L(0, 1991, 1992, 1988, 1989),
        L(5, 1989, 1995, 1989, 1994),
        L(10, 1994, 2010, 1994, 2009),
        L(15, 2009, 2012, 2006, 2008),    # FVG [1995, 2006]
        L(20, 2008, 2009, 1996, 1997),    # fill @2006
        L(25, 1997, 1998, 1985, 1986),    # falls through stop 1987.90 -> LOSS -1R
    ]
    return candles + seq


def _md(candles):
    return MarketData(by_tf={Timeframe.M5: candles})


def test_winning_day_detects_and_scores_2r():
    candles = _build_winning_day(datetime(2026, 6, 1, tzinfo=UTC))
    setup = LondonSweepReclaimLong()
    intents = setup.scan(_md(candles))
    assert len(intents) == 1
    intent = intents[0]
    assert intent.direction == Direction.LONG
    # arm only references past data: fill must occur strictly after arm.
    results = simulate(intents, candles, NO_COST)
    r = results[0]
    assert r.outcome == TradeOutcome.WIN
    assert r.exit_reason == ExitReason.TAKE_PROFIT
    assert r.r_multiple == pytest.approx(2.0, abs=0.05)
    assert r.entry_time > intent.arm_time


def test_losing_day_scores_minus_1r():
    candles = _build_losing_day(datetime(2026, 6, 2, tzinfo=UTC))
    setup = LondonSweepReclaimLong()
    results = simulate(setup.scan(_md(candles)), candles, NO_COST)
    assert len(results) == 1
    r = results[0]
    assert r.outcome == TradeOutcome.LOSS
    assert r.exit_reason == ExitReason.STOP_LOSS
    assert r.r_multiple == pytest.approx(-1.0, abs=0.05)


def test_no_setup_when_asian_low_never_swept():
    """If London never trades below the Asian low, there is no occurrence."""
    day = datetime(2026, 6, 3, tzinfo=UTC).replace(hour=0)
    candles = _asian_block(day, 1990.0, 2000.0)
    london = day.replace(hour=7)
    for i in range(6):
        t = i * 5
        candles.append(_c(london, t, 1996, 1999, 1995, 1998))  # stays inside range
    assert LondonSweepReclaimLong().scan(_md(candles)) == []


def test_costs_reduce_r():
    candles = _build_winning_day(datetime(2026, 6, 4, tzinfo=UTC))
    intents = LondonSweepReclaimLong().scan(_md(candles))
    free = simulate(intents, candles, NO_COST)[0].r_multiple
    costed = simulate(intents, candles, CostModel(0.5, 0.5))[0].r_multiple
    assert costed < free  # adverse costs shrink realized R


def test_classification_insufficient_then_no_edge():
    # tiny sample -> Insufficient Data regardless of how good it looks
    good = [
        TradeResult("s", "v1", datetime(2026, 6, 1, tzinfo=UTC), Direction.LONG,
                    "LONDON", datetime(2026, 6, 1, tzinfo=UTC), 2000.0, 1990.0,
                    2020.0, datetime(2026, 6, 1, tzinfo=UTC), 2020.0, 2.0,
                    TradeOutcome.WIN, ExitReason.TAKE_PROFIT)
        for _ in range(10)
    ]
    assert classify(compute_metrics(good)) == Classification.INSUFFICIENT_DATA

    # 120 trades, net negative -> No Edge
    losers = [
        TradeResult("s", "v1", datetime(2026, 6, 1, tzinfo=UTC), Direction.LONG,
                    "LONDON", datetime(2026, 6, 1, tzinfo=UTC), 2000.0, 1990.0,
                    2020.0, datetime(2026, 6, 1, tzinfo=UTC), 1990.0, -1.0,
                    TradeOutcome.LOSS, ExitReason.STOP_LOSS)
        for _ in range(120)
    ]
    assert classify(compute_metrics(losers)) == Classification.NO_EDGE


def test_run_setup_end_to_end_smoke():
    candles = _build_winning_day(datetime(2026, 6, 5, tzinfo=UTC))
    result = run_setup(LondonSweepReclaimLong(), _md(candles))
    assert result.metrics.occurrences == 1
    assert result.classification == Classification.INSUFFICIENT_DATA  # n=1
    assert len(result.sensitivity) == 4  # default cost grid
    assert "LONDON" in result.by_session
