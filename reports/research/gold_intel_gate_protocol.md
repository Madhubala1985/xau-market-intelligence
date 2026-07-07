# Pre-registered protocol: GOLD-INTEL-001 replay ship gate

**Frozen 2026-07-07 before the gate run.** (Honesty gates per decision
2026-07-05-01; this gate decides whether gold_intel may trade the demo
account.)

## What is being tested

The restored day-narrative brain (+ regime dial + cost gates) with its June
2026 knobs (quality_bar 0.70, strong_bar 0.78, 2 entries/day, 3R trend
targets) — **frozen, no re-tuning** — over Dukascopy M1 history it has never
seen. Its prior positive evidence (+2.43R/10d, +7.0R/8.5mo) came from 2026
Exness MT5 data; 2019-2025 Dukascopy is out-of-tuning-sample.

## Harness

`scripts/intel_replay.py` → the standard `DecisionReplay` fill model:
- entry next-M5-open charged spread + 0.30 slippage adverse,
- **replay spread 0.50 USD** (mid-stress; > the 2.29 bps ≈ 0.45-0.9 USD
  measured Dukascopy entry spread at 2019-2025 price levels),
- stop-first intrabar ambiguity; chassis break-even at +1R,
- one position at a time; 25/day envelope mirror; R-scored.
- Regime dial fed CAUSALLY per day (cached FRED, as-of 1-day lag).

## Windows (fixed in `scripts/intel_replay.py` BEFORE any replay P&L existed)

Mar 1-28 and Sep 1-28 of each year 2019-2025 → 14 windows (~280 trading
days). 2026 remains untouched (holdout: Feb/Apr/Jun 2026, run ONLY on a
PASS).

**Disclosure:** during harness debugging (cost-gate defect: the fixed-USD
stop floor wrongly blocked all sub-$2 stops at 2021-2024 price levels, and
blocked approvals consumed the brain's daily slots), a smoke run of
2024-03-01..14 was seen: 22 trades, net −8.45R. The window set was NOT
changed in response; Mar-2024 stays in the gate and counts.

## PASS bar (all four required)

1. Total net R > 0 across all 14 windows,
2. ≥ 8 of 14 windows non-negative,
3. pooled max drawdown ≤ 20R,
4. ≥ 100 closed trades (else Insufficient Data, not a pass).

## On PASS
Run the 2026 holdout windows (Feb/Apr/Jun); holdout net R ≥ 0 required.
Only then: demo forward via the service (owner-started), with the
pre-registered live kill rule — if the demo book reaches −15R or the weekly
−10% stop, the service stops and the result is recorded as a live FAIL.

## On FAIL
The brain's prior edge does not replicate on 7 years of tick-derived data.
Record honestly in the decision log; gold_intel stays FLAT (the service is
not started); the negative result extends to the day-narrative composite.
No knob search on gate data — any re-tune is a NEW protocol on the train
years only (2019-2023), validated on 2024-2025 before it may claim the gate.
