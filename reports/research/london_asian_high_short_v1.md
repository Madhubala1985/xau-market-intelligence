# Research Result — london_asian_high_short (v1)

- **Classification:** **Insufficient Data**
- **Data span:** 2026-04-08T04:00:00+00:00 -> 2026-06-17T20:53:13+00:00
- **Base costs:** spread 0.20 + slippage 0.30 (USD, adverse)

## Exact mechanical rules

- **name:** london_asian_high_short
- **version:** v1
- **description:** London sweep of Asian high -> rejection -> bearish CHOCH -> FVG mitigation short; stop above swept high, fixed RR target.
- **asian_window_utc:** [00:00,07:00)
- **london_window_utc:** [07:00,11:00)
- **min_asian_candles:** 12
- **min_asian_range_usd:** 1.5
- **reclaim_within_bars:** 6
- **choch_within_bars:** 10
- **swing_strength:** 2
- **mitigation_within_bars:** 12
- **sl_buffer_usd:** 0.1
- **rr:** 2.0
- **session:** LONDON

## Result table (base costs)

| metric | value |
|---|---|
| occurrences | 0 |
| trades | 0 |
| win_rate | 0.0% |
| avg_R | +0.000 |
| median_R | +0.000 |
| expectancy_R | +0.000 |
| profit_factor | 0.00 |
| total_R | +0.0 |
| max_DD_R | 0.0 |
| max_consec_losses | 0 |
| wins / losses / breakeven | 0 / 0 / 0 |
| cancelled before fill | 0 (invalidated=0, expired_unfilled=0) |
| best / worst R | +0.00 / +0.00 |

> ⚠️ **Only 0 filled trades** (< 100). Per lab policy this is **Insufficient Data**: no edge claim is valid from this sample. Load more history and re-run.

## Spread / slippage sensitivity

| cost profile | spread | slippage | trades | win rate | expectancy R | total R |
|---|---|---|---|---|---|---|
| tight | 0.10 | 0.10 | 0 | 0.0% | +0.000 | +0.0 |
| base | 0.20 | 0.30 | 0 | 0.0% | +0.000 | +0.0 |
| wide | 0.40 | 0.50 | 0 | 0.0% | +0.000 | +0.0 |
| stress | 0.70 | 0.80 | 0 | 0.0% | +0.000 | +0.0 |

## Session sensitivity

| session | trades | win rate | expectancy R | total R |
|---|---|---|---|---|

## Winning examples

- (none)

## Losing examples (why they lost)

- (none)

## Automation verdict

- Automation is **NOT justified** (Insufficient Data). Execution stays retired. Refine rules as a NEW version or gather more data.
