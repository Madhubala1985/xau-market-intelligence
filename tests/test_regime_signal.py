"""Tests for the gold macro regime risk dial (research/regime.py)."""

from research.regime import gold_macro_regime


def _rising(n=80):
    return [100.0 + i * 0.1 for i in range(n)]


def _falling(n=80):
    return [100.0 - i * 0.1 for i in range(n)]


def test_tightening_when_both_rising():
    r = gold_macro_regime(_rising(), _rising())
    assert r.label == "TIGHTENING"
    assert r.exposure == 0.0            # all lookbacks agree -> de-risk fully
    assert r.tightening_votes == 3


def test_easing_when_both_falling():
    r = gold_macro_regime(_falling(), _falling())
    assert r.label == "EASING"
    assert r.exposure == 1.0            # full exposure in the supportive regime


def test_mixed_when_diverging():
    r = gold_macro_regime(_rising(), _falling())
    assert r.label == "MIXED"
    assert r.exposure == 1.0            # no tightening votes


def test_exposure_scales_with_partial_tightening():
    # yields rising on all lookbacks, dollar rising only recently (short lookback)
    ry = _rising()
    dx = [100.0 - i * 0.1 for i in range(60)] + [94.0 + i * 0.5 for i in range(20)]
    r = gold_macro_regime(ry, dx, lookbacks=(20, 40, 60))
    assert 0.0 <= r.exposure <= 1.0
    assert r.tightening_votes >= 1      # at least the short lookback flags tightening
