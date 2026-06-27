# 41_METHODOLOGY.md — The Reusable Edge-Falsification Harness

The most valuable thing this project produced is not a strategy — it is a
**market-agnostic research harness for falsifying trading edges.** It is designed
around one principle: **the default answer is "no edge," and a claim must survive
a gauntlet of controls to overturn it.** Most of the gauntlet exists specifically
to defeat the ways researchers fool themselves.

This document describes the harness as a standalone tool, independent of XAU/USD.

---

## Design principle: assume noise, demand proof

A backtest that "looks good" is the beginning of an investigation, not the end.
Edges die for predictable reasons — look-ahead leakage, overfitting to one
period, ignoring costs, multiple comparisons, and confusing a market trend with a
signal. The harness has one stage to kill each failure mode.

## The gauntlet (every stage is mandatory)

1. **Strictly causal backtest.** A decision at bar *t* sees only `candles[:t+1]`;
   fills happen forward in time. Setups emit `EntryIntent`s (pending LIMIT or
   next-bar MARKET) with explicit stop / target / invalidation / expiry. The
   simulator is conservative: stop-checked-first on ties, adverse fills.
   *Kills:* look-ahead bias.

2. **Frozen classification gate.** Thresholds fixed in advance (`research/metrics.py`):
   `Insufficient Data` (< 100 trades) → `No Edge` (expectancy ≤ 0 or PF < 1) →
   `Weak Edge` → `Proven Edge Candidate` (expectancy ≥ +0.10R **and** PF ≥ 1.30
   **and** holds ≥ 50% of edge under cost-stress). No tuning the bar after seeing
   the result. *Kills:* moving goalposts, tiny-sample claims.

3. **Cost-stress grid.** Re-run across spread/slippage levels (tight → stress). An
   edge that only exists at zero cost is not an edge. *Kills:* ignoring frictions.

4. **Walk-forward / multi-regime k-fold.** Expanding-window or fold splits;
   require positive performance across *consecutive* periods, not just the recent
   one. This single stage killed the breakout "edge" (profitable 2023–26, a loser
   2011–17). *Kills:* regime artifacts / non-stationarity / recency bias.

5. **Random-entry baseline.** Monte-Carlo random entries with **identical**
   stop-distance, R-multiple, and long/short mix, placed at random bars. If the
   strategy is not clearly outside this distribution, the *signal* adds nothing —
   the result was geometry + trend, not the idea. This exposed Fibonacci levels
   (z = +0.57) and every isolated SMC factor as inert. *Kills:* mistaking risk
   geometry / drift for signal.

6. **Bonferroni correction.** When testing *k* hypotheses, require significance at
   α/k (e.g. 6 factors → z ≥ 2.39). *Kills:* multiple-comparisons false positives.

7. **Out-of-sample holdout replication.** A candidate must also hold on an
   untouched fold it was not selected on. *Kills:* the survivor that was really
   the luckiest of many tries.

A claim is an **edge** only if it clears all seven. Everything else is recorded
and discarded.

## Code map (reusable, market-agnostic core)

| File | Role |
|---|---|
| `research/data_loader.py` | Load/validate candles from CSV; aggregate timeframes; skip malformed rows |
| `research/setups/base.py` | `EntryIntent` / `MarketData` / `Setup` contract (the plug-in point) |
| `research/harness.py` | Causal simulator (LIMIT + MARKET, time-stops), cost grid, session breakdown, `run_setup` |
| `research/metrics.py` | `TradeResult` / `Metrics` + **frozen** classification thresholds |
| `research/report.py` | Per-setup evidence report + cross-setup ranking |
| `scripts/*_tune.py`, `edge_scan.py` | Walk-forward / k-fold / forward-return scanning |
| `scripts/fib_run.py`, `factor_isolation.py` | Random-baseline + Bonferroni + holdout templates |
| Data fetchers | `fetch_yahoo_history.py` (prices), `macro_data.py` (FRED keyless + CFTC COT) |

## The plug-in contract — pointing it at a new domain

To test a new instrument or hypothesis, supply two things; the gauntlet is reused
unchanged:

1. **A data loader** producing time-ordered `Candle`s (or any OHLC-shaped series).
2. **A `Setup`** — a class with `scan(MarketData) -> List[EntryIntent]` that emits
   causal entries with stop/target/invalidation. That is the *only* thing a new
   idea needs to implement. The harness handles fills, costs, metrics, gate,
   folds; the script templates add the random baseline + correction + holdout.

Nothing in the gauntlet is XAU-specific. It operates on returns and R-multiples.

## Domains it could be pointed at next

- **Other liquid instruments** (indices, FX majors, crypto, single names) — same
  price-pattern hypotheses, fresh data; the harness will falsify or confirm them
  with identical rigor.
- **Cross-asset / macro factor models** — the `macro_data.py` pattern (FRED, COT)
  generalizes to any factor → forward-return study with walk-forward CV.
- **Event studies** — scheduled releases (CPI/FOMC/earnings): post-event drift /
  volatility regimes via the same forward-return + holdout machinery.
- **Strategy due-diligence** — drop a *third-party* signal in as a `Setup` and run
  it through the gauntlet before risking capital on it. (Arguably the highest-value
  reuse: a vendor-/influencer-claim falsifier.)

## Known limitations (so the next user isn't misled)

- **Daily/H1 frequency.** It does not model microstructure, queue position, or
  sub-bar latency — it cannot evaluate HFT/execution edges.
- **Proxy-data caveat.** Public sources (e.g. GC=F for spot XAU) differ from a
  specific broker feed; confirm survivors on the target feed before trusting.
- **It falsifies; it does not optimize.** By design it resists fitting. Finding an
  edge still requires a real hypothesis to feed it — the harness only tells you,
  honestly, whether that hypothesis is noise.

---

This harness is the project's transferable legacy: a disciplined way to ask "does
this actually work?" and get an answer you can trust — including, often, **"no."**
That "no", delivered cheaply and rigorously, is exactly what it is for.
