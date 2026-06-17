"""Mechanical setup definitions for the research lab.

Each setup is a versioned, fully-mechanical detector. It emits EntryIntents
(pending limit orders with stop / target / invalidation / expiry) using only
data available at the arming bar. The harness then simulates fills strictly
forward in time. Setups contain the EDGE; the simulator is shared and
conservative.

Setup 5 (post_spike_chop) is a NO-TRADE FILTER, not a directional setup, so it
is not in the directional REGISTRY — it is measured as expectancy uplift on the
other setups (see post_spike_chop.measure_uplift).
"""

from research.setups.base import EntryIntent, MarketData, Setup
from research.setups.donchian_breakout_trend import DonchianBreakoutTrend
from research.setups.london_asian_high_short import LondonAsianHighShort
from research.setups.london_sweep_reclaim import LondonSweepReclaimLong
from research.setups.mean_reversion_m5 import MeanReversionM5
from research.setups.momentum_continuation import MomentumContinuation
from research.setups.ny_london_sweep_reversal import NyLondonSweepReversal
from research.setups.trend_bos_fvg_retest import TrendBosFvgRetest

__all__ = [
    "EntryIntent",
    "MarketData",
    "Setup",
    "LondonSweepReclaimLong",
    "LondonAsianHighShort",
    "NyLondonSweepReversal",
    "TrendBosFvgRetest",
    "MomentumContinuation",
    "DonchianBreakoutTrend",
    "MeanReversionM5",
    "REGISTRY",
]

# Directional setups available to scripts/research_run.py.
REGISTRY = {
    LondonSweepReclaimLong.name: LondonSweepReclaimLong,
    LondonAsianHighShort.name: LondonAsianHighShort,
    NyLondonSweepReversal.name: NyLondonSweepReversal,
    TrendBosFvgRetest.name: TrendBosFvgRetest,
    MomentumContinuation.name: MomentumContinuation,
    DonchianBreakoutTrend.name: DonchianBreakoutTrend,
    MeanReversionM5.name: MeanReversionM5,
}
