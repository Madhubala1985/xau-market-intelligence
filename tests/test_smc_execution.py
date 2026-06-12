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


# -- D2 guards (decision 2026-06-12-01): stale anchors / counter-trend stand-down ----

def test_stale_anchor_cannot_qualify():
    """Live defect 2026-06-11: a SHORT at 4214 was anchored to a BOS from
    4078 — 135 USD below, structure the rally had invalidated hours
    earlier. An anchor whose level sits > 10x ATR(M5) from price is dead
    structure and must fail gate C with a reentry plan (no freeze)."""
    m5 = m5_breakdown(3.0)
    pipe = smc_pipeline(structure=structure_result(
        events=(bos_event(index=len(m5) - 1, price=3320.0),)  # ~59 away
    ))
    result = pipe.decide(pipeline_input(m5, m1=m1_with_local_swing()))
    assert not result.approved
    assert "SMC_ANCHOR_STALE" in result.reason
    smc = result.context.challenge
    assert smc["reentry_plan"], "stale anchor must leave a reentry plan"


def m5_rally(final_body, *, start=START):
    """44 rising candles, two drifts, then a big bullish displacement."""
    closes = [3340.0 + 0.5 * (i + 1) for i in range(44)]      # -> 3362.0
    closes += [3361.8, 3361.6]
    closes += [3361.6 + final_body]
    return make_candles(closes, start=start)


def conflicted_alignment():
    """The live 2026-06-11 signature: D1/H4 stale-bearish while the whole
    intraday stack is bullish; the candidate fell back to SHORT."""
    return MtfAlignment(
        d1=Bias.BEARISH, h4=Bias.BEARISH, h1=Bias.BULLISH,
        m15=Bias.BULLISH, m5=Bias.BULLISH,
        direction=Direction.SHORT, score=0.55, reason="stub conflict",
    )


def test_ltf_consensus_conflict_never_fades_with_the_stale_candidate():
    """With D3 (2026-06-12-02) the unanimous-LTF + displacement scenario
    flips the candidate to the trend direction BEFORE guard 2 is reached:
    the fresh bearish BOS can no longer be faded — the model hunts LONG
    setups instead (here none qualify, but the override is explicit).
    Guard 2 remains in the code as defense-in-depth."""
    m5 = m5_rally(3.0)
    pipe = smc_pipeline(
        structure=structure_result(events=(
            bos_event(index=len(m5) - 1, price=3364.0),  # FRESH bearish BOS
        )),
        mtf=conflicted_alignment(),
    )
    result = pipe.decide(pipeline_input(m5, m1=m1_with_local_swing()))
    assert not result.approved
    smc = result.context.challenge
    assert "TREND_DAY_OVERRIDE->LONG" in smc["htf_context"]
    assert smc["direction"] == "LONG"  # no bearish fade was considered


def test_fresh_sweep_reclaim_may_still_fade_a_trend(monkeypatch):
    """The stand-down must NOT block the one pattern designed to fade:
    a fresh sweep + displacement reclaim in the candidate direction."""
    m5 = m5_breakdown(3.0)
    pipe = smc_pipeline(
        sweeps=[true_sweep(index=len(m5) - 2, price=3382.4)],
        mtf=MtfAlignment(
            d1=Bias.BEARISH, h4=Bias.BEARISH, h1=Bias.BULLISH,
            m15=Bias.BULLISH, m5=Bias.BULLISH,
            direction=Direction.SHORT, score=0.55, reason="stub conflict",
        ),
    )
    result = pipe.decide(pipeline_input(m5, m1=m1_with_local_swing()))
    # the breakdown displacement is BEARISH here, so guard 2's
    # "displacement against the candidate" arm is not armed — the sweep
    # anchor qualifies exactly as before
    assert result.approved, result.reason
    assert result.context.challenge["smc_anchor"] == "SWEEP_DISPLACEMENT"


# -- D3 (decision 2026-06-12-02): trend-day consensus overrides a stale HTF veto -----

