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
