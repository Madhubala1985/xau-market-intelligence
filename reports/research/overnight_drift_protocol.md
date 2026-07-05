# Pre-registered protocol: XAU overnight-drift candidate (ALPHA-HUNT-001)

Written 2026-07-05 BEFORE examining 2025 validation or 2026 holdout data for
this rule. This file freezes the rule and the pass criteria first.

## The finding (train = 2019-01-01 .. 2024-12-31 ONLY)

Gold's intraday drift concentrates in the hour after the COMEX daily break
(17:00→18:00 ET): ET-hour 18 mean +2.35 bps (t=4.7); all other hours ≈ 0.
Anchored in ET, not UTC (US DST). Bonferroni-corrected discovery scan:
reports/research/intraday_scan.md (hour=23 UTC cell z=+6.5).

Tick-level reality (measured, 47 sampled days): the reopen quote spread is
~5.7 bps — market orders AT the reopen capture nothing (net −5.6 bps).
Implementation must therefore enter BEFORE the break at normal spreads.

## Frozen rule v1 (chosen on train data only)

- Instrument: XAUUSD spot (demo: XAUUSDm).
- Every Mon–Thu: BUY at market at 16:50 ET; SELL at market at 18:20 ET.
  (Sundays excluded v1: no same-day pre-break session. Separate study later.)
- No stop inside the window by design intent, BUT the live executor must
  carry a hard catastrophe SL (policy: mandatory SL) far enough to not bind
  (5 × window std ≈ 50 bps ≈ 0.5% of price) — expected to trigger ~never.
- Train stats (bid-to-bid): +3.09 bps/trade, std 9.6, t=11.1, n=1195,
  positive each year 2019–2024 (worst: 2022 +0.57).

## Cost model to apply

Entry pays the 16:50 ET spread (tick-measured), exit pays the 18:20 ET
spread; net per trade = bid-to-bid return − entry ask/bid spread. Stress
grid: 1.0× / 1.5× / 2.0× measured median spreads.

## Pass criteria (must ALL hold, else the candidate is dead)

1. Tick-level net capture on sampled train days: mean net > 0 with t ≥ 2.
2. 2025 validation year (never used for rule choice): net expectancy > 0
   under the 1.5× cost stress.
3. 2026 holdout (untouched by every scan in this repo): net expectancy > 0.
4. Random-baseline: 1000 random same-length windows (same instrument/period,
   uniform random start hour) — the rule's gross mean must exceed the 99.9th
   percentile of random-window means (the hour-grid Bonferroni already
   implies this; this is the formal check).
5. Sub-period: no train year net-negative under measured (1.0×) costs by
   more than −1 bps/trade.

## What failure means

If any criterion fails, the anomaly is either not capturable at retail costs
or non-stationary — record it in 30_RESEARCH_FINDINGS.md and stop. Do NOT
re-tune the window on validation/holdout data.