def m1_rising(entry_zone=3364.6, *, start=START):
    closes = [entry_zone + d for d in
              (-1.0, -0.6, -0.2, 0.2, -0.2, -0.6, 0.1, 0.8, 1.2, 1.6,
               1.8, 2.0)]
    return make_candles(closes, timeframe="M1", minutes=1,
                        start=start + timedelta(hours=3, minutes=43))


def test_trend_day_consensus_overrides_stale_htf_veto():
    """Live defect 2026-06-11: D1+H4 weights (0.55 bearish) kept the
    candidate SHORT all day against a unanimous bullish intraday stack on
    a +145 USD trend day — four fades, zero longs. With unanimous
    H1/M15/M5 + confirming displacement the consensus direction becomes
    the candidate; all other gates unchanged."""
    m5 = m5_rally(3.0)
    pipe = smc_pipeline(
        structure=structure_result(
            events=(bos_event(index=len(m5) - 1, price=3364.0,
                              bias=Bias.BULLISH),),
            final_bias=Bias.BULLISH,
        ),
        mtf=MtfAlignment(
            d1=Bias.BEARISH, h4=Bias.BEARISH, h1=Bias.BULLISH,
            m15=Bias.BULLISH, m5=Bias.BULLISH,
            direction=Direction.SHORT, score=0.55, reason="stale HTF veto",
        ),
    )
    result = pipe.decide(pipeline_input(m5, m1=m1_rising()))
    assert result.approved, result.reason
    assert result.decision.direction is Direction.LONG
    assert "TREND_DAY_OVERRIDE->LONG" in result.context.challenge["htf_context"]


def test_no_override_without_unanimous_ltf():
    """m5 disagreeing breaks unanimity: the candidate stays SHORT and the
    bullish-BOS anchor cannot exist for it -> no trade, no override."""
    m5 = m5_rally(3.0)
    pipe = smc_pipeline(
        structure=structure_result(
            events=(bos_event(index=len(m5) - 1, price=3364.0,
                              bias=Bias.BULLISH),),
        ),
        mtf=MtfAlignment(
            d1=Bias.BEARISH, h4=Bias.BEARISH, h1=Bias.BULLISH,
            m15=Bias.BULLISH, m5=Bias.BEARISH,
            direction=Direction.SHORT, score=0.55, reason="mixed",
        ),
    )
    result = pipe.decide(pipeline_input(m5, m1=m1_rising()))
    assert not result.approved
    assert "TREND_DAY_OVERRIDE" not in result.context.challenge["htf_context"]


def test_no_override_without_confirming_displacement():
    """A quiet drift (no displacement) never overrides the HTF direction."""
    m5 = m5_rally(0.2)  # tiny final body: displacement < 1.3x
    pipe = smc_pipeline(
        structure=structure_result(
            events=(bos_event(index=len(m5) - 1, price=3364.0,
                              bias=Bias.BULLISH),),
        ),
        mtf=MtfAlignment(
            d1=Bias.BEARISH, h4=Bias.BEARISH, h1=Bias.BULLISH,
            m15=Bias.BULLISH, m5=Bias.BULLISH,
            direction=Direction.SHORT, score=0.55, reason="stale HTF veto",
        ),
    )
    result = pipe.decide(pipeline_input(m5, m1=m1_rising()))
    assert "TREND_DAY_OVERRIDE" not in result.context.challenge["htf_context"]


# -- D5 (decision 2026-06-12-03): no drift fades against unanimous consensus ---------

def m5_drift_pullback(*, start=START):
    """A quiet upward drift with a small pullback rejection — the trade-4
    signature: no displacement footprint in either direction."""
    closes = [3340.0 + 0.35 * (i + 1) for i in range(44)]   # gentle rise
    closes += [3355.6, 3355.9, 3355.5]                      # small pullback
    return make_candles(closes, start=start)


