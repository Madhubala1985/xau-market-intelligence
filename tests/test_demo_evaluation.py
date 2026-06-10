"""Tests for the post-session evaluation + reflection reports (DEMO-EVAL).

Proves:
- totals, distributions (regime/session/confidence/spread), and block counts
  are derived correctly from a session report's cycle stats,
- performance metrics over CLOSED real demo trades: P&L, win rate, max
  drawdown of the realized equity curve,
- the three modes are separated: real MT5 demo orders (journal records with
  tickets) vs dry-run simulated orders vs analysis-only decisions,
- findings carry ONLY the approved classifications (Proven Defect /
  High-Confidence Defect / Hypothesis / Observation / Design Improvement),
- "market genuinely untradeable" is recognized (choppy window, no setups),
- the artificial session cap is reported as too strict when it blocked
  approved entries,
- missed opportunities are honestly classified as HYPOTHESIS (backtest first),
- the reflection report fills its sections and proposes no self-mutation,
- rendered reports contain no credentials.
"""

from datetime import datetime, timedelta, timezone

from src.data.enums import Direction, TradeOutcome
from src.data.schemas import TradeRecord
from src.reflection.demo_evaluation import (
    FindingClass,
    SessionEvaluator,
    build_reflection,
    render_evaluation_markdown,
    render_reflection_markdown,
)

T0 = datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc)


def cycle(minute, *, regime="TREND", session="LONDON", direction="WAIT",
          approved=False, reason="no setup", confidence=0.5, spread=0.18,
          entry_action="NONE", entry_detail="", risk_action=None,
          news_known=True, news_risky=False):
    return {
        "time_utc": (T0 + timedelta(minutes=minute)).isoformat(),
        "stage": "RISK_EVALUATED",
        "direction": direction,
        "approved": approved,
        "reason": reason,
        "spread_price": spread,
        "confidence": confidence,
        "uncertainty": 0.2,
        "regime": regime,
        "session": session,
        "htf_bias": "BULLISH",
        "news_known": news_known,
        "news_risky": news_risky,
        "risk_action": risk_action,
        "entry_action": entry_action,
        "entry_detail": entry_detail,
    }


def record(record_id, *, outcome, pnl=None, opened_min=0, closed_min=None,
           ticket=True, stop=2299.0, thesis="sweep reclaimed"):
    return TradeRecord(
        record_id=record_id,
        created_at_utc=T0 + timedelta(minutes=opened_min),
        symbol="XAUUSDM",
        direction=Direction.LONG,
        outcome=outcome,
        opened_at_utc=T0 + timedelta(minutes=opened_min),
        closed_at_utc=(
            T0 + timedelta(minutes=closed_min) if closed_min is not None else None
        ),
        entry_price=2300.0,
        stop_loss=stop,
        lot_size=0.05,
        pnl=pnl,
        confidence=0.75,
        uncertainty=0.2,
        thesis=thesis,
        notes=f"ticket={hash(record_id) % 10_000}" if ticket else "",
    )


def session_payload(stats, *, orders_sent=0, orders_simulated=0, mode="DEMO_LIVE",
                    violations=0, verdict="CLEAN"):
    return {
        "task": "DEMO-002",
        "mode": "SUPERVISED_DEMO",
        "symbol": "XAUUSDm",
        "profile": "evaluation",
        "report": {
            "symbol": "XAUUSDm",
            "mode": mode,
            "profile": "evaluation",
            "verdict": verdict,
            "started_at_utc": T0.isoformat(),
            "ended_at_utc": (T0 + timedelta(hours=1)).isoformat(),
            "cycles": len(stats),
            "decisions_logged": len(stats),
            "orders_sent": orders_sent,
            "orders_simulated": orders_simulated,
            "orders_rejected": 0,
            "entries_blocked": sum(
                1 for s in stats
                if s["entry_action"] in ("PLAN_BLOCKED", "ENTRY_BLOCKED",
                                         "CAP_REACHED")
            ),
            "stop_updates": 1,
            "violations": violations,
            "halt_reason": "",
            "final_reconciliation": {"clean": True},
            "cycle_stats": stats,
        },
    }


def traded_session():
    stats = [
        cycle(0),
        cycle(5, direction="LONG", approved=True, reason="ok",
              confidence=0.8, entry_action="SENT", entry_detail="ticket=1"),
        cycle(10, regime="RANGE"),
        cycle(15, direction="LONG", approved=True, reason="ok",
              confidence=0.75, entry_action="SENT", entry_detail="ticket=2"),
        cycle(20, regime="CHOPPY", reason="regime choppy"),
        cycle(25, news_risky=True, reason="news risk"),
    ]
    records = [
        record("T-1", outcome=TradeOutcome.OPEN, opened_min=5),
        record("T-1", outcome=TradeOutcome.WIN, pnl=50.0,
               opened_min=5, closed_min=12),
        record("T-2", outcome=TradeOutcome.OPEN, opened_min=15),
        record("T-2", outcome=TradeOutcome.LOSS, pnl=-30.0,
               opened_min=15, closed_min=40),
    ]
    return session_payload(stats, orders_sent=2), records


