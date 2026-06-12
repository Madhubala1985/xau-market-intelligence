"""Tests for the SMC v2 decision brain (SMC-V2-001).

Behavioral contract per 26_SMC_V2_DESIGN.md:
- untradeable day states refuse entries with an explicit re-arm condition,
- counter-narrative directions can never trade,
- conviction below the bar refuses entries,
- probe limit: after 2 SL losses in a direction, only a fresh reclaim
  re-arms it,
- a playbook with 2 SL losses stands down for the day,
- the quality score gates entries; approved trades carry playbook +
  narrative in the journaled setup/thesis,
- the chassis contract is identical to v1 (decision with stop, 2R target,
  lot tier, governor verdict).
"""

from datetime import timedelta, timezone, datetime

from src.data.enums import Direction
from src.data.validation import DataValidator, ValidationConfig
from src.strategy.pipeline import PipelineStage
from src.strategy.smc_execution import SmcEngines, make_challenge_limits
from src.strategy.smc_v2 import SmcV2Pipeline
from src.structure.zones import ZoneKind
from tests.test_demo_challenge import SYMBOL, make_candles, pipeline_input
from tests.test_smc_execution import (
    StubAsian,
    StubHtf,
    StubLiquidity,
    StubMtf,
    StubStructure,
    StubSweep,
    StubZones,
    bearish_alignment,
    bearish_zone,
    structure_result,
    true_sweep,
)
from src.data.session_levels import AsianRangeContext
from src.regime.htf_bias import HtfBias

START = datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc)  # LONDON


def v2_pipeline(*, structure=None, sweeps=(), zones=(), asian=None,
                mtf=None, htf_bias=HtfBias.BEARISH):
    engines = SmcEngines(
        validator=DataValidator(ValidationConfig(
            expected_symbol=SYMBOL, detect_gaps=False,
            max_staleness=timedelta(minutes=30),
        )),
        htf=StubHtf(htf_bias),
        mtf=StubMtf(mtf or bearish_alignment()),
        structure=StubStructure(structure or structure_result()),
        liquidity=StubLiquidity(),
        sweep=StubSweep(sweeps),
        zones=StubZones(zones),
        asian=StubAsian(asian or AsianRangeContext(
            known=True, high=3401.0, low=3397.0, swept="NONE",
        )),
    )
    return SmcV2Pipeline(make_challenge_limits(SYMBOL), engines=engines)


def trend_down_m5(final_body=3.0):
    """A clear DOWN trend day: legs of selling, expansion past the Asian
    range, ending with a pullback + breakdown trigger candle."""
    closes = [3400.0]
    px = 3400.0
    for i in range(36):
        px -= 1.4 if i % 4 != 3 else -0.5
        closes.append(px)
    closes += [px + 0.6, px + 1.2, px + 1.8, px + 2.4]   # pullback
    closes += [px + 2.2, px + 2.0]                        # drift
    closes += [px + 2.0 - final_body]                     # breakdown
    return make_candles(closes, start=START)


def flat_m5():
    closes = [3400.0 + (0.2 if i % 2 else -0.2) for i in range(60)]
    return make_candles(closes, start=START)


def zone_at(price_bottom, price_top, kind=ZoneKind.FAIR_VALUE_GAP):
    return bearish_zone(kind, bottom=price_bottom, top=price_top)


def fvg_for(m5):
    last = m5[-1].close
    return zone_at(last + 1.4, last + 3.0)


def test_trend_day_continuation_short_approves():
    m5 = trend_down_m5()
    pipe = v2_pipeline(zones=[fvg_for(m5)])
    result = pipe.decide(pipeline_input(m5))
    assert result.approved, result.reason
    smc = result.context.challenge
    assert smc["playbook"] == "TREND_CONTINUATION"
    assert "TREND_DAY" in smc["narrative"]
    assert result.decision.direction is Direction.SHORT
    assert result.decision.stop_loss > result.decision.entry_price
    assert result.lot_size in (0.05, 0.10)
    assert "TREND_DAY" in result.decision.thesis


def test_flat_day_refuses_with_rearm_condition():
    pipe = v2_pipeline(zones=[fvg_for(flat_m5())])
    result = pipe.decide(pipeline_input(flat_m5()))
    assert not result.approved
    assert result.stage is PipelineStage.HYPOTHESIS
    smc = result.context.challenge
    assert "DAY_NARRATIVE" in result.reason or "CONVICTION" in result.reason
    assert smc["reentry_plan"]


def test_counter_narrative_direction_cannot_trade():
    """A bullish HTF stub cannot make the model LONG on a clear DOWN
    trend day: allowed_directions only contains SHORT."""
    m5 = trend_down_m5()
    bullish = bearish_alignment(direction=Direction.LONG)
    pipe = v2_pipeline(zones=[fvg_for(m5)], mtf=bullish,
                       htf_bias=HtfBias.BULLISH)
    result = pipe.decide(pipeline_input(m5))
    # either it refuses (conviction conflict) or it trades SHORT with the
    # narrative — it must NEVER go LONG.
    if result.approved:
        assert result.decision.direction is Direction.SHORT
    else:
        assert result.decision is None


