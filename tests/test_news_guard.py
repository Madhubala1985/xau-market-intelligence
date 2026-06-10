"""Tests for the news-risk guard (Audit F-5): honest, fail-closed by design.

Proves:
- no source at all -> known=False -> blocks_orders (fail closed),
- manual block file always wins,
- calendar windows raise/clear the risk flag with known=True,
- a MALFORMED calendar reads as unknown (fail closed), never as "no news",
- naive timestamps are rejected,
- the live shadow session raises news_risk only on a known-risky state.
"""

import json
from datetime import datetime, timezone

import pytest

from src.risk import NewsRiskGuard

UTC = timezone.utc
NOW = datetime(2026, 6, 10, 12, 30, tzinfo=UTC)


def make_guard(tmp_path, calendar: dict | None = None) -> NewsRiskGuard:
    cal_path = tmp_path / "news_windows.json"
    if calendar is not None:
        cal_path.write_text(json.dumps(calendar), encoding="utf-8")
    return NewsRiskGuard(
        block_path=tmp_path / "NEWS_BLOCK", calendar_path=cal_path
    )


def window(start: str, end: str, label="CPI") -> dict:
    return {"start_utc": start, "end_utc": end, "label": label}


# ---------------------------------------------------------------------------
# Fail-closed without a source
# ---------------------------------------------------------------------------

def test_no_source_is_unknown_and_blocks_orders(tmp_path):
    state = make_guard(tmp_path).assess(NOW)
    assert state.known is False
    assert state.risky is False  # not asserted risky — honestly unknown
    assert state.blocks_orders is True  # but orders must fail closed
    assert state.source == "none"


def test_malformed_calendar_reads_as_unknown_not_safe(tmp_path):
    cal_path = tmp_path / "news_windows.json"
    cal_path.write_text("{not valid json", encoding="utf-8")
    guard = NewsRiskGuard(block_path=tmp_path / "NB", calendar_path=cal_path)
    state = guard.assess(NOW)
    assert state.known is False
    assert state.blocks_orders is True


def test_calendar_with_naive_timestamps_is_unknown(tmp_path):
    guard = make_guard(tmp_path, {"windows": [
        window("2026-06-10T12:00:00", "2026-06-10T13:00:00")  # naive -> invalid
    ]})
    state = guard.assess(NOW)
    assert state.known is False
    assert state.blocks_orders is True


# ---------------------------------------------------------------------------
# Manual block
# ---------------------------------------------------------------------------

def test_manual_block_engages_and_releases(tmp_path):
    guard = make_guard(tmp_path)
    guard.engage_manual_block("NFP in 10 minutes")
    state = guard.assess(NOW)
    assert state.known is True and state.risky is True
    assert state.source == "manual"
    assert state.blocks_orders is True
    guard.release_manual_block()
    assert make_guard(tmp_path).assess(NOW).source == "none"


def test_manual_block_wins_over_quiet_calendar(tmp_path):
    guard = make_guard(tmp_path, {"windows": []})
    guard.engage_manual_block()
    assert guard.assess(NOW).source == "manual"


# ---------------------------------------------------------------------------
# Calendar windows
# ---------------------------------------------------------------------------

def test_inside_calendar_window_is_risky(tmp_path):
    guard = make_guard(tmp_path, {"windows": [
        window("2026-06-10T12:00:00+00:00", "2026-06-10T13:00:00+00:00")
    ]})
    state = guard.assess(NOW)  # 12:30 — inside
    assert state.known is True and state.risky is True
    assert state.source == "calendar"
    assert "CPI" in state.detail


def test_outside_window_is_known_and_clear(tmp_path):
    guard = make_guard(tmp_path, {"windows": [
        window("2026-06-10T14:00:00+00:00", "2026-06-10T15:00:00+00:00")
    ]})
    state = guard.assess(NOW)  # 12:30 — before the window
    assert state.known is True and state.risky is False
    assert state.blocks_orders is False


def test_empty_calendar_is_an_explicit_all_clear(tmp_path):
    # An empty windows list is the operator's explicit assertion.
    state = make_guard(tmp_path, {"windows": []}).assess(NOW)
    assert state.known is True and state.risky is False


def test_naive_now_rejected(tmp_path):
    with pytest.raises(ValueError):
        make_guard(tmp_path).assess(datetime(2026, 6, 10, 12, 30))


# ---------------------------------------------------------------------------
# Shadow session wiring
# ---------------------------------------------------------------------------

def test_shadow_session_passes_known_risky_news_into_pipeline(tmp_path):
    from tests.test_live_shadow import FakeMT5, demo_env, BASE_DT
    from datetime import timedelta
    from unittest.mock import MagicMock
    from src.broker.mt5_data_adapter import MT5DataAdapter
    from src.broker.mt5_settings import load_mt5_settings
    from src.execution import LiveShadowSession, make_live_pipeline
    from src.journal import TradeJournal

    guard = make_guard(tmp_path)
    guard.engage_manual_block("test window")

    captured = {}

    class SpyPipeline:
        def decide(self, inp):
            captured["news_risk"] = inp.news_risk
            return make_live_pipeline("XAUUSDM").decide(inp)

    adapter = MT5DataAdapter(load_mt5_settings(demo_env()), client=FakeMT5())
    adapter.connect()
    session = LiveShadowSession(
        adapter=adapter, pipeline=SpyPipeline(),
        journal=TradeJournal(tmp_path / "j.jsonl"), symbol="XAUUSDm",
        news_guard=guard,
        now=lambda: BASE_DT + timedelta(seconds=60),
        monotonic=MagicMock(side_effect=range(0, 1000, 10)), sleep=MagicMock(),
    )
    session.decide_once()
    assert captured["news_risk"] is True

