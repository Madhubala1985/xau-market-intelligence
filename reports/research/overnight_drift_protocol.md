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

---

# VERDICT (2026-07-05, same day — pre-registered criteria applied)

**Candidate v1: FAILED — not promoted.**

| criterion | result |
|---|---|
| 1. tick-level net capture t≥2 | **FAIL** — n=157 sampled train days: net +0.13 bps, median −0.82, t=+0.22 (entry spread 2.29 bps, exit 2.18) |
| 2. 2025 validation | not evaluated (short-circuited by 1/4/5; data stays unexamined) |
| 3. 2026 holdout | not evaluated (stays untouched) |
| 4. random baseline p99.9 | **FAIL** — gross +3.09 at percentile 99.80 vs p99.9=+3.10 (hairline, but the rule is the rule) |
| 5. no train year < −1 bps net | **FAIL** — 2022 net −1.64 at measured cost |

Bar-level train stats (gross +3.09 bps/trade, t=+11.1, all 6 years positive)
confirm the ANOMALY is real in mid prices; the tick test proves it is NOT
capturable through a ~2.2-2.3 bps spread. The effect lives inside the spread.

**Conditional path (recorded, not acted on):** the cost was measured on
Dukascopy quotes. If the actual execution venue (Exness raw-spread XAUUSDm)
shows all-in round-trip cost ≤ ~1.3 bps at 16:50/18:20 ET (spread +
commission, measured on the demo account, e.g. 2 weeks of symbol_info
sampling at those clock times), net expectancy ≈ +1.5-1.8 bps/trade and the
candidate re-enters at criterion 2. Venue measurement is a cost-parameter
update, NOT a rule change. Until then: dead.

**Program lesson for Phase C:** at ~2 bps retail round-trip, tradeable XAU
effects need |edge| well above ~5 bps/trade → target 4h-48h holds with
conditioning, not sub-hour windows.
