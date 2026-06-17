# Research Result — ny_london_sweep_reversal (v1)

- **Classification:** **Insufficient Data**
- **Data span:** 2026-04-08T04:00:00+00:00 -> 2026-06-17T20:53:13+00:00
- **Base costs:** spread 0.20 + slippage 0.30 (USD, adverse)

## Exact mechanical rules

- **name:** ny_london_sweep_reversal
- **version:** v1
- **description:** NY sweep of London high/low -> failed continuation -> reversal displacement -> FVG mitigation; stop beyond the swept extreme.
- **london_window_utc:** [07:00,12:00)
- **ny_window_utc:** [12:00,16:00)
- **min_london_candles:** 24
- **min_range_usd:** 2.0
- **reclaim_within_bars:** 6
- **displacement_factor:** 1.5
- **mitigation_within_bars:** 12
- **sl_buffer_usd:** 0.1
- **rr:** 2.0
- **session:** NEW_YORK

## Result table (base costs)

| metric | value |
|---|---|
| occurrences | 19 |
| trades | 9 |
| win_rate | 11.1% |
| avg_R | -0.732 |
| median_R | -1.037 |
| expectancy_R | -0.732 |
| profit_factor | 0.23 |
| total_R | -6.6 |
| max_DD_R | 6.6 |
| max_consec_losses | 5 |
| wins / losses / breakeven | 1 / 8 / 0 |
| cancelled before fill | 10 (invalidated=3, expired_unfilled=7) |
| best / worst R | +1.94 / -1.16 |

> ⚠️ **Only 9 filled trades** (< 100). Per lab policy this is **Insufficient Data**: no edge claim is valid from this sample. Load more history and re-run.

## Spread / slippage sensitivity

| cost profile | spread | slippage | trades | win rate | expectancy R | total R |
|---|---|---|---|---|---|---|
| tight | 0.10 | 0.10 | 9 | 11.1% | -0.691 | -6.2 |
| base | 0.20 | 0.30 | 9 | 11.1% | -0.732 | -6.6 |
| wide | 0.40 | 0.50 | 9 | 11.1% | -0.781 | -7.0 |
| stress | 0.70 | 0.80 | 9 | 11.1% | -0.854 | -7.7 |

## Session sensitivity

| session | trades | win rate | expectancy R | total R |
|---|---|---|---|---|
| NEW_YORK | 9 | 11.1% | -0.732 | -6.6 |

## Winning examples

- **2026-05-12** SHORT entry@4705.00 (2026-05-12T13:35:00+00:00) → +1.94R [TAKE_PROFIT] MFE +2.01R / MAE -0.31R — target hit (14.40 risk)

## Losing examples (why they lost)

- **2026-06-17** SHORT entry@4349.90 (2026-06-17T13:10:00+00:00) → -1.16R [STOP_LOSS] MFE +0.57R / MAE -1.78R — stopped at swept low
- **2026-05-21** LONG entry@4509.70 (2026-05-21T12:50:00+00:00) → -1.13R [STOP_LOSS] MFE +0.38R / MAE -1.38R — stopped at swept low
- **2026-04-22** LONG entry@4773.90 (2026-04-22T13:50:00+00:00) → -1.06R [STOP_LOSS] MFE +0.25R / MAE -1.06R — stopped at swept low
- **2026-05-01** SHORT entry@4606.00 (2026-05-01T13:00:00+00:00) → -1.06R [STOP_LOSS] MFE +0.71R / MAE -1.11R — stopped at swept low
- **2026-04-21** LONG entry@4803.50 (2026-04-21T13:55:00+00:00) → -1.04R [STOP_LOSS] MFE +0.25R / MAE -1.08R — stopped at swept low

## Automation verdict

- Automation is **NOT justified** (Insufficient Data). Execution stays retired. Refine rules as a NEW version or gather more data.
