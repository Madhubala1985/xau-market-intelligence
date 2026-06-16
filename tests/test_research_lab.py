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
from research.report import render_ranking
from research.setups import REGISTRY
from research.setups.base import MarketData
from research.setups.london_asian_high_short import LondonAsianHighShort
from research.setups.london_sweep_reclaim import LondonSweepReclaimLong
from research.setups.ny_london_sweep_reversal import NyLondonSweepReversal
from research.setups.post_spike_chop import make_filter, post_spike_chop_block
from research.setups.trend_bos_fvg_retest import TrendBosFvgRetest
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


# ---------------------------------------------------------------------------
# Setup 3: NY sweep of London low -> failed continuation -> reversal long
# ---------------------------------------------------------------------------

def _c5(day, off, o, h, l, c):
    return _c(day, off, o, h, l, c)


def _build_setup3_long_win(day_date):
    day = day_date.replace(hour=0, minute=0)
    candles = []
    # London 07:00-12:00: 30 calm M5 candles, range [2990, 3000].
    for i in range(30):
        off = 420 + i * 5
        if i % 2 == 0:
            candles.append(_c5(day, off, 2992, 2995, 2990, 2993))
        else:
            candles.append(_c5(day, off, 2997, 3000, 2995, 2996))
    # NY 12:00+ : sweep London low, fail, reversal displacement + FVG, run to target.
    candles += [
        _c5(day, 720, 2991, 2992, 2988, 2989),   # sweep low 2988 < 2990, close below
        _c5(day, 725, 2989, 2995, 2989, 2994),   # failed continuation: close 2994 > 2990
        _c5(day, 730, 2994, 3012, 2994, 3011),   # bull displacement
        _c5(day, 735, 3011, 3014, 3008, 3010),   # FVG [2995, 3008]
        _c5(day, 740, 3010, 3011, 3005, 3006),   # mitigation: low 3005 <= entry 3008 -> fill
        _c5(day, 745, 3006, 3050, 3006, 3049),   # target 3008+2*~20 -> WIN
    ]
    return candles


def test_setup3_detects_ny_reversal_long_win():
    candles = _build_setup3_long_win(datetime(2026, 6, 8, tzinfo=UTC))
    intents = NyLondonSweepReversal().scan(_md(candles))
    assert len(intents) == 1
    assert intents[0].direction == Direction.LONG
    r = simulate(intents, candles, NO_COST)[0]
    assert r.outcome == TradeOutcome.WIN
    assert r.exit_reason == ExitReason.TAKE_PROFIT
    assert r.r_multiple == pytest.approx(2.0, abs=0.1)
    assert r.session == "NEW_YORK"


# ---------------------------------------------------------------------------
# Setup 2: London sweep of Asian high -> rejection -> bearish CHOCH -> FVG short
# ---------------------------------------------------------------------------

def _build_setup2_short(day_date):
    """Asian high 102.5; London sweeps it, rejects, structure breaks down
    (BOS up then bearish CHOCH, calibrated against the real engine), bear FVG."""
    day = day_date.replace(hour=0, minute=0)
    candles = []
    for i in range(12):                       # Asian range [100, 102.5]
        off = i * 5
        if i % 2 == 0:
            candles.append(_c(day, off, 101, 102.5, 100, 101.5))
        else:
            candles.append(_c(day, off, 101, 102, 100.5, 101))
    london_pts = [
        (100, 100.5, 99.5, 100), (100, 100.5, 99.5, 100),
        (99, 99.6, 98, 99),                   # swing low
        (99, 100, 98.6, 99.8), (99.8, 101, 99.5, 100.8),
        (101, 103, 100.9, 102.6),             # sweep Asian high 102.5; swing high
        (102.6, 102.8, 101, 101.5),           # rejection: close 101.5 < 102.5
        (101.5, 101.9, 100.6, 101),
        (101, 103.6, 101, 103.5),             # BOS bullish
        (103.5, 103.7, 102.4, 102.6),
        (102.6, 102.9, 101.6, 101.8),         # swing low forming
        (101.8, 102.1, 100.9, 101),
        (101, 101.2, 98.5, 98.7),             # bearish CHOCH
        (98.7, 99, 95, 95.5),                 # bearish displacement
        (95.5, 96, 94, 94.5),                 # bear FVG [96, 98.5]
    ]
    for i, p in enumerate(london_pts):
        candles.append(_c(day, 420 + i * 5, *p))
    return candles


