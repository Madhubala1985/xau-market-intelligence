"""Tests for the institutional SMC execution pipeline (SMC-EXECUTION-001).

Proves the A+B+C+D gate model:
- M1/M5 momentum alone (no SMC anchor) can NEVER trade (SMC_ANCHOR_MISSING),
- a trade requires HTF context + session/liquidity context + SMC anchor +
  executable local trigger,
- FVG retest / OB retest / sweep+displacement / break-retest / BOS anchors
  can each qualify a trade,
- kill-zone and liquidity context are evaluated and reported,
- an Asian sweep enables trading outside kill zones; low liquidity with no
  liquidity event waits,
- a too-wide stop produces a RE-ENTRY PLAN (waiting_for=...), never the old
  endless STOP_TOO_WIDE_FOR_ACCOUNT block,
- every new candle refreshes the fresh-entry scan,
- the tactical stop is structurally justified (stop_logic /
  invalidation_reason / risk_if_sl_hit reported).

Engines are injected as stubs so each gate condition is exact and
deterministic; the live path uses the real institutional engines.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.data.enums import Direction
from src.data.session_levels import AsianRangeContext
from src.data.validation import DataValidator, ValidationConfig
from src.regime.htf_bias import HtfBias
from src.strategy.confluence import MtfAlignment
from src.strategy.pipeline import PipelineStage
from src.strategy.smc_execution import (
    LOT_NORMAL,
    LOT_STRONG,
    SmcEngines,
    SmcExecutionPipeline,
    make_challenge_limits,
)
from src.structure.market_structure import Bias, StructureEventType
from src.structure.zones import Zone, ZoneKind
from src.liquidity.sweep import SweepStatus
from tests.test_demo_challenge import SYMBOL, make_candles, pipeline_input

START = datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc)        # -> LONDON
LATE = datetime(2026, 6, 11, 18, 20, tzinfo=timezone.utc)       # -> 22:10 LOW_LIQ


# -- engine stubs ---------------------------------------------------------------

class StubStructure:
    def __init__(self, result):
        self._result = result

    def analyze(self, candles):
        return self._result


class StubLiquidity:
    def build(self, candles):
        return SimpleNamespace(levels=[], buy_side=lambda: [],
                               sell_side=lambda: [])


class StubSweep:
    def __init__(self, sweeps=()):
        self._sweeps = list(sweeps)

    def detect(self, candles, liquidity_map):
        return list(self._sweeps)


class StubZones:
    def __init__(self, zones=()):
        self._zones = list(zones)

    def build(self, candles):
        return list(self._zones)


class StubAsian:
    def __init__(self, ctx):
        self._ctx = ctx

    def analyze(self, candles, now):
        return self._ctx


class StubMtf:
    def __init__(self, alignment):
        self._alignment = alignment

    def align(self, **kwargs):
        return self._alignment


class StubHtf:
    def __init__(self, bias):
        self._bias = bias

    def classify(self, daily, h4):
        return SimpleNamespace(bias=self._bias)


def bearish_alignment(score=0.85, direction=Direction.SHORT):
    return MtfAlignment(
        d1=Bias.BEARISH, h4=Bias.BEARISH, h1=Bias.BEARISH,
        m15=Bias.BEARISH, m5=Bias.BEARISH,
        direction=direction, score=score, reason="stub",
    )


def no_direction_alignment():
    return MtfAlignment(
        d1=None, h4=None, h1=Bias.NEUTRAL, m15=Bias.NEUTRAL, m5=None,
        direction=None, score=0.0, reason="stub: no direction",
    )


def structure_result(events=(), final_bias=Bias.BEARISH):
    return SimpleNamespace(swings=(), events=tuple(events),
                           final_bias=final_bias)


def bos_event(index, price, bias=Bias.BEARISH):
    return SimpleNamespace(event_type=StructureEventType.BOS, bias=bias,
                           index=index, price=price)


def bearish_zone(kind, *, bottom=3381.0, top=3382.7):
    return Zone(kind=kind, bias=Bias.BEARISH, top=top, bottom=bottom,
                origin_index=30, created_index=32, created_time=START,
                mitigated=False)


def true_sweep(index=43, price=3382.4):
    return SimpleNamespace(
        status=SweepStatus.TRUE_SWEEP, rejection_bias=Bias.BEARISH,
        sweep_index=index, level=SimpleNamespace(price=price),
        swept_side=SimpleNamespace(value="BUY_SIDE"),
    )


def smc_pipeline(*, structure=None, sweeps=(), zones=(), asian=None,
                 mtf=None, htf_bias=HtfBias.NEUTRAL):
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
        asian=StubAsian(asian or AsianRangeContext(known=True, swept="NONE")),
    )
    return SmcExecutionPipeline(make_challenge_limits(SYMBOL),
                                engines=engines)


# -- candle scenarios -------------------------------------------------------------

def m5_breakdown(final_body, *, start=START):
    """40 declining candles, a 4-candle pullback (into a supply zone), two
    small drifts, then a breakdown candle with the given body."""
    closes = [3400.0 - 0.5 * (i + 1) for i in range(40)]        # -> 3380.0
    closes += [3380.6, 3381.2, 3381.8, 3382.4]                  # pullback
    closes += [3382.2, 3382.0]                                  # drift
    closes += [3382.0 - final_body]                             # breakdown
    return make_candles(closes, start=start)


def m1_with_local_swing(entry_zone=3381.0, *, start=START):
    closes = [entry_zone + d for d in
              (1.0, 0.6, 0.2, -0.2, 0.2, 0.6, -0.1, -0.8, -1.2, -1.6,
               -1.8, -2.0)]
    return make_candles(closes, timeframe="M1", minutes=1,
                        start=start + timedelta(hours=3, minutes=43))


# -- the core rule: momentum alone cannot trade --------------------------------------

def test_m1_m5_momentum_alone_cannot_trade():
    # Strong bearish momentum, breakdown candle, aligned HTF — but ZERO SMC
    # anchors (no sweep, no zones, no structure events): NO trade.
    pipe = smc_pipeline(structure=structure_result(events=()))
    result = pipe.decide(pipeline_input(m5_breakdown(3.0),
                                        m1=m1_with_local_swing()))
    assert not result.approved
    assert result.stage is PipelineStage.HYPOTHESIS
    assert "SMC_ANCHOR_MISSING" in result.reason
    assert "momentum alone does not trade" in result.reason
    smc = result.context.challenge
    assert smc["smc_anchor"] == "NONE"
    assert smc["waiting_for"] in ("SWEEP", "FVG_RETEST", "OB_RETEST",
                                  "BREAK_RETEST", "LOCAL_SWING")


# -- anchors that DO qualify ----------------------------------------------------------

def test_fvg_retest_anchor_qualifies_a_trade():
    pipe = smc_pipeline(zones=[bearish_zone(ZoneKind.FAIR_VALUE_GAP)])
    result = pipe.decide(pipeline_input(m5_breakdown(3.0),
                                        m1=m1_with_local_swing()))
    assert result.approved, result.reason
    smc = result.context.challenge
    assert smc["smc_anchor"] == "FVG_RETEST"
    assert smc["entry_trigger"] == "MITIGATION_REJECTION"
    assert smc["killzone"] == "LONDON"
    assert smc["tactical_stop_source"] in (
        "local_swing", "FVG_boundary", "rejection_wick",
    )
    # the stop is structurally justified and fully explained
    assert smc["stop_logic"]
    assert smc["invalidation_reason"]
    assert smc["risk_if_sl_hit"] is not None and smc["risk_if_sl_hit"] > 0
    distance = result.decision.stop_loss - result.decision.entry_price
    assert 0 < distance <= 8.0
    assert result.lot_size in (LOT_NORMAL, LOT_STRONG)
    assert "lot=" in result.decision.setup_type


def test_ob_retest_anchor_qualifies():
    pipe = smc_pipeline(zones=[bearish_zone(ZoneKind.ORDER_BLOCK)])
    result = pipe.decide(pipeline_input(m5_breakdown(3.0),
                                        m1=m1_with_local_swing()))
    assert result.approved, result.reason
    assert result.context.challenge["smc_anchor"] == "OB_RETEST"


def test_sweep_displacement_anchor_qualifies():
    pipe = smc_pipeline(sweeps=[true_sweep()])
    result = pipe.decide(pipeline_input(m5_breakdown(3.0),
                                        m1=m1_with_local_swing()))
    assert result.approved, result.reason
    smc = result.context.challenge
    assert smc["smc_anchor"] == "SWEEP_DISPLACEMENT"
    assert smc["liquidity_context"] == "SESSION_LIQUIDITY"


def test_bos_anchor_qualifies():
    m5 = m5_breakdown(3.0)
    pipe = smc_pipeline(structure=structure_result(
        events=(bos_event(index=len(m5) - 1, price=3381.0),)
    ))
    result = pipe.decide(pipeline_input(m5, m1=m1_with_local_swing()))
    assert result.approved, result.reason
    assert result.context.challenge["smc_anchor"] == "BOS"
    assert result.context.challenge["entry_trigger"] == "CONTINUATION"


def test_break_and_retest_anchor_qualifies():
    m5 = m5_breakdown(3.0)
    # BOS happened earlier; price pulled back to the broken level and the
    # last candle closed back below it.
    pipe = smc_pipeline(structure=structure_result(
        events=(bos_event(index=len(m5) - 4, price=3381.0),)
    ))
    result = pipe.decide(pipeline_input(m5, m1=m1_with_local_swing()))
    assert result.approved, result.reason
    assert result.context.challenge["smc_anchor"] == "BREAK_RETEST"
    assert result.context.challenge["entry_trigger"] == "BREAK_RETEST"


def test_strong_grade_uses_010_in_killzone():
    pipe = smc_pipeline(zones=[bearish_zone(ZoneKind.FAIR_VALUE_GAP)])
    result = pipe.decide(pipeline_input(m5_breakdown(3.0),
                                        m1=m1_with_local_swing()))
    assert result.approved
    # LONDON kill zone + FVG anchor + 3x displacement + mtf 0.85 => STRONG
    assert result.context.challenge["grade"] == "STRONG"
    assert result.lot_size == LOT_STRONG


# -- gate A and B refusals --------------------------------------------------------

def test_no_htf_direction_waits():
    pipe = smc_pipeline(mtf=no_direction_alignment(),
                        htf_bias=HtfBias.NEUTRAL,
                        zones=[bearish_zone(ZoneKind.FAIR_VALUE_GAP)])
    result = pipe.decide(pipeline_input(m5_breakdown(3.0)))
    assert not result.approved
    assert "waiting for higher-timeframe direction" in result.reason
    assert result.context.challenge["waiting_for"] == "HTF_DIRECTION"


def test_outside_killzone_without_liquidity_event_waits():
    m5 = m5_breakdown(3.0, start=LATE)  # last candle ~22:10 UTC
    pipe = smc_pipeline(zones=[bearish_zone(ZoneKind.FAIR_VALUE_GAP)])
    result = pipe.decide(pipeline_input(m5))
    assert not result.approved
    assert "outside kill zones" in result.reason
    smc = result.context.challenge
    assert "LOW_LIQUIDITY" in smc["killzone"]
    assert smc["liquidity_context"] == "NONE"
    assert smc["waiting_for"] == "SWEEP"


def test_asian_sweep_enables_trading_outside_killzones():
    m5 = m5_breakdown(3.0, start=LATE)
    pipe = smc_pipeline(
        zones=[bearish_zone(ZoneKind.FAIR_VALUE_GAP)],
        asian=AsianRangeContext(known=True, swept="LOW", high=3402.0,
                                low=3380.0),
    )
    result = pipe.decide(pipeline_input(
        m5, m1=m1_with_local_swing(start=LATE),
    ))
    assert result.approved, result.reason
    smc = result.context.challenge
    assert smc["liquidity_context"] == "ASIAN_LOW_SWEEP"
    # outside a kill zone the grade stays NORMAL -> 0.05
    assert result.lot_size == LOT_NORMAL


# -- gate D / stop refusals produce re-entry plans, never silence -------------------

def test_anchor_without_local_trigger_waits_with_plan():
    closes = [3400.0 - 0.5 * (i + 1) for i in range(40)]
    closes += [3380.4]  # last candle closes UP: no executable SHORT trigger
    m5 = make_candles(closes)
    pipe = smc_pipeline(structure=structure_result(
        events=(bos_event(index=len(m5) - 1, price=3381.0),)
    ))
    result = pipe.decide(pipeline_input(m5))
    assert not result.approved
    assert "no executable local trigger" in result.reason
    smc = result.context.challenge
    assert smc["smc_anchor"] == "BOS"
    assert smc["entry_trigger"] == "NONE"
    assert smc["waiting_for"]
    assert smc["reentry_plan"]


def test_stop_too_wide_creates_reentry_plan_not_silent_block():
    # Vertical collapse: valid anchor + trigger but NO local invalidation
    # within the tactical ceiling. The answer is a re-entry plan that
    # refreshes next candle — never STOP_TOO_WIDE_FOR_ACCOUNT for hours.
    closes = [3400.0 - 0.5 * (i + 1) for i in range(40)]
    closes += [3380.0 - 7.0]
    m5 = make_candles(closes)
    pipe = smc_pipeline(structure=structure_result(
        events=(bos_event(index=len(m5) - 1, price=3381.0),)
    ))
    result = pipe.decide(pipeline_input(m5))
    assert not result.approved
    assert "re-entry plan armed" in result.reason
    assert "never used" in result.reason
    assert "STOP_TOO_WIDE_FOR_ACCOUNT" not in result.reason
    smc = result.context.challenge
    assert smc["waiting_for"]
    assert smc["fresh_entry_scan"] == "ACTIVE"


def test_every_new_candle_refreshes_the_scan():
    pipe = smc_pipeline(zones=[bearish_zone(ZoneKind.FAIR_VALUE_GAP)])
    m5 = m5_breakdown(3.0)
    first = pipe.decide(pipeline_input(m5, m1=m1_with_local_swing()))
    assert first.context.challenge["new_candle_detected"] == "first_cycle"
    extended = m5 + make_candles(
        [m5[-1].close - 0.4], start=m5[-1].time_utc + timedelta(minutes=5),
    )
    second = pipe.decide(pipeline_input(extended, m1=m1_with_local_swing()))
    assert second.context.challenge["new_candle_detected"] == "yes"
    assert second.context.challenge["fresh_entry_scan"] == "ACTIVE"


def test_htf_context_killzone_and_liquidity_are_always_reported():
    pipe = smc_pipeline(structure=structure_result(events=()))
    result = pipe.decide(pipeline_input(m5_breakdown(3.0)))
    smc = result.context.challenge
    assert "mtf_score=0.85" in smc["htf_context"]
    assert "d1=BEARISH" in smc["htf_context"]
    assert smc["killzone"] == "LONDON"
    assert "liquidity_context" in smc and "smc_anchor" in smc
