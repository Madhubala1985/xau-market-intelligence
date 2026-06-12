"""Tests for the head-to-head decision replay engine (SMC-V2-001).

Deterministic stub pipelines + constructed candles prove the fill model:
- entry at the NEXT candle open with adverse spread+slippage,
- SL-first on a candle that touches both stop and target,
- break-even armed at +1R exactly like the live chassis,
- SL losses at the original stop notify note_stop_loss; BE exits do not,
- R accounting, day breakdown, and the shipping verdict.
"""

from datetime import datetime, timedelta, timezone

from src.backtest.decision_replay import (
    SLIPPAGE,
    DecisionReplay,
    ReplayResult,
    ReplayTrade,
    verdict,
)
from src.data.enums import Direction
from src.strategy.pipeline import PipelineResult, PipelineStage
from tests.test_demo_challenge import make_candles
from tests.test_smc_accounting import approved_smc

START = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)


class OneShotPipeline:
    """Approves exactly one SHORT at a chosen step; never again."""

    def __init__(self, at_index, entry, stop, target):
        self.at = at_index
        self.entry, self.stop, self.target = entry, stop, target
        self.fired = False
        self.noted = []

    def note_stop_loss(self, direction, stop, when):
        self.noted.append((direction, stop, when))

    def decide(self, inp):
        i = len(inp.exec_candles)
        if not self.fired and inp.now is not None and \
                inp.trades_today == 0 and self._step(inp):
            self.fired = True
            result = approved_smc("replay-1")
            d = result.decision.model_copy(update={
                "entry_price": self.entry, "stop_loss": self.stop,
                "take_profits": (self.target,),
            })
            return PipelineResult(
                stage=PipelineStage.RISK_EVALUATED, approved=True,
                reason="stub", decision=d,
            )
        _ = i
        return PipelineResult(stage=PipelineStage.HYPOTHESIS,
                              approved=False, reason="no")

    def _step(self, inp):
        return inp.exec_candles[-1].time_utc >= \
            START + timedelta(minutes=5 * self.at)


def flat_then(path, n_flat=70, base=2315.0):
    closes = [base + (0.05 if i % 2 else -0.05) for i in range(n_flat)]
    closes += path
    return make_candles(closes, start=START, wick=0.1)


def run_one(path, *, entry=2315.0, stop=2317.5, target=2310.0, at=70):
    m5 = flat_then(path)
    pipe = OneShotPipeline(at, entry, stop, target)
    res = DecisionReplay(m5, warmup=60, spread=0.2).run({"x": pipe})["x"]
    return res, pipe


def test_entry_fills_next_open_with_adverse_costs():
    res, _ = run_one([2315.0, 2314.0, 2313.0, 2312.0, 2311.0, 2309.5])
    assert len(res.trades) == 1
    t = res.trades[0]
    # SHORT fill = next open - (spread + slippage)
    assert t.entry < 2315.1
    assert t.direction is Direction.SHORT


def test_stop_first_when_candle_touches_both():
    # one candle spikes through BOTH stop and target -> LOSS (conservative)
    res, pipe = run_one([2315.0, 2330.0])  # huge candle: low/high cover both
    closed = res.closed
    assert len(closed) == 1
    assert closed[0].outcome == "LOSS"
    assert closed[0].r_multiple <= -1.0
    assert pipe.noted, "original-stop loss must notify note_stop_loss"


def test_win_reaches_target():
    res, pipe = run_one([2314.5, 2313.5, 2312.0, 2311.0, 2309.0])
    closed = res.closed
    assert len(closed) == 1
    assert closed[0].outcome == "WIN"
    assert closed[0].r_multiple > 1.0
    assert not pipe.noted


def test_breakeven_armed_at_1r_and_tagged():
    # decision on the last flat candle (at=69): entry ~2314.55, stop
    # 2317.5 -> risk ~2.95, 1R ~2311.6; the path touches 1R (low 2311.4),
    # then comes back up through the BE stop -> BREAKEVEN
    res, pipe = run_one([2313.5, 2311.5, 2313.0, 2316.0], at=69)
    closed = res.closed
    assert len(closed) == 1
    assert closed[0].outcome == "BREAKEVEN"
    assert abs(closed[0].r_multiple) < 0.25
    assert not pipe.noted, "a BE exit must not consume a zone"


def test_r_accounting_and_day_breakdown():
    res, _ = run_one([2314.5, 2313.0, 2312.0, 2311.0, 2309.0])
    s = res.summary()
    assert s["trades"] == 1 and s["wins"] == 1
    assert s["net_r"] == res.closed[0].r_multiple
    assert len(s["by_day"]) == 1


def test_verdict_gate():
    day = datetime(2026, 6, 1, tzinfo=timezone.utc).date()
    day2 = datetime(2026, 6, 2, tzinfo=timezone.utc).date()

    def trade(r, d=day):
        return ReplayTrade(
            day=d, direction=Direction.SHORT, entry_time=None,
            entry=0, stop=1, target=-2, setup="s",
            outcome="WIN" if r > 0 else "LOSS", r_multiple=r,
        )

    v1 = ReplayResult("v1", [trade(2.0), trade(-1.0), trade(-1.0)])
    v2 = ReplayResult("v2", [trade(2.0), trade(1.5, day2)])
    out = verdict(v1, v2)
    assert out["ship"] is True

    # edge destruction: v1 won the day big, v2 lost it
    v2_bad = ReplayResult("v2", [trade(-1.0)])
    out2 = verdict(v1, v2_bad)
    assert out2["ship"] is False
