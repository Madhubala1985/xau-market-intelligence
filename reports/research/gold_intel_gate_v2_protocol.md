# Pre-registered protocol: GOLD-INTEL-001 ship gate v2 (corrected costs)

**Frozen 2026-07-07, after gate v1 FAILED and before any v2 result was
computed.** Registered per decision 2026-07-07-02(c).

## Why a v2 exists (measurement correction, not results shopping)

Gate v1 (reports/research/gold_intel_gate_protocol.md) charged a FLAT 0.50
USD spread across 2019-2025. Gold moved $1,280 → $3,700 over that span, so
the flat charge was 3.8 bps in 2019 but 1.6 bps in 2025 — costs overstated
in early years, understated recently. v2 uses PRICE-PROPORTIONAL costs:

- spread = **2.2 bps of price** (the measured Dukascopy entry spread, the
  same figure used across ALPHA-HUNT-001),
- slippage = **1.0 bps of price** per side,
- total ≈ 4.2 bps round trip — the program's standard cost bar.

This correction is HARSHER than v1 on the only two windows that were
positive in v1 (2025, where 0.50 USD ≈ 1.6 bps) and gentler on 2019-2021.
It cannot rig the verdict upward for the windows that carried v1's hope.

## Everything else is IDENTICAL to v1 (windows, harness, bars)

Same 14 windows (Mar+Sep 2019-2025), same DecisionReplay fill model
(next-open adverse fill, stop-first ambiguity, BE at +1R), same frozen
knobs, same causal regime dial, same PASS bar:
1. total net R > 0, 2. ≥ 8/14 windows non-negative, 3. pooled DD ≤ 20R,
4. ≥ 100 trades.

## Also run (diagnostic, NOT a gate)

The same 14 windows at ZERO cost (spread 0, slippage 0) to decompose the
v1 result into decision quality vs cost drag. This number cannot promote
anything; it only informs the post-mortem.

## Verdict rules

- v2 PASS → 2026 holdout (Feb/Apr/Jun) at v2 costs must be ≥ 0 → only then
  demo forward with the pre-registered live kill (−15R book or weekly −10%).
- v2 FAIL → the day-narrative composite is falsified at realistic costs
  across regimes; gold_intel stays FLAT permanently in this form; the
  result extends the negative record. Any knob re-tune is a NEW protocol
  trained ONLY on 2019-2023 and validated on 2024-2025 before it may claim
  a gate — and the v1+v2 FAILs remain on the record either way.
