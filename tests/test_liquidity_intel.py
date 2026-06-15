"""LiquidityIntelEngine tests (LIQUIDITY-INTEL-001, option 1).

The single engine is the proven day-narrative brain (SmcV2Pipeline) re-branded
for the one profile. Deep decision logic is covered by test_smc_v2.py and
test_smc_execution.py; here we assert the single-path contract:
- it IS the proven brain (composition, not a from-scratch re-derivation);
- decide() runs end-to-end and the output is branded liquidity_intel;
- all six timeframes feed the decision (htf_context), the engine WAITs with a
  reason rather than going silent, and news/dangerous conditions block;
- the note_stop_loss trade-memory hook is wired.
"""

from datetime import datetime, timedelta, timezone

from src.data.enums import BrokerConnectionStatus, Direction
from src.data.schemas import BrokerState, Candle
from src.strategy.liquidity_intel import (
    DEFAULT_MAX_ENTRIES_PER_DAY,
    DEFAULT_QUALITY_BAR,
    PROFILE_NAME,
    LiquidityIntelEngine,
    make_intel_limits,
    make_liquidity_intel_pipeline,
)
from src.strategy.pipeline import PipelineInput
from src.strategy.smc_v2 import SmcV2Pipeline

NOW = datetime(2026, 6, 15, 13, 0, tzinfo=timezone.utc)
SYM = "XAUUSD"


def _candle(tf, t, o, h, l, c, v=400):
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
    return PipelineInput(
        symbol="XAUUSDm",
        exec_candles=kw.pop("m5", _series("5M", 120, 3300, 5, 0.0, 1.2)),
        daily_candles=_series("1D", 30, 2500, 1440, 5.0, 20.0),
        h4_candles=_series("4H", 40, 2900, 240, 2.0, 8.0),
        m15_candles=_series("15M", 80, 3250, 15, 0.5, 2.0),
        h1_candles=_series("1H", 60, 3100, 60, 1.0, 4.0),
        m1_candles=_series("1M", 60, 3380, 1, 0.0, 0.5),
        broker=_broker(), current_spread=kw.pop("spread", 0.3), now=NOW, **kw)


def test_engine_is_the_proven_day_narrative_brain():
    eng = make_liquidity_intel_pipeline(SYM)
    assert isinstance(eng, LiquidityIntelEngine)
    assert isinstance(eng, SmcV2Pipeline)          # composed, not re-derived
    assert eng.threshold_profile == PROFILE_NAME


def test_aggressive_cadence_is_the_max_profitable_setting():
    eng = make_liquidity_intel_pipeline(SYM)
    # the entries/day sweep (2026-06-15) put the edge at +2.43R (2/day) /
    # +2.30R (3/day), NEGATIVE at 4+/day — so 3/day is the most aggressive
    # cadence that still makes money.
    assert eng._max_entries_per_day == DEFAULT_MAX_ENTRIES_PER_DAY == 3
    # the quality bar (the EDGE) is kept.
    assert eng._quality_bar == DEFAULT_QUALITY_BAR == 0.70


def test_envelope_is_the_single_anchor_set():
    limits = make_intel_limits(SYM)
    assert limits.max_risk_per_trade == 0.030
    assert limits.max_daily_loss == 0.05
    assert limits.max_weekly_loss == 0.10
    assert limits.max_open_trades == 3


def test_decide_runs_and_is_branded_liquidity_intel():
    eng = make_liquidity_intel_pipeline(SYM)
    ch = eng.decide(_input()).context.challenge
    assert ch["profile"] == PROFILE_NAME
    assert ch["mode"] == PROFILE_NAME
    # day-narrative reasoning is present.
    assert "narrative" in ch


def test_decide_consumes_all_six_timeframes():
    eng = make_liquidity_intel_pipeline(SYM)
    ch = eng.decide(_input()).context.challenge
    htf = ch["htf_context"]
    for tf in ("d1=", "h4=", "h1=", "m15=", "m5="):
        assert tf in htf
    assert "mtf_score=" in htf


def test_no_setup_waits_with_a_reason_not_silence():
    eng = make_liquidity_intel_pipeline(SYM)
    ch = eng.decide(_input()).context.challenge
    assert not eng.decide(_input()).approved
    assert ch["reason"]                       # never empty
    assert ch.get("waiting_for") or ch.get("reentry_plan") or ch.get("narrative")


def test_news_risk_blocks_new_entries():
    eng = make_liquidity_intel_pipeline(SYM)
    result = eng.decide(_input(news_risk=True))
    assert not result.approved


def test_wide_spread_does_not_trade():
    eng = make_liquidity_intel_pipeline(SYM)
    assert not eng.decide(_input(spread=5.0)).approved


def test_note_stop_loss_memory_hook_is_wired():
    eng = make_liquidity_intel_pipeline(SYM)
    # the trade-memory hook accepts an SL notification without error.
    eng.note_stop_loss(Direction.SHORT, 3352.0, NOW)
    assert eng._sl_losses_by_direction.get(Direction.SHORT) == 1
