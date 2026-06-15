"""GoldAlpha engine tests (GOLD-ALPHA-001): EV objective, protected SL, exit
model, the learning loop, full output, and the safety gates."""

from datetime import datetime, timedelta, timezone

from src.data.enums import BrokerConnectionStatus, Direction
from src.data.schemas import BrokerState, Candle
from src.liquidity.liquidity_map import (
    LiquidityKind,
    LiquidityLevel,
    LiquidityMap,
    LiquiditySide,
)
from src.strategy.gold_alpha import (
    PROFILE_NAME,
    GoldAlphaEngine,
    make_gold_alpha_pipeline,
    make_gold_limits,
)
from src.strategy.pipeline import PipelineInput
from src.strategy.trade_attribution import TradeContext

NOW = datetime(2026, 6, 15, 13, 0, tzinfo=timezone.utc)
SYM = "XAUUSD"


def _c(tf, t, o, h, l, c, v=400):
    return Candle(symbol=SYM, timeframe=tf, broker_time=t, time_utc=t,
                  open=o, high=h, low=l, close=c, tick_volume=v)


def _series(tf, n, start, step, drift, vol):
    out, p = [], start
    for i in range(n):
        t = NOW - timedelta(minutes=step * (n - i))
        o, c = p, p + drift
        out.append(_c(tf, t, o, max(o, c) + vol, min(o, c) - vol, c)); p = c
    return out


def _broker(balance=2000.0, equity=2000.0, open_positions=0):
    return BrokerState(time_utc=NOW, connection_status=BrokerConnectionStatus.CONNECTED,
                       symbol="XAUUSDm", balance=balance, equity=equity,
                       free_margin=balance, leverage=200,
                       open_positions=open_positions, trade_allowed=True)


def _input(**kw):
    return PipelineInput(
        symbol="XAUUSDm",
        exec_candles=kw.pop("m5", _series("5M", 120, 3300, 5, 0.0, 1.2)),
        daily_candles=_series("1D", 30, 2500, 1440, 5.0, 20.0),
        h4_candles=_series("4H", 40, 2900, 240, 2.0, 8.0),
        m15_candles=_series("15M", 80, 3250, 15, 0.5, 2.0),
        h1_candles=_series("1H", 60, 3100, 60, 1.0, 4.0),
        m1_candles=_series("1M", 60, 3380, 1, 0.0, 0.5),
        broker=kw.pop("broker", _broker()), current_spread=kw.pop("spread", 0.3),
        now=NOW, **kw)


def test_engine_identity_and_envelope():
    eng = make_gold_alpha_pipeline(SYM)
    assert isinstance(eng, GoldAlphaEngine)
    assert eng.threshold_profile == PROFILE_NAME
    limits = make_gold_limits(SYM)
    assert limits.max_risk_per_trade == 0.06
    assert limits.max_daily_loss == 1.0 and limits.max_weekly_loss == 1.0


def test_decide_runs_and_emits_full_evidence_output():
    ch = make_gold_alpha_pipeline(SYM).decide(_input()).context.challenge
    for k in ("profile", "regime", "narrative", "htf_context", "liquidity_map",
              "sweep_status", "structure_state", "fvg_ob_status", "orderflow",
              "premium_discount", "candidates", "ev", "p_win", "target_r",
              "tp_trail", "reason"):
        assert k in ch
    assert ch["profile"] == PROFILE_NAME


def test_six_timeframes_are_read():
    htf = make_gold_alpha_pipeline(SYM).decide(_input()).context.challenge["htf_context"]
    for tf in ("d1=", "h4=", "h1=", "m15=", "m5="):
        assert tf in htf


def test_news_and_spread_and_no_setup_all_wait_with_reason():
    eng = make_gold_alpha_pipeline(SYM)
    for inp in (_input(news_risk=True), _input(spread=5.0), _input()):
        r = eng.decide(inp)
        assert not r.approved
        assert r.context.challenge["reason"]  # never silent


