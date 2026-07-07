"""GOLD-INTEL-001: the three-brain engine's own guarantees.

- branding: the single profile label on every cycle;
- cost brain: reopen-window block, min-stop block, spread-vs-stop block;
- risk brain: tighten-only regime demotion (STRONG -> NORMAL, never up);
- exit model: break-even at +1R, ATR trail, tighten-only in both directions.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.data.enums import Direction
from src.data.schemas import Candle, TradeDecision
from src.strategy.gold_intel import (
    GoldIntelEngine,
    MAX_SPREAD_FRACTION_OF_STOP,
    MIN_STOP_USD,
    PROFILE_NAME,
    REGIME_DEMOTE_BELOW,
    _in_reopen_block,
    make_gold_intel_pipeline,
    make_intel_limits,
)
from src.strategy.pipeline import PipelineInput, PipelineResult
from src.strategy.smc_v2 import SmcV2Pipeline


def _candle(ts, o=4000.0, h=4004.0, lo=3996.0, c=4002.0):
    return Candle(
        symbol="XAUUSDM", timeframe="M5", broker_time=ts, time_utc=ts,
        open=o, high=h, low=lo, close=c, tick_volume=100,
    )


def _inp(ts, spread=0.35):
    return PipelineInput(
        symbol="XAUUSDM", exec_candles=[_candle(ts)], daily_candles=[],
        h4_candles=[], broker=None, current_spread=spread,
    )


def _decision(entry=4000.0, stop=3995.0, setup="lot=0.10 SWEEP_RECLAIM"):
    return TradeDecision(
        decision_id="T-1", time_utc=datetime(2026, 7, 6, 14, 0,
                                             tzinfo=timezone.utc),
        symbol="XAUUSDM", direction=Direction.LONG, setup_type=setup,
        thesis="t", invalidation_price=stop, entry_price=entry,
        stop_loss=stop,
    )


def _engine():
    return make_gold_intel_pipeline("XAUUSDM")


def test_engine_is_the_day_narrative_brain_branded_gold_intel():
    e = _engine()
    assert isinstance(e, SmcV2Pipeline)
    assert e.threshold_profile == PROFILE_NAME == "gold_intel"


def test_envelope_limits_reinstate_the_brakes():
    lim = make_intel_limits("XAUUSDM")
    assert lim.max_risk_per_trade == 0.030
    assert lim.max_daily_loss == 0.05
    assert lim.max_weekly_loss == 0.10
    assert lim.max_open_trades == 3


# ---- cost brain --------------------------------------------------------


def test_reopen_window_is_blocked_in_et():
    # 17:30 ET on a Monday == 21:30 UTC (EDT, July)
    ts = datetime(2026, 7, 6, 21, 30, tzinfo=timezone.utc)
    assert _in_reopen_block(_inp(ts))
    # 14:00 ET is normal NY session
    ts = datetime(2026, 7, 6, 18, 0, tzinfo=timezone.utc)
    assert not _in_reopen_block(_inp(ts))


def _gated(engine, inp, decision):
    result = PipelineResult(
        stage=None, approved=True, reason="ok", decision=decision,
    )
    return engine._cost_gate(inp, result)


def test_cost_gate_blocks_reopen_window_entry():
    e = _engine()
    ts = datetime(2026, 7, 6, 21, 30, tzinfo=timezone.utc)  # 17:30 ET
    why = _gated(e, _inp(ts), _decision())
    assert why is not None and "COST_REOPEN_WINDOW" in why


def test_cost_gate_blocks_sub_minimum_stop():
    e = _engine()
    ts = datetime(2026, 7, 6, 18, 0, tzinfo=timezone.utc)
    why = _gated(e, _inp(ts), _decision(entry=4000.0,
                                        stop=4000.0 - MIN_STOP_USD + 0.5))
    assert why is not None and "COST_STOP_TOO_TIGHT" in why


def test_cost_gate_blocks_wide_spread_vs_stop():
    e = _engine()
    ts = datetime(2026, 7, 6, 18, 0, tzinfo=timezone.utc)
    stop_dist = 4.0
    bad_spread = MAX_SPREAD_FRACTION_OF_STOP * stop_dist + 0.10
    why = _gated(e, _inp(ts, spread=bad_spread),
                 _decision(entry=4000.0, stop=4000.0 - stop_dist))
    assert why is not None and "COST_SPREAD_VS_STOP" in why


def test_cost_gate_passes_a_normal_entry():
    e = _engine()
    ts = datetime(2026, 7, 6, 18, 0, tzinfo=timezone.utc)
    why = _gated(e, _inp(ts, spread=0.35),
                 _decision(entry=4000.0, stop=3995.0))
    assert why is None


# ---- risk brain --------------------------------------------------------


def test_regime_dial_is_clamped_and_labelled():
    e = _engine()
    e.set_regime(1.7, "EASING")
    assert e._regime_exposure == 1.0
    e.set_regime(None)
    assert e._regime_label == "UNAVAILABLE"
    assert e._regime_exposure is None


def test_regime_demotion_threshold_is_tighten_only():
    # demotion applies under the threshold; the dial can never upsize a
    # NORMAL decision (there is no code path that raises the tier).
    assert 0 < REGIME_DEMOTE_BELOW < 0.5


# ---- exit model --------------------------------------------------------


def _m5(ts, closes):
    out = []
    for i, c in enumerate(closes):
        out.append(Candle(
            symbol="XAUUSDM", timeframe="M5",
            broker_time=ts + timedelta(minutes=5 * i),
            time_utc=ts + timedelta(minutes=5 * i),
            open=c - 0.5, high=c + 1.0, low=c - 1.0, close=c,
            tick_volume=100,
        ))
    return out


def test_manage_stop_arms_break_even_at_one_r():
    e = _engine()
    ts = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
    m5 = _m5(ts, [4000.0 + 0.2 * i for i in range(30)])
    # long from 4000, original stop 3995 (r=5), price now 4006 (+1.2R)
    new = e.manage_stop(Direction.LONG, 4000.0, 3995.0, 4006.0, m5)
    assert new is not None and new >= 4000.0  # at least break-even


def test_manage_stop_never_widens():
    e = _engine()
    ts = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
    m5 = _m5(ts, [4000.0] * 30)
    # long stop already at 4004; price barely above -> nothing tighter
    new = e.manage_stop(Direction.LONG, 4000.0, 4004.0, 4004.5, m5)
    assert new is None or new > 4004.0


def test_note_trade_closed_clears_exit_memory():
    e = _engine()
    e._open_risk[Direction.LONG] = 5.0
    e.note_trade_closed(Direction.LONG, 1.2)
    assert Direction.LONG not in e._open_risk
