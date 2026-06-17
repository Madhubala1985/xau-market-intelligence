# Research Result — donchian_breakout_trend (v1)

- **Classification:** **No Edge**
- **Data span:** 2024-01-25T05:00:00+00:00 -> 2026-06-17T20:53:13+00:00
- **Base costs:** spread 0.20 + slippage 0.30 (USD, adverse)

## Exact mechanical rules

- **name:** donchian_breakout_trend
- **version:** v1
- **description:** H1 fresh 20-bar Donchian breakout -> market entry next bar; ATR stop & target; trend-continuation (the edge-scan-selected signal).
- **exec_timeframe:** H1
- **lookback:** 20
- **atr_len:** 14
- **stop_atr:** 2.0
- **tp_atr:** 4.0
- **cooldown:** 12
- **max_hold_bars:** None
- **entry:** MARKET next bar
- **session:** ANY

## Result table (base costs)

| metric | value |
|---|---|
| occurrences | 551 |
| trades | 551 |
| win_rate | 33.4% |
| avg_R | -0.044 |
| median_R | -1.020 |
| expectancy_R | -0.044 |
| profit_factor | 0.94 |
| total_R | -24.3 |
| max_DD_R | 54.1 |
| max_consec_losses | 14 |
| wins / losses / breakeven | 184 / 367 / 0 |
| cancelled before fill | 0 (invalidated=0, expired_unfilled=0) |
| best / worst R | +2.00 / -1.19 |

## Spread / slippage sensitivity

| cost profile | spread | slippage | trades | win rate | expectancy R | total R |
|---|---|---|---|---|---|---|
| tight | 0.10 | 0.10 | 551 | 33.4% | -0.015 | -8.5 |
| base | 0.20 | 0.30 | 551 | 33.4% | -0.044 | -24.3 |
| wide | 0.40 | 0.50 | 551 | 33.4% | -0.079 | -43.3 |
| stress | 0.70 | 0.80 | 551 | 33.4% | -0.130 | -71.8 |

## Session sensitivity

| session | trades | win rate | expectancy R | total R |
|---|---|---|---|---|
| ANY | 551 | 33.4% | -0.044 | -24.3 |

## Winning examples

- **2026-01-30** SHORT entry@5038.80 (2026-01-30T10:00:00+00:00) → +2.00R [TAKE_PROFIT] MFE +2.12R / MAE -0.67R — target hit (204.77 risk)
- **2025-11-26** LONG entry@4197.50 (2025-11-26T03:00:00+00:00) → +1.99R [TAKE_PROFIT] MFE +2.00R / MAE -0.58R — target hit (111.66 risk)
- **2026-02-06** LONG entry@4952.20 (2026-02-06T14:00:00+00:00) → +1.99R [TAKE_PROFIT] MFE +2.17R / MAE -0.88R — target hit (111.60 risk)
- **2025-08-01** LONG entry@3394.60 (2025-08-01T13:00:00+00:00) → +1.99R [TAKE_PROFIT] MFE +2.00R / MAE -0.50R — target hit (111.20 risk)
- **2024-07-31** LONG entry@2462.10 (2024-07-31T04:00:00+00:00) → +1.99R [TAKE_PROFIT] MFE +2.04R / MAE -0.88R — target hit (107.01 risk)

## Losing examples (why they lost)

- **2024-02-27** LONG entry@2048.20 (2024-02-27T09:00:00+00:00) → -1.19R [STOP_LOSS] MFE +0.07R / MAE -1.23R — stopped at swept low
- **2024-02-29** SHORT entry@2037.80 (2024-02-29T12:00:00+00:00) → -1.18R [STOP_LOSS] MFE +0.40R / MAE -4.40R — stopped at swept low
- **2024-02-28** SHORT entry@2036.40 (2024-02-28T08:00:00+00:00) → -1.17R [STOP_LOSS] MFE +0.63R / MAE -1.93R — stopped at swept low
- **2024-02-08** SHORT entry@2045.10 (2024-02-08T09:00:00+00:00) → -1.16R [STOP_LOSS] MFE +0.12R / MAE -1.12R — stopped at swept low
- **2024-02-12** SHORT entry@2032.30 (2024-02-12T14:00:00+00:00) → -1.15R [STOP_LOSS] MFE +1.27R / MAE -1.36R — stopped at swept low

## Automation verdict

- Automation is **NOT justified** (No Edge). Execution stays retired. Refine rules as a NEW version or gather more data.
