"""Tests for the honest macro interface (INTELLIGENCE-002): no fake data."""

from datetime import datetime, timezone

import pytest

from src.orderflow.macro_context import (
    MacroContext,
    MacroSignal,
    NullMacroProvider,
)


def test_null_provider_never_fabricates_availability():
    ctx = NullMacroProvider().assess(datetime.now(timezone.utc))
    assert ctx.any_available is False
    for signal in (ctx.dxy, ctx.us_yields, ctx.gold_futures):
        assert signal.available is False
        assert signal.bias == "UNAVAILABLE"
    assert "UNAVAILABLE" in ctx.summary()
    assert "never faked" in ctx.summary()


def test_unavailable_signal_cannot_carry_a_bias():
    with pytest.raises(ValueError, match="no faking"):
        MacroSignal(available=False, bias="BULLISH_GOLD")


def test_available_signal_must_carry_a_bias():
    with pytest.raises(ValueError):
        MacroSignal(available=True, bias="UNAVAILABLE")
    ok = MacroSignal(available=True, bias="BEARISH_GOLD", detail="test feed")
    assert MacroContext(dxy=ok).any_available is True

# ---------------------------------------------------------------------------
# FINAL-INTELLIGENCE: file provider + gold pressure + confluence influence
# ---------------------------------------------------------------------------

import json
from datetime import timedelta

from src.orderflow.macro_context import FileMacroProvider, gold_pressure

NOW = datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc)


def write_macro(tmp_path, *, age_hours=1.0, dxy="RISING", us10y="RISING",
                futures="BEARISH", max_age=12):
    path = tmp_path / "macro_context.json"
    path.write_text(json.dumps({
        "as_of_utc": (NOW - timedelta(hours=age_hours)).isoformat(),
        "max_age_hours": max_age,
        "dxy": dxy, "us10y": us10y, "gold_futures": futures,
    }), encoding="utf-8")
    return path


def test_fresh_operator_file_provides_macro_and_futures(tmp_path):
    ctx = FileMacroProvider(write_macro(tmp_path)).assess(NOW)
    assert ctx.any_available is True
    pressure, why = gold_pressure(ctx)
    assert pressure == "BEARISH_GOLD"
    assert "rising" in why.lower()
    assert ctx.gold_futures.bias == "BEARISH_GOLD"


def test_stale_or_missing_file_is_unavailable_never_guessed(tmp_path):
    stale = FileMacroProvider(write_macro(tmp_path, age_hours=20)).assess(NOW)
    assert stale.any_available is False
    missing = FileMacroProvider(tmp_path / "nope.json").assess(NOW)
    assert missing.any_available is False
    assert gold_pressure(missing)[0] == "UNAVAILABLE"


def test_mixed_macro_reads_neutral(tmp_path):
    ctx = FileMacroProvider(
        write_macro(tmp_path, dxy="RISING", us10y="FALLING")
    ).assess(NOW)
    assert gold_pressure(ctx)[0] == "NEUTRAL"


def test_macro_and_futures_influence_confluence_not_trigger(tmp_path):
    """Macro/futures shade the confluence score; they cannot create a
    candidate direction by themselves."""
    from tests.test_confluence import assess

    bearish_ctx = FileMacroProvider(write_macro(tmp_path)).assess(NOW)
    bullish_ctx = FileMacroProvider(
        write_macro(tmp_path, dxy="FALLING", us10y="FALLING",
                    futures="BULLISH")
    ).assess(NOW)
    agree = assess(macro=bearish_ctx)       # SHORT candidate + bearish macro
    conflict = assess(macro=bullish_ctx)
    neutral = assess(macro=None)
    assert agree.score > neutral.score > conflict.score
    assert "BEARISH_GOLD" in agree.statuses["macro"]
    assert agree.statuses["futures"] == "BEARISH_GOLD"
    # no candidate -> still no trade direction regardless of macro
    none_report = assess(direction=None, macro=bearish_ctx)
    assert none_report.direction is None and none_report.score == 0.0


def test_macro_conflict_contracts_adaptive_risk():
    from tests.test_adaptive_risk import ENGINE, elite

    clean = ENGINE.decide(elite())
    conflicted = ENGINE.decide(elite(macro_conflict=True))
    cautious = ENGINE.decide(elite(news_caution=True))
    assert conflicted.risk_pct < clean.risk_pct
    assert cautious.risk_pct < clean.risk_pct
