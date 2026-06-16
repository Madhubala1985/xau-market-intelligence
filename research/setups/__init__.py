"""Mechanical setup definitions for the research lab.

Each setup is a versioned, fully-mechanical detector. It emits EntryIntents
(pending limit orders with stop / target / invalidation / expiry) using only
data available at the arming bar. The harness then simulates fills strictly
forward in time. Setups contain the EDGE; the simulator is shared and
conservative.
"""

from research.setups.base import EntryIntent, MarketData, Setup
from research.setups.london_sweep_reclaim import LondonSweepReclaimLong

__all__ = ["EntryIntent", "MarketData", "Setup", "LondonSweepReclaimLong"]

# Registry of setups available to scripts/research_run.py.
REGISTRY = {
    LondonSweepReclaimLong.name: LondonSweepReclaimLong,
}
