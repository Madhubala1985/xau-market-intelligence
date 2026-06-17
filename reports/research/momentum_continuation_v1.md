# Research Result — momentum_continuation (v1)

- **Classification:** **No Edge**
- **Data span:** 2026-04-08T04:00:00+00:00 -> 2026-06-17T20:53:13+00:00
- **Base costs:** spread 0.20 + slippage 0.30 (USD, adverse)

## Exact mechanical rules

- **name:** momentum_continuation
- **version:** v1
- **description:** Session-agnostic: H1 trend + strong M5 displacement leaving an FVG -> continuation entry on FVG retest; stop beyond the leg; rr=3 to run.
- **active_window_utc:** [00:00,24:00)
- **htf:** H1 BOS/CHOCH
- **displacement_factor:** 2.0
- **swing_strength:** 2
- **mitigation_within_bars:** 12
- **cooldown_bars:** 12
- **sl_buffer_usd:** 0.1
- **rr:** 3.0
- **session:** ANY
- **cadence:** multiple per day

## Result table (base costs)

| metric | value |
|---|---|
| occurrences | 187 |
| trades | 147 |
| win_rate | 23.8% |
| avg_R | -0.137 |
| median_R | -1.067 |
| expectancy_R | -0.137 |
| profit_factor | 0.83 |
| total_R | -20.1 |
| max_DD_R | 32.1 |
| max_consec_losses | 13 |
| wins / losses / breakeven | 35 / 112 / 0 |
| cancelled before fill | 40 (invalidated=3, expired_unfilled=37) |
| best / worst R | +2.99 / -1.35 |

## Spread / slippage sensitivity

| cost profile | spread | slippage | trades | win rate | expectancy R | total R |
|---|---|---|---|---|---|---|
| tight | 0.10 | 0.10 | 147 | 23.8% | -0.081 | -11.9 |
| base | 0.20 | 0.30 | 147 | 23.8% | -0.137 | -20.1 |
| wide | 0.40 | 0.50 | 147 | 23.8% | -0.204 | -30.0 |
| stress | 0.70 | 0.80 | 147 | 23.8% | -0.305 | -44.8 |

## Session sensitivity

| session | trades | win rate | expectancy R | total R |
|---|---|---|---|---|
| ANY | 147 | 23.8% | -0.137 | -20.1 |

## Winning examples

- **2026-04-20** SHORT entry@4811.50 (2026-04-20T09:45:00+00:00) → +2.99R [TAKE_PROFIT] MFE +3.00R / MAE -1.01R — target hit (67.70 risk)
- **2026-06-12** LONG entry@4222.30 (2026-06-12T15:00:00+00:00) → +2.97R [TAKE_PROFIT] MFE +4.25R / MAE -0.05R — target hit (24.40 risk)
- **2026-04-21** SHORT entry@4763.40 (2026-04-21T15:10:00+00:00) → +2.97R [TAKE_PROFIT] MFE +3.25R / MAE -0.55R — target hit (23.90 risk)
- **2026-05-15** SHORT entry@4575.50 (2026-05-15T05:40:00+00:00) → +2.96R [TAKE_PROFIT] MFE +3.32R / MAE -0.98R — target hit (18.60 risk)
- **2026-06-10** SHORT entry@4194.00 (2026-06-10T08:10:00+00:00) → +2.95R [TAKE_PROFIT] MFE +3.18R / MAE -0.91R — target hit (17.10 risk)

## Losing examples (why they lost)

- **2026-06-04** LONG entry@4507.40 (2026-06-04T20:05:00+00:00) → -1.35R [STOP_LOSS] MFE +0.30R / MAE -1.48R — stopped at swept low
- **2026-05-12** LONG entry@4733.90 (2026-05-12T04:25:00+00:00) → -1.24R [STOP_LOSS] MFE +0.53R / MAE -1.97R — stopped at swept low
- **2026-05-06** LONG entry@4660.20 (2026-05-06T04:35:00+00:00) → -1.20R [STOP_LOSS] MFE +1.78R / MAE -1.12R — stopped at swept low
- **2026-04-29** SHORT entry@4610.00 (2026-04-29T05:40:00+00:00) → -1.17R [STOP_LOSS] MFE +0.15R / MAE -1.48R — stopped at swept low
- **2026-05-22** SHORT entry@4524.60 (2026-05-22T08:45:00+00:00) → -1.17R [STOP_LOSS] MFE +2.04R / MAE -2.57R — stopped at swept low

## Automation verdict

- Automation is **NOT justified** (No Edge). Execution stays retired. Refine rules as a NEW version or gather more data.