def test_totals_and_distributions():
    payload, records = traded_session()
    ev = SessionEvaluator().evaluate(payload, records)
    assert ev.cycles == 6
    assert ev.decisions_total == 6
    assert ev.actionable_decisions == 2
    assert ev.approved_decisions == 2
    assert ev.trades_real == 2
    assert ev.trades_simulated == 0
    assert ev.regime_distribution == {"TREND": 4, "RANGE": 1, "CHOPPY": 1}
    assert ev.session_distribution == {"LONDON": 6}
    assert ev.news_risky_cycles == 1
    assert ev.news_unknown_cycles == 0
    assert ev.spread_stats["samples"] == 6
    assert abs(ev.spread_stats["mean"] - 0.18) < 1e-9
    assert sum(ev.confidence_buckets.values()) == 6
    assert ev.no_trade_reasons["regime choppy"] == 1


def test_performance_pnl_winrate_and_max_drawdown():
    payload, records = traded_session()
    ev = SessionEvaluator().evaluate(payload, records)
    p = ev.performance
    assert p.trades_closed == 2
    assert p.wins == 1 and p.losses == 1
    assert p.win_rate == 0.5
    assert p.pnl_total == 20.0
    # equity: +50 (peak) then -30 -> trough 20; drawdown = 30
    assert p.max_drawdown == 30.0
    assert p.open_positions == 0


def test_modes_are_separated_real_vs_simulated():
    stats = [cycle(0, direction="LONG", approved=True, reason="ok",
                   entry_action="SIMULATED")]
    payload = session_payload(stats, orders_simulated=1, mode="DRY_RUN")
    ev = SessionEvaluator().evaluate(payload, [])
    assert ev.mode == "DRY_RUN"
    assert ev.trades_simulated == 1
    assert ev.trades_real == 0
    assert ev.performance.trades_closed == 0  # simulations never count as trades


def test_findings_use_only_approved_classifications():
    payload, records = traded_session()
    ev = SessionEvaluator().evaluate(payload, records)
    assert ev.findings  # the standing design-improvement finding at minimum
    for f in ev.findings:
        assert f.classification in FindingClass
    assert any(
        f.classification is FindingClass.DESIGN_IMPROVEMENT for f in ev.findings
    )


def test_untradeable_market_is_recognized_not_blamed_on_filters():
    stats = [cycle(i * 5, regime="CHOPPY", reason="regime choppy",
                   confidence=0.2) for i in range(6)]
    ev = SessionEvaluator().evaluate(session_payload(stats), [])
    assert ev.market_untradeable is True
    assert any("genuinely poor" in f.title for f in ev.findings)
    reflection = build_reflection(ev)
    assert any("correct patience" in line for line in reflection.avoided_correctly)
    # an untradeable window must not produce a "too strict" verdict
    assert not any("too narrow" in line for line in reflection.too_strict)


def test_artificial_cap_blocks_are_surfaced_as_too_strict():
    stats = [
        cycle(0, direction="LONG", approved=True, reason="ok",
              confidence=0.8, entry_action="SENT"),
        cycle(5, direction="LONG", approved=True, reason="ok", confidence=0.85,
              entry_action="CAP_REACHED",
              entry_detail="session max_orders=1 reached; manage-only"),
    ]
    ev = SessionEvaluator().evaluate(session_payload(stats, orders_sent=1), [])
    assert ev.entry_actions["CAP_REACHED"] == 1
    assert any("order cap" in f.title for f in ev.findings)
    reflection = build_reflection(ev)
    assert any("max_orders" in line or "cap" in line
               for line in reflection.too_strict)


def test_missed_opportunities_are_hypotheses_routed_to_backtest():
    stats = [
        cycle(0, direction="LONG", approved=True, confidence=0.85,
              reason="ok", entry_action="PLAN_BLOCKED",
              entry_detail="['NEWS_BLOCKED']: news risk active"),
    ]
    ev = SessionEvaluator().evaluate(session_payload(stats), [])
    missed = [f for f in ev.findings
              if f.title == "high-confidence entries were blocked"]
    assert missed and missed[0].classification is FindingClass.HYPOTHESIS
    assert missed[0].action == "backtest before changing"
    reflection = build_reflection(ev)
    assert reflection.missed_opportunities
    assert any("high-confidence" in line
               for line in reflection.backtest_before_change)
    assert not any("high-confidence" in line for line in reflection.fix_immediately)


def test_violations_must_be_fixed_immediately():
    payload, records = traded_session()
    payload["report"]["violations"] = 2
    payload["report"]["verdict"] = "ATTENTION_REQUIRED"
    ev = SessionEvaluator().evaluate(payload, records)
    assert any(
        f.classification is FindingClass.HIGH_CONFIDENCE_DEFECT
        and f.action == "fix immediately"
        for f in ev.findings
    )
    reflection = build_reflection(ev)
    assert reflection.fix_immediately


def test_reports_render_and_contain_no_credentials():
    payload, records = traded_session()
    ev = SessionEvaluator().evaluate(payload, records)
    reflection = build_reflection(ev)
    eval_md = render_evaluation_markdown(ev)
    refl_md = render_reflection_markdown(reflection)
    for text in (eval_md, refl_md):
        lowered = text.lower()
        assert "password" not in lowered
        assert "mt5_login" not in lowered
        assert "secret" not in lowered
    assert "Demo Session Evaluation" in eval_md
    assert "No live self-mutation" in refl_md
    # round-trip safety: the dict forms serialize
    import json
    json.dumps(ev.to_dict())
    json.dumps(reflection.to_dict())


def test_evaluator_accepts_a_bare_report_dict():
    stats = [cycle(0)]
    bare = session_payload(stats)["report"]
    ev = SessionEvaluator().evaluate(bare, [])
    assert ev.cycles == 1
    assert ev.mode == "DEMO_LIVE"
