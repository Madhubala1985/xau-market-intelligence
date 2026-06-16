"""XAU/USD edge-discovery research lab.

This package is the new front door for the project (see 29_RESEARCH_LAB.md).
Its single job is to PROVE OR DISPROVE specific, fully-mechanical XAU/USD
setups with evidence, before any automation is permitted.

It reuses the existing repo purely as infrastructure (data schemas, session
utilities, structure/zone/sweep primitives). It NEVER sends orders, never runs
the trading service, and never optimizes for "confidence" — only expectancy.

Hard rules (mirrored from the owner directive and 06_DATA_POLICY.md):
- No live orders. No trading service. Execution is retired for now.
- No look-ahead: a decision at bar t may only see candles[:t+1]; fills happen
  strictly forward in time under conservative (adverse) cost assumptions.
- No curve-fitting: setup rules are versioned. Changing a rule after seeing a
  result requires a NEW version recorded separately, not an in-place edit.
- No success claims from tiny samples: < MIN_OCCURRENCES => Insufficient Data.
"""

from research.metrics import (
    Classification,
    Metrics,
    TradeResult,
    classify,
    compute_metrics,
)

__all__ = [
    "Classification",
    "Metrics",
    "TradeResult",
    "classify",
    "compute_metrics",
]
