# Research Result — mean_reversion_m5 (v1)

- **Classification:** **No Edge**
- **Data span:** 2026-04-08T04:00:00+00:00 -> 2026-06-17T20:53:13+00:00
- **Base costs:** spread 0.20 + slippage 0.30 (USD, adverse)

## Exact mechanical rules

- **name:** mean_reversion_m5
- **version:** v1
- **description:** M5 big-bar fade (mean reversion); market entry, ATR stop/target.
- **exec_timeframe:** M5
- **atr_len:** 14
- **trigger_atr:** 1.5
- **stop_atr:** 1.5
- **tp_atr:** 1.5
- **cooldown:** 6
- **max_hold_bars:** 8
- **entry:** MARKET next bar
- **session:** ANY

## Result table (base costs)

| metric | value |
|---|---|
| occurrences | 331 |
| trades | 331 |
| win_rate | 47.4% |
| avg_R | -0.136 |
| median_R | -0.234 |
| expectancy_R | -0.136 |
| profit_factor | 0.74 |
| total_R | -45.2 |
| max_DD_R | 46.8 |
| max_consec_losses | 7 |
| wins / losses / breakeven | 157 / 174 / 0 |
| cancelled before fill | 0 (invalidated=0, expired_unfilled=0) |
| best / worst R | +0.96 / -1.30 |

## Spread / slippage sensitivity

| cost profile | spread | slippage | trades | win rate | expectancy R | total R |
|---|---|---|---|---|---|---|
| tight | 0.10 | 0.10 | 331 | 47.4% | -0.068 | -22.7 |
| base | 0.20 | 0.30 | 331 | 47.4% | -0.136 | -45.2 |
| wide | 0.40 | 0.50 | 331 | 46.8% | -0.218 | -72.1 |
| stress | 0.70 | 0.80 | 331 | 45.9% | -0.340 | -112.6 |

## Session sensitivity

| session | trades | win rate | expectancy R | total R |
|---|---|---|---|---|
| ANY | 331 | 47.4% | -0.136 | -45.2 |

## Winning examples

- **2026-05-19** SHORT entry@4506.70 (2026-05-19T13:55:00+00:00) → +0.96R [TAKE_PROFIT] MFE +0.98R / MAE -0.51R — target hit (20.00 risk)
- **2026-04-17** LONG entry@4886.90 (2026-04-17T13:20:00+00:00) → +0.96R [TAKE_PROFIT] MFE +1.00R / MAE -0.87R — target hit (18.56 risk)
- **2026-06-09** LONG entry@4265.40 (2026-06-09T16:40:00+00:00) → +0.96R [TAKE_PROFIT] MFE +1.27R / MAE -0.31R — target hit (17.79 risk)
- **2026-05-04** LONG entry@4531.80 (2026-05-04T15:25:00+00:00) → +0.95R [TAKE_PROFIT] MFE +1.08R / MAE -0.38R — target hit (16.90 risk)
- **2026-04-23** LONG entry@4694.70 (2026-04-23T17:45:00+00:00) → +0.95R [TAKE_PROFIT] MFE +1.89R / MAE -0.88R — target hit (16.53 risk)

## Losing examples (why they lost)

- **2026-04-27** SHORT entry@4697.00 (2026-04-27T22:00:00+00:00) → -1.30R [STOP_LOSS] MFE +0.00R / MAE -1.87R — stopped at swept low
- **2026-04-28** SHORT entry@4711.30 (2026-04-28T00:05:00+00:00) → -1.22R [STOP_LOSS] MFE +0.00R / MAE -1.45R — stopped at swept low
- **2026-06-04** LONG entry@4503.50 (2026-06-04T22:45:00+00:00) → -1.20R [STOP_LOSS] MFE +0.13R / MAE -1.70R — stopped at swept low
- **2026-06-17** SHORT entry@4357.10 (2026-06-17T00:10:00+00:00) → -1.20R [STOP_LOSS] MFE +0.03R / MAE -1.21R — stopped at swept low
- **2026-04-27** LONG entry@4737.80 (2026-04-27T05:05:00+00:00) → -1.20R [STOP_LOSS] MFE +0.10R / MAE -1.53R — stopped at swept low

## Automation verdict

- Automation is **NOT justified** (No Edge). Execution stays retired. Refine rules as a NEW version or gather more data.