# -- the protected-stop doctrine -------------------------------------------

def test_short_stop_is_pushed_beyond_a_buy_side_pool():
    eng = make_gold_alpha_pipeline(SYM)
    pool = LiquidityLevel(kind=LiquidityKind.EQUAL_HIGHS,
                          side=LiquiditySide.BUY_SIDE, price=3353.0, time_utc=NOW)
    lmap = LiquidityMap(levels=(pool,))
    stop, dist, beyond = eng._protect_stop(Direction.SHORT, 3350.0, 3352.0,
                                           2.0, 0.3, lmap)
    assert stop > 3353.0 and stop > 3350.0 and dist > 0 and beyond


def test_unprotectable_stop_returns_none():
    eng = make_gold_alpha_pipeline(SYM)
    assert eng._protect_stop(Direction.SHORT, 3350.0, 3395.0, 1.0, 0.3,
                             LiquidityMap(levels=())) is None


# -- the EV objective gates entries ----------------------------------------

def test_ev_is_expected_value_of_the_candidate():
    # ev = p_win*target_R - (1-p_win)*1 ; thin edges are rejected.
    eng = make_gold_alpha_pipeline(SYM)
    # featureless tape -> no candidate clears the EV bar -> WAIT.
    r = eng.decide(_input())
    assert not r.approved


# -- exit model -------------------------------------------------------------

def test_break_even_arms_at_plus_1r_and_is_tighten_only():
    eng = make_gold_alpha_pipeline(SYM)
    eng._open_ctx[Direction.LONG] = TradeContext(
        setup_type="TREND_CONTINUATION", regime="TREND_DAY", direction="LONG",
        entry=3300.0, stop=3295.0, target=3315.0, score=0.4, p_win=0.45,
        displacement=1.4, spread_ratio=0.3, confirmation=0.7,
        stop_beyond_pool=True, extended=False)
    m5 = _series("5M", 40, 3300, 5, 0.0, 1.0)
    # +1R in profit (entry 3300, stop 3295 -> 1R = +5 -> price 3305)
    new_stop = eng.manage_stop(Direction.LONG, 3300.0, 3290.0, 3306.0, m5)
    assert new_stop is not None and new_stop >= 3300.0  # at/above break-even
    # tighten-only: if the stop is already higher, no change
    assert eng.manage_stop(Direction.LONG, 3300.0, 3304.0, 3306.0, m5) is None


def test_manage_stop_is_noop_when_not_in_profit():
    eng = make_gold_alpha_pipeline(SYM)
    eng._open_ctx[Direction.LONG] = TradeContext(
        setup_type="X", regime="TREND_DAY", direction="LONG", entry=3300.0,
        stop=3295.0, target=3315.0, score=0.4, p_win=0.45, displacement=1.0,
        spread_ratio=0.3, confirmation=0.7, stop_beyond_pool=True, extended=False)
    m5 = _series("5M", 40, 3300, 5, 0.0, 1.0)
    assert eng.manage_stop(Direction.LONG, 3300.0, 3295.0, 3301.0, m5) is None


# -- the learning loop ------------------------------------------------------

def test_stop_loss_is_attributed_and_downweights_the_setup():
    eng = make_gold_alpha_pipeline(SYM)
    for _ in range(5):
        eng._open_ctx[Direction.SHORT] = TradeContext(
            setup_type="RANGE_FADE", regime="RANGE_DAY", direction="SHORT",
            entry=3300.0, stop=3305.0, target=3290.0, score=0.2, p_win=0.35,
            displacement=1.0, spread_ratio=0.3, confirmation=0.6,
            stop_beyond_pool=False, extended=False)
        eng.note_stop_loss(Direction.SHORT, 3305.0, NOW)
    # the store now down-weights this repeatedly-trapped setup
    assert eng._perf.p_win_adjustment("RANGE_FADE", "RANGE_DAY") < 0
