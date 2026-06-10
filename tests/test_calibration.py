"""Tests for the threshold-calibration replay (BACKTEST-001 readiness)."""

from datetime import datetime, timedelta, timezone

from src.backtest.calibration import (
    DEFAULT_VARIANTS,
    ThresholdCalibrator,
    ThresholdVariant,
)
from src.data.schemas import Candle

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)


def candle(i, o, h, l, c):
    t = T0 + i * timedelta(minutes=5)
    return Candle(symbol="XAUUSD", timeframe="5M", broker_time=t, time_utc=t,
                  open=o, high=h, low=l, close=c, tick_volume=100)


def wavy_series(n):
    """A drifting series with pullbacks: produces structure + some setups."""
    out = []
    px = 2400.0
    for i in range(n):
        wave = 3.0 if (i // 24) % 2 == 0 else -2.0
        step = wave / 24
        out.append(candle(i, px, px + abs(step) + 0.4, px - abs(step) - 0.4,
                          px + step))
        px += step
    return out


def test_report_compares_variants_and_serializes():
    calibrator = ThresholdCalibrator(window=120, step=24, horizon=24,
                                     min_trades=1)
    report = calibrator.run(wavy_series(600), DEFAULT_VARIANTS)
    assert len(report.results) == len(DEFAULT_VARIANTS)
    for r in report.results:
        assert r.windows > 0
        assert r.approved >= 0
        assert 0.0 <= r.win_rate <= 1.0
    payload = report.to_dict()
    assert payload["task"] == "BACKTEST-001-READINESS"
    assert "never mutated" in payload["note"]


def test_insufficient_history_is_honest():
    report = ThresholdCalibrator().run(wavy_series(50))
    assert report.results == ()
    assert report.recommended is None
    assert "insufficient history" in report.detail


def test_recommendation_requires_minimum_trades():
    calibrator = ThresholdCalibrator(window=120, step=48, horizon=24,
                                     min_trades=10_000)  # unreachable
    report = calibrator.run(wavy_series(600))
    assert report.recommended is None
    assert "collect more history" in report.detail


def test_replay_never_mutates_live_thresholds():
    from src.strategy.pipeline import DecisionPipeline

    live = DecisionPipeline()
    before = (live._chop_override_confluence, live._continuation_confluence,
              live._continuation_displacement)
    ThresholdCalibrator(window=120, step=48, horizon=24).run(
        wavy_series(400),
        [ThresholdVariant("x", 0.10, 0.10, 0.5)],
    )
    after = (live._chop_override_confluence, live._continuation_confluence,
             live._continuation_displacement)
    assert before == after  # variants run in their OWN pipelines only
