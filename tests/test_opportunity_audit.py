"""Tests for the long no-trade opportunity audit (INTELLIGENCE-001)."""

from src.reflection.demo_evaluation import FindingClass
from src.reflection.opportunity_audit import (
    build_opportunity_audit,
    render_opportunity_audit_markdown,
)


def stat(*, session="LONDON", entry_action="NONE", confluence=0.3,
         mtf_direction=None, mtf_score=0.0, regime="CHOPPY",
         subtype="LOW_QUALITY_CHOP", sweep="NONE", displacement=0.5):
    return {
        "session": session,
        "entry_action": entry_action,
        "confluence_score": confluence,
        "mtf_direction": mtf_direction,
        "mtf_score": mtf_score,
        "regime": regime,
        "regime_subtype": subtype,
        "intel": {
            "displacement_ratio": displacement,
            "confluence": {"statuses": {"sweep": sweep}},
        },
    }


def test_hard_block_window_reads_no_trade_correct():
    stats = [stat(subtype="DANGEROUS_CHOP") for _ in range(30)]
    audit = build_opportunity_audit(stats)
    assert audit.verdict == "NO_TRADE_CORRECT"
    assert audit.trades_taken == 0
    assert any(
        f.classification is FindingClass.MARKET_ARTIFACT for f in audit.findings
    )


def test_repeated_near_misses_read_possibly_too_strict():
    stats = [
        stat(confluence=0.62, mtf_direction="SHORT", mtf_score=0.8,
             sweep="TRUE_SWEEP", displacement=2.0)
        for _ in range(30)
    ]
    audit = build_opportunity_audit(stats)
    assert audit.verdict == "POSSIBLY_TOO_STRICT"
    assert audit.near_misses == 30
    hypo = [f for f in audit.findings
            if f.classification is FindingClass.HYPOTHESIS]
    assert hypo and all(f.action == "backtest before changing" for f in hypo)
    # aligned MTF + sweep + displacement coincided without an entry
    assert any("coincided" in f.title for f in audit.findings)


def test_trades_taken_reads_mixed():
    stats = [stat() for _ in range(10)] + [stat(entry_action="SENT")]
    audit = build_opportunity_audit(stats)
    assert audit.verdict == "MIXED"
    assert audit.trades_taken == 1


def test_all_classifications_are_valid_and_render():
    stats = [stat() for _ in range(10)]
    audit = build_opportunity_audit(stats)
    for f in audit.findings:
        assert f.classification in FindingClass
    md = render_opportunity_audit_markdown(audit)
    assert "Opportunity Audit" in md
    assert audit.verdict in md
    payload = audit.to_dict()
    assert payload["cycles_examined"] == 10