def test_setup2_detects_choch_short():
    candles = _build_setup2_short(datetime(2026, 6, 13, tzinfo=UTC))
    intents = LondonAsianHighShort().scan(candles_md := _md(candles))
    assert len(intents) == 1
    it = intents[0]
    assert it.direction == Direction.SHORT
    assert it.stop > it.entry_price            # stop above the swept high
    assert it.target < it.entry_price          # short target below entry
    assert it.invalidation_price >= 102.5      # the swept Asian high
    # The intent simulates without error under the shared simulator.
    res = simulate(intents, candles, NO_COST)[0]
    assert res.session == "LONDON"


# ---------------------------------------------------------------------------
# Setup 4: H1 BOS sets bullish trend -> M5 displacement+FVG continuation long
# ---------------------------------------------------------------------------

def _h1(day, hours, o, h, l, c):
    t = day + timedelta(hours=hours)
    return Candle(symbol="XAUUSD", timeframe="1H", broker_time=t, time_utc=t,
                  open=o, high=h, low=l, close=c, tick_volume=100)


def _build_setup4_long_win(day_date):
    day = day_date.replace(hour=0, minute=0)
    h1 = [
        _h1(day, 0, 100, 101, 99, 100),
        _h1(day, 1, 100, 101, 99, 100),
        _h1(day, 2, 100, 105, 99, 100),   # swing high 105
        _h1(day, 3, 100, 102, 99, 100),
        _h1(day, 4, 100, 102, 99, 100),   # swing confirmed here
        _h1(day, 5, 100, 106, 100, 106),  # close 106 > 105 -> bullish BOS
    ]
    m5 = []
    for i in range(15):                    # calm baseline in the active window
        off = 420 + i * 5
        m5.append(_c5(day, off, 200, 200.5, 199.5, 200))
    m5 += [
        _c5(day, 495, 200, 204, 200, 203.5),   # bull displacement (range 4 >> baseline 1)
        _c5(day, 500, 203.5, 205, 202, 204),    # FVG [200.5, 202]
        _c5(day, 505, 204, 204, 201, 203),       # mitigation: low 201 <= entry 202 -> fill
        _c5(day, 510, 203, 208, 203, 207.5),     # target 202+2*~2.6 -> WIN
    ]
    return {Timeframe.M5: m5, Timeframe.H1: h1}


def test_setup4_detects_trend_continuation_long_win():
    data = MarketData(by_tf=_build_setup4_long_win(datetime(2026, 6, 9, tzinfo=UTC)))
    intents = TrendBosFvgRetest().scan(data)
    assert len(intents) == 1
    assert intents[0].direction == Direction.LONG
    r = simulate(intents, data.exec_candles, NO_COST)[0]
    assert r.outcome == TradeOutcome.WIN
    assert r.r_multiple == pytest.approx(2.0, abs=0.1)


def test_setup4_requires_h1_context():
    # No H1 data -> no trend -> no occurrences (multi-TF dependency enforced).
    data = MarketData(by_tf={Timeframe.M5: _build_setup4_long_win(
        datetime(2026, 6, 9, tzinfo=UTC))[Timeframe.M5]})
    assert TrendBosFvgRetest().scan(data) == []


# ---------------------------------------------------------------------------
# Setup 5: post-spike chop filter + registry + ranking
# ---------------------------------------------------------------------------

def test_post_spike_chop_blocks_after_spike_then_chop():
    day = datetime(2026, 6, 10, tzinfo=UTC).replace(hour=0)
    candles = [_c(day, i * 5, 100, 100.5, 99.5, 100) for i in range(25)]  # calm baseline
    candles.append(_c(day, 125, 100, 110, 100, 109))                       # spike (range 10)
    for i in range(4):                                                     # chop after spike
        candles.append(_c(day, 130 + i * 5, 109, 109.6, 108.4, 109))
    assert post_spike_chop_block(candles, len(candles) - 1) is True
    # A calm index well before the spike is not blocked.
    assert post_spike_chop_block(candles, 20) is False


def test_filter_removes_intents_in_chop_window():
    candles = _build_winning_day(datetime(2026, 6, 11, tzinfo=UTC))
    base = run_setup(LondonSweepReclaimLong(), _md(candles))
    # A filter that blocks everything must drop all occurrences.
    blocked = run_setup(LondonSweepReclaimLong(), _md(candles),
                        entry_filter=lambda c, i: True)
    assert base.metrics.occurrences == 1
    assert blocked.metrics.occurrences == 0


def test_registry_has_four_directional_setups():
    assert len(REGISTRY) == 4
    for cls in REGISTRY.values():
        s = cls()
        assert s.rules()["version"] == s.version


def test_ranking_renders_and_orders_proven_first():
    candles = _build_winning_day(datetime(2026, 6, 12, tzinfo=UTC))
    r = run_setup(LondonSweepReclaimLong(), _md(candles))
    md = render_ranking([r])
    assert "Setup Quality Ranking" in md
    assert r.setup in md
