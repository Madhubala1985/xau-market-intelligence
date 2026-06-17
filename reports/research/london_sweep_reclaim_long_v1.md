# Research Result — london_sweep_reclaim_long (v1)

- **Classification:** **Insufficient Data**
- **Data span:** 2026-04-08T04:00:00+00:00 -> 2026-06-17T20:53:13+00:00
- **Base costs:** spread 0.20 + slippage 0.30 (USD, adverse)

## Exact mechanical rules

- **name:** london_sweep_reclaim_long
- **version:** v1
- **description:** London sweep of Asian low -> reclaim -> bullish displacement -> FVG mitigation long; stop below swept low, fixed RR target.
- **asian_window_utc:** [00:00, 07:00)
- **london_window_utc:** [07:00, 11:00)
- **min_asian_candles:** 12
- **min_asian_range_usd:** 1.5
- **reclaim_within_bars:** 6
- **displacement_factor:** 1.5
- **baseline_lookback:** 20
- **mitigation_within_bars:** 12
- **sl_buffer_usd:** 0.1
- **rr:** 2.0
- **session:** LONDON

## Result table (base costs)

| metric | value |
|---|---|
| occurrences | 9 |
| trades | 8 |
| win_rate | 25.0% |
| avg_R | -0.398 |
| median_R | -1.064 |
| expectancy_R | -0.398 |
| profit_factor | 0.52 |
| total_R | -3.2 |
| max_DD_R | 5.1 |
| max_consec_losses | 4 |
| wins / losses / breakeven | 2 / 6 / 0 |
| cancelled before fill | 1 (invalidated=0, expired_unfilled=1) |
| best / worst R | +1.88 / -1.24 |

> ⚠️ **Only 8 filled trades** (< 100). Per lab policy this is **Insufficient Data**: no edge claim is valid from this sample. Load more history and re-run.

## Spread / slippage sensitivity

| cost profile | spread | slippage | trades | win rate | expectancy R | total R |
|---|---|---|---|---|---|---|
| tight | 0.10 | 0.10 | 8 | 25.0% | -0.305 | -2.4 |
| base | 0.20 | 0.30 | 8 | 25.0% | -0.398 | -3.2 |
| wide | 0.40 | 0.50 | 8 | 25.0% | -0.508 | -4.1 |
| stress | 0.70 | 0.80 | 8 | 25.0% | -0.675 | -5.4 |

## Session sensitivity

| session | trades | win rate | expectancy R | total R |
|---|---|---|---|---|
| LONDON | 8 | 25.0% | -0.398 | -3.2 |

## Winning examples

- **2026-06-17** LONG entry@4342.90 (2026-06-17T09:00:00+00:00) → +1.88R [TAKE_PROFIT] MFE +2.28R / MAE -0.61R — target hit (6.90 risk)
- **2026-05-21** LONG entry@4521.10 (2026-05-21T08:00:00+00:00) → +1.58R [TAKE_PROFIT] MFE +2.05R / MAE -1.00R — target hit (1.90 risk)

## Losing examples (why they lost)

- **2026-05-15** LONG entry@4560.50 (2026-05-15T10:20:00+00:00) → -1.24R [STOP_LOSS] MFE +1.73R / MAE -1.48R — stopped at swept low
- **2026-06-03** LONG entry@4488.00 (2026-06-03T10:20:00+00:00) → -1.16R [STOP_LOSS] MFE +0.84R / MAE -1.18R — stopped at swept low
- **2026-04-16** LONG entry@4838.00 (2026-04-16T11:25:00+00:00) → -1.08R [STOP_LOSS] MFE +0.85R / MAE -2.81R — stopped at swept low
- **2026-05-26** LONG entry@4532.40 (2026-05-26T08:10:00+00:00) → -1.08R [STOP_LOSS] MFE +0.15R / MAE -1.21R — stopped at swept low
- **2026-05-19** LONG entry@4546.80 (2026-05-19T11:05:00+00:00) → -1.04R [STOP_LOSS] MFE +0.23R / MAE -1.24R — stopped at swept low

## Automation verdict

- Automation is **NOT justified** (Insufficient Data). Execution stays retired. Refine rules as a NEW version or gather more data.