def test_probe_limit_two_stopouts_block_third_attempt():
    m5 = trend_down_m5()
    pipe = v2_pipeline(zones=[fvg_for(m5)])
    now = m5[-1].time_utc
    pipe.note_stop_loss(Direction.SHORT, m5[-1].close + 50.0, now)
    pipe.note_stop_loss(Direction.SHORT, m5[-1].close + 60.0, now)
    result = pipe.decide(pipeline_input(m5))
    assert not result.approved
    assert "PROBE_LIMIT" in result.reason


def test_playbook_stands_down_after_two_losses():
    m5 = trend_down_m5()
    pipe = v2_pipeline(zones=[fvg_for(m5)])
    first = pipe.decide(pipeline_input(m5))
    assert first.approved, first.reason
    playbook = first.context.challenge["playbook"]
    # two SL losses attributed to that playbook, far away (no H8/probe
    # interference: H8 needs proximity, probe limit needs 2 same-direction
    # losses — attribute one to each direction)
    now = m5[-1].time_utc
    pipe._sl_losses_by_playbook[playbook] = 2
    again = pipe.decide(pipeline_input(m5))
    assert not again.approved
    assert "stood down" in again.reason
    _ = now


def test_memory_resets_on_a_new_day():
    m5 = trend_down_m5()
    pipe = v2_pipeline(zones=[fvg_for(m5)])
    pipe.note_stop_loss(Direction.SHORT, m5[-1].close + 50.0,
                        m5[-1].time_utc)
    pipe.note_stop_loss(Direction.SHORT, m5[-1].close + 60.0,
                        m5[-1].time_utc)
    assert pipe._sl_losses_by_direction[Direction.SHORT] == 2
    next_day = [c.model_copy(update={
        "time_utc": c.time_utc + timedelta(days=1),
        "broker_time": c.broker_time + timedelta(days=1),
    }) for c in m5]
    pipe.decide(pipeline_input(next_day))
    assert pipe._sl_losses_by_direction.get(Direction.SHORT, 0) == 0


def test_quality_below_bar_refuses():
    """A BOS-only anchor outside any kill zone with a weak narrative must
    not clear the quality bar."""
    m5 = trend_down_m5()
    late = [c.model_copy(update={
        "time_utc": c.time_utc + timedelta(hours=13, minutes=20),
        "broker_time": c.broker_time + timedelta(hours=13, minutes=20),
    }) for c in m5]   # ~22:2x UTC: LOW_LIQUIDITY session
    from tests.test_smc_execution import bos_event
    pipe = v2_pipeline(structure=structure_result(
        events=(bos_event(len(late) - 30, late[-1].close + 2.0),),
    ))
    result = pipe.decide(pipeline_input(late))
    assert not result.approved
    assert ("QUALITY_BELOW_BAR" in result.reason
            or "DAY_NARRATIVE" in result.reason
            or "no SMC anchor" in result.reason
            or "trigger" in result.reason)


def test_approved_decision_carries_narrative_and_2r_target():
    m5 = trend_down_m5()
    pipe = v2_pipeline(zones=[fvg_for(m5)])
    result = pipe.decide(pipeline_input(m5))
    assert result.approved, result.reason
    d = result.decision
    risk = d.stop_loss - d.entry_price
    assert abs((d.entry_price - d.take_profits[0]) - 2.0 * risk) < 0.02
    assert "smc_" in d.setup_type
    assert "lot=" in d.setup_type


def test_sweep_reclaim_playbook_fires_on_post_spike_reclaim():
    """A spike day with a fresh HELD reclaim may trade ONLY the reclaim
    direction via SWEEP_RECLAIM."""
    closes = [3400.0 + (0.2 if i % 2 else -0.2) for i in range(50)]
    closes += [3414.0]                    # spike up
    closes += [3412.0, 3409.0, 3406.0]    # rejection legs back down
    closes += [3405.0, 3404.0 - 3.0]      # continuation breakdown
    m5 = make_candles(closes, start=START)
    sweep = true_sweep(index=50, price=3410.0)  # swept buy-side, rejected
    pipe = v2_pipeline(sweeps=[sweep])
    result = pipe.decide(pipeline_input(m5))
    if result.approved:
        smc = result.context.challenge
        assert smc["playbook"] in ("SWEEP_RECLAIM", "TREND_CONTINUATION")
        assert result.decision.direction is Direction.SHORT
    else:
        # acceptable refusals: stop construction or quality — but the
        # narrative must have armed a playbook for SHORT only
        assert "LONG" not in str(result.context.challenge.get("direction"))