# ---------------------------------------------------------------------------
# NEWS-001: graded states (FINAL-INTELLIGENCE)
# ---------------------------------------------------------------------------

import json as _json
from datetime import timedelta as _td

from src.risk.news_guard import (NewsStatus, NewsWindow,
                                 StaticCalendarProvider)


def _write_cal(tmp_path, windows):
    cal = tmp_path / "news.json"
    cal.write_text(_json.dumps({"windows": windows}), encoding="utf-8")
    return cal


def _guard(tmp_path, windows):
    cal = _write_cal(tmp_path, windows)
    return NewsRiskGuard(block_path=tmp_path / "NB", calendar_path=cal)


def test_high_impact_active_blocks_with_status(tmp_path):
    now = datetime(2026, 6, 10, 12, 30, tzinfo=timezone.utc)
    state = _guard(tmp_path, [{
        "start_utc": "2026-06-10T12:00:00+00:00",
        "end_utc": "2026-06-10T13:00:00+00:00",
        "label": "CPI", "impact": "HIGH", "category": "CPI",
    }]).assess(now)
    assert state.status == NewsStatus.ACTIVE
    assert state.risky is True and state.blocks_orders
    assert "CPI" in state.detail


def test_medium_impact_active_reduces_instead_of_blocking(tmp_path):
    now = datetime(2026, 6, 10, 12, 30, tzinfo=timezone.utc)
    state = _guard(tmp_path, [{
        "start_utc": "2026-06-10T12:00:00+00:00",
        "end_utc": "2026-06-10T13:00:00+00:00",
        "label": "ISM", "impact": "MEDIUM", "category": "ISM_PMI",
    }]).assess(now)
    assert state.status == NewsStatus.ACTIVE
    assert state.risky is False and state.caution is True
    assert state.blocks_orders is False  # reduced, not blocked


def test_high_impact_soon_reduces_risk(tmp_path):
    now = datetime(2026, 6, 10, 12, 40, tzinfo=timezone.utc)
    state = _guard(tmp_path, [{
        "start_utc": "2026-06-10T13:00:00+00:00",
        "end_utc": "2026-06-10T13:30:00+00:00",
        "label": "NFP", "impact": "HIGH", "category": "NFP",
    }]).assess(now)
    assert state.status == NewsStatus.HIGH_IMPACT_SOON
    assert state.caution is True and state.risky is False
    assert "NFP" in state.detail and "min" in state.detail


def test_unknown_impact_is_treated_as_high(tmp_path):
    now = datetime(2026, 6, 10, 12, 30, tzinfo=timezone.utc)
    state = _guard(tmp_path, [{
        "start_utc": "2026-06-10T12:00:00+00:00",
        "end_utc": "2026-06-10T13:00:00+00:00",
        "label": "mystery", "impact": "banana",
    }]).assess(now)
    assert state.status == NewsStatus.ACTIVE and state.risky is True


def test_manual_block_and_unknown_statuses(tmp_path):
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    guard = NewsRiskGuard(block_path=tmp_path / "NB",
                          calendar_path=tmp_path / "missing.json")
    assert guard.assess(now).status == NewsStatus.UNKNOWN
    guard.engage_manual_block("operator")
    assert guard.assess(now).status == NewsStatus.BLOCK
    guard.release_manual_block()
    cal_guard = _guard(tmp_path, [])
    assert cal_guard.assess(now).status == NewsStatus.CLEAR


def test_provider_abstraction_is_injectable(tmp_path):
    class FakeFeed:
        def fetch_windows(self, now):
            return [NewsWindow(start_utc=now - _td(minutes=5),
                               end_utc=now + _td(minutes=5),
                               label="FOMC", impact="HIGH", category="FOMC")]

    guard = NewsRiskGuard(block_path=tmp_path / "NB",
                          calendar_path=tmp_path / "missing.json",
                          provider=FakeFeed())
    state = guard.assess(datetime(2026, 6, 10, 18, 0, tzinfo=timezone.utc))
    assert state.status == NewsStatus.ACTIVE and "FOMC" in state.detail


def test_old_calendar_format_still_parses(tmp_path):
    # No impact/category keys: backward compatible, treated as HIGH.
    provider = StaticCalendarProvider(_write_cal(tmp_path, [{
        "start_utc": "2026-06-10T12:00:00+00:00",
        "end_utc": "2026-06-10T13:00:00+00:00",
        "label": "legacy",
    }]))
    windows = provider.fetch_windows(
        datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    )
    assert windows is not None and windows[0].impact == "HIGH"
