# 29_RESEARCH_LAB.md — XAU/USD Edge-Discovery Research Lab

## Mission (owner directive, 2026-06-17)

**Stop building trading bots.** The previous approach failed because we kept
shipping full autonomous models before proving a repeatable edge. The project is
now an **edge-discovery research lab first**.

- Execution is **retired** for now. No live orders. The trading service is not run.
- The existing repo is used **only as infrastructure** (MT5 data export, candle
  schemas, session/structure/zone/sweep primitives, accounting).
- **Goal:** find ONE repeatable XAU/USD setup with **positive expectancy** —
  proven on ≥100 occurrences — **before any automation is allowed.**

This supersedes the aggressive-growth / autonomous-model direction
(GOLD-ALPHA-001, LIQUIDITY-INTEL-001 and earlier). Those profiles stay in the
tree as retired infrastructure; none of them trades.

## Anti-curve-fit rules (binding)

1. **No look-ahead.** A decision at bar `t` sees only `candles[:t+1]`; fills are
   simulated strictly forward under adverse (worst-case) cost assumptions.
2. **Versioned rules.** Setup rules are frozen per version. Changing a rule after
   seeing a result requires a **new version recorded separately** — never an
   in-place edit to make a number look better.
3. **No tiny-sample claims.** < 100 filled occurrences ⇒ **Insufficient Data**,
   regardless of how good the sample looks.
4. **Cost stress is mandatory.** Every setup is run across a spread/slippage grid;
   an edge that dies under realistic costs is not an edge.

## Architecture

```
research/
  data_loader.py    load+validate candles from data/raw/ (CSV); aggregate from M1
  metrics.py        TradeResult, Metrics, classification thresholds (v1, frozen)
  harness.py        forward-only fill simulator + cost grid + session breakdown
  report.py         renders the required evidence report (markdown)
  setups/
    base.py         EntryIntent / MarketData / Setup contract
    london_sweep_reclaim.py   Setup 1 (v1) — implemented
scripts/
  export_mt5_history.py   WINDOWS-side: dump XAUUSD CSVs into data/raw/ (data-only)
  research_run.py         run setups over stored history -> reports/research/*.md
tests/
  test_research_lab.py    end-to-end proof on synthetic data (no MT5 needed)
```

Reused infrastructure: `src/data/{schemas,enums,aggregation,sessions,session_levels}`,
`src/structure/{market_structure,zones}`, `src/liquidity/{sweep,liquidity_map}`.

## Data flow (how to get real numbers)

MT5's Python package is **Windows-only and unavailable in the research (WSL/Linux)
environment**, and the repo ships **no stored candles**. So:

1. On the **Windows MT5 terminal**, in the project venv:
   `python scripts/export_mt5_history.py --years 3`
   → writes `data/raw/XAUUSD_{5M,15M,1H,4H,1D}.csv` (data-fetch only; never orders).
2. Sync `data/raw/*.csv` to the research environment.
3. `python scripts/research_run.py` → `reports/research/<setup>_<version>.md`.

Until step 1 runs, the lab is **built and self-verified on synthetic data** but
has **no real occurrences** — every result reads *Insufficient Data* by design.

## Classification thresholds (metrics.py, v1 — frozen)

| Class | Rule |
|---|---|
| Insufficient Data | filled trades < 100 |
| No Edge | expectancy ≤ 0 OR profit factor < 1.0 |
| Proven Edge Candidate | expectancy ≥ +0.10R AND profit factor ≥ 1.30 AND holds ≥50% of base expectancy across the cost grid (and stays positive) |
| Weak Edge | positive but fails a "proven" gate |

Only a **Proven Edge Candidate** unlocks a proposal for an execution model — and
that proposal is itself gated on out-of-sample / walk-forward confirmation.

## Setups

### Setup 1 (v1): London sweep of Asian low → reclaim → displacement → FVG → long
`research/setups/london_sweep_reclaim.py` — **implemented & self-tested.**
Exact mechanical rules are documented in that module's docstring and emitted in
every report. Summary: Asian range 00:00–07:00 UTC; in the London window
07:00–11:00 UTC an M5 candle sweeps below the Asian low, price closes back above
it (reclaim), a bullish displacement candle (range ≥ 1.5× baseline) leaves a
3-candle FVG; buy the FVG mitigation, stop below the swept low, fixed 2R target;
invalidate on a new low below the swept low before fill; one trade/day.

### Setups roadmap (not yet implemented — add as separate versioned modules)
2. London sweep of Asian high → rejection → CHOCH → FVG mitigation → short.
3. NY sweep of London high/low → failed continuation → reversal displacement.
4. Trend-day continuation after H1/M15 BOS → M5 FVG retest.
5. Post-spike chop-avoidance filter (a no-trade gate, measured as uplift).

## Status / what to build next

- **Done:** lab scaffolding, loader, metrics+classification, forward simulator,
  cost-stress grid, session breakdown, report renderer, Setup 1 (v1), Windows
  exporter, end-to-end synthetic test (6 tests pass; 826 total collected).
- **Blocked on data:** real result tables require the one-time Windows export.
- **Next:** (a) run the export; (b) `research_run.py` to produce Setup 1's first
  real evidence table; (c) implement Setups 2–4 as versioned modules; (d) only if
  a setup reaches *Proven Edge Candidate*, write an execution-model proposal.
