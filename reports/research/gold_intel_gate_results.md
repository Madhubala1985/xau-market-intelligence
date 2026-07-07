# GOLD-INTEL-001 ship gate — results (2026-07-07)

Protocols: gold_intel_gate_protocol.md (v1, frozen pre-run, commit a8c19bf)
and gold_intel_gate_v2_protocol.md (v2, frozen pre-run, commit c23d80c).
Same 14 fixed windows (Mar+Sep 2019-2025), same frozen knobs, same harness;
only the cost model differs. Raw JSON: gold_intel_replay_gate*.json.

| run | costs | trades | net R | windows ≥ 0 | pooled DD | verdict |
|---|---|---|---|---|---|---|
| gate v1 | flat 0.50 USD + 0.30 slip | 577 | **−130.37** | 2/14 | 139.8R | **FAIL** |
| gate v2 | 2.2 bps + 1.0 bps (≈4.2 bps RT) | 566 | **−73.69** | 2/14 | 99.8R | **FAIL** |
| gross (diagnostic) | zero | 596 | **−1.56** | 7/14 | 46.6R | n/a (not a gate) |

## The decomposition answer

The zero-cost run settles the "bad decisions vs cost drag" question: the
brain's raw decision quality is **≈ 0R over 596 trades** — statistically a
coin flip BEFORE any costs. Costs then guarantee the loss (every realistic
cost model is firmly negative). This is not a cost-model artifact and not a
tuning-distance miss.

## What this falsifies

The day-narrative composite (day classification → playbooks → conviction →
quality bar), knobs frozen at their June 2026 optimum, does NOT have
persistent edge across 2019-2025. Its prior positive record (+2.43R/10d,
+7.0R/8.5mo on 2026 Exness data) was regime-local and/or small-sample. This
extends 40_CONCLUSION.md's verdict to the strongest composite the project
ever had.

Per-window detail: both cost models agree the only consistently non-negative
windows are 2025 (the regime nearest the June tuning). Gross-positive
pockets (2022-2023, 2025) never survive costs together with the losing
years.

## Consequences (per the frozen protocols)

- gold_intel stays FLAT. The trading service is NOT started; there is no
  run command to hand the owner.
- The 2026 holdout is NOT examined (PASS-only step; it stays clean for any
  future protocol).
- A knob re-tune would be a NEW protocol trained only on 2019-2023 and
  validated on 2024-2025 — but with gross expectancy ≈ 0, selectivity
  cannot rescue it (there is no positive subset to select; the same lesson
  as the gold_alpha EV-bar sweep).
- The one live thread remains the venue-spread measurement
  (scripts/measure_venue_spread.py, Windows, ~2 weeks) for overnight-drift
  v1 — the only anomaly with real statistical support (t=11 gross).