def test_drift_fade_against_unanimous_consensus_is_refused():
    """Live defect 2026-06-11 (trade 4, -15.50): a SHORT off a fresh CHOCH
    in 0.87x drift against an all-bullish H1/M15/M5 stack. Fading a
    unanimous consensus now requires the candidate's own >= 1.3x
    displacement footprint."""
    m5 = m5_drift_pullback()
    pipe = smc_pipeline(
        structure=structure_result(events=(
            bos_event(index=len(m5) - 2, price=3355.0,
                      bias=Bias.BEARISH),  # fresh bearish CHOCH/BOS
        )),
        mtf=MtfAlignment(
            d1=Bias.BEARISH, h4=Bias.BEARISH, h1=Bias.BULLISH,
            m15=Bias.BULLISH, m5=Bias.BULLISH,
            direction=Direction.SHORT, score=0.55, reason="stale veto",
        ),
    )
    result = pipe.decide(pipeline_input(m5, m1=m1_with_local_swing(3355.5)))
    assert not result.approved
    assert "COUNTER_TREND_NO_DISPLACEMENT" in result.reason
    assert "footprint" in result.reason


# -- D6 market-state gate + H6b sweep freshness (decision 2026-06-12-04) -------------

def test_dangerous_volatility_environment_blocks_entries():
    """A monster candle in the ENVIRONMENT (not the signal candle) makes
    conditions untradeable regardless of anchors."""
    closes = [3400.0 - 0.5 * (i + 1) for i in range(40)]
    closes += [3360.0]   # ~19-point spike = last ENVIRONMENT candle
    closes += [3360.5]   # current (signal) candle, excluded from the env
    m5 = make_candles(closes)
    pipe = smc_pipeline(zones=[bearish_zone(ZoneKind.FAIR_VALUE_GAP,
                                            bottom=3360.8, top=3362.0)])
    result = pipe.decide(pipeline_input(m5, m1=m1_with_local_swing(3360.5)))
    assert not result.approved
    assert "VOLATILITY_BLOCK" in result.reason
    assert "vol=" in result.context.challenge["market_state"]


def test_structureless_chop_blocks_entries():
    """Flat, driftless closes are consolidation: CHOP_BLOCK fires before
    any anchor can qualify (7 of 9 live losses were chop probes)."""
    closes = [3380.0 + (0.08 if i % 2 else -0.08) for i in range(46)]
    m5 = make_candles(closes)
    pipe = smc_pipeline(zones=[bearish_zone(ZoneKind.FAIR_VALUE_GAP,
                                            bottom=3379.8, top=3380.6)])
    result = pipe.decide(pipeline_input(m5, m1=m1_with_local_swing(3380.0)))
    assert not result.approved
    assert "CHOP_BLOCK" in result.reason


def test_sweep_freshness_uses_rejection_extreme_not_swept_level():
    """H6b: a sweep of a FAR level whose rejection happened AT price must
    pass the staleness guard (trade 11 anchored 47 USD away pre-fix)."""
    m5 = m5_breakdown(3.0)
    far_sweep = SimpleNamespace(
        status=SweepStatus.TRUE_SWEEP, rejection_bias=Bias.BEARISH,
        sweep_index=len(m5) - 2,                      # rejection candle near price
        level=SimpleNamespace(price=3450.0),          # swept level 70 away
        swept_side=SimpleNamespace(value="BUY_SIDE"),
    )
    pipe = smc_pipeline(sweeps=[far_sweep])
    result = pipe.decide(pipeline_input(m5, m1=m1_with_local_swing()))
    assert result.approved, result.reason
    smc = result.context.challenge
    assert smc["smc_anchor"] == "SWEEP_DISPLACEMENT"
    assert "rejected @" in result.decision.thesis or "rejected @" in smc["reason"]


# -- H8: zone consumption after an SL loss (decision 2026-06-12-07) ------------
# Live evidence 2026-06-12: trade 18 stopped at 4211.60 and trade 19 re-faded
# the same zone 3 minutes later with a stop at 4211.65 — both lost (-34.90).
# Winners 8 and 17 placed their stops well BEYOND the prior violated level
# and must stay allowed; far-away prior losses (trade 6) are out of scope.

def _approved_short(pipe):
    result = pipe.decide(pipeline_input(m5_breakdown(3.0),
                                        m1=m1_with_local_swing()))
    assert result.approved, result.reason
    return result


def test_sl_loss_consumes_the_zone():
    pipe = smc_pipeline(zones=[bearish_zone(ZoneKind.FAIR_VALUE_GAP)])
    first = _approved_short(pipe)
    pipe.note_stop_loss(Direction.SHORT, first.decision.stop_loss,
                        first.decision.time_utc)
    again = pipe.decide(pipeline_input(m5_breakdown(3.0),
                                       m1=m1_with_local_swing()))
    assert not again.approved
    assert "ZONE_CONSUMED" in again.reason
    smc = again.context.challenge
    assert smc["waiting_for"] == "LOCAL_SWING"
    assert smc["reentry_plan"]


def test_reentry_clearing_the_consumed_level_is_allowed():
    pipe = smc_pipeline(zones=[bearish_zone(ZoneKind.FAIR_VALUE_GAP)])
    first = _approved_short(pipe)
    # the violated level sits 6 USD below the new stop: cleared (trade 17/8)
    pipe.note_stop_loss(Direction.SHORT, first.decision.stop_loss - 6.0,
                        first.decision.time_utc)
    again = pipe.decide(pipeline_input(m5_breakdown(3.0),
                                       m1=m1_with_local_swing()))
    assert again.approved, again.reason


def test_consumed_level_expires_after_ttl():
    pipe = smc_pipeline(zones=[bearish_zone(ZoneKind.FAIR_VALUE_GAP)])
    first = _approved_short(pipe)
    pipe.note_stop_loss(Direction.SHORT, first.decision.stop_loss,
                        first.decision.time_utc - timedelta(minutes=31))
    again = pipe.decide(pipeline_input(m5_breakdown(3.0),
                                       m1=m1_with_local_swing()))
    assert again.approved, again.reason


def test_distant_consumed_level_is_out_of_scope():
    # trade-6 analogue: the prior loss was ~20 USD away — D6 territory,
    # not zone consumption.
    pipe = smc_pipeline(zones=[bearish_zone(ZoneKind.FAIR_VALUE_GAP)])
    first = _approved_short(pipe)
    pipe.note_stop_loss(Direction.SHORT, first.decision.stop_loss + 20.0,
                        first.decision.time_utc)
    again = pipe.decide(pipeline_input(m5_breakdown(3.0),
                                       m1=m1_with_local_swing()))
    assert again.approved, again.reason


def test_opposite_direction_loss_does_not_consume():
    pipe = smc_pipeline(zones=[bearish_zone(ZoneKind.FAIR_VALUE_GAP)])
    first = _approved_short(pipe)
    pipe.note_stop_loss(Direction.LONG, first.decision.stop_loss,
                        first.decision.time_utc)
    again = pipe.decide(pipeline_input(m5_breakdown(3.0),
                                       m1=m1_with_local_swing()))
    assert again.approved, again.reason


def test_high_atr_cannot_make_clearing_unreachable():
    """Decision 2026-06-12-09 (live evidence, ATR 10.75 spike day): the
    clearance is capped inside the 8-USD proximity, so a stop materially
    BEYOND the violated level (deeper structure) always has an escape."""
    pipe = smc_pipeline()
    t = datetime(2026, 6, 12, 15, 45, tzinfo=timezone.utc)
    pipe.note_stop_loss(Direction.LONG, 4214.86, t)
    # 7.16 beyond the violated level, inside proximity, spike ATR:
    assert pipe._consumed_stop_block(
        Direction.LONG, 4207.70, 10.75, t + timedelta(minutes=5)
    ) == ""
    # the churn case stays blocked at any ATR:
    assert "ZONE_CONSUMED" in pipe._consumed_stop_block(
        Direction.LONG, 4214.40, 10.75, t + timedelta(minutes=5)
    )
