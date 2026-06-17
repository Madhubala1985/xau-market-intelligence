# Research Result — trend_bos_fvg_retest (v1)

- **Classification:** **Insufficient Data**
- **Data span:** 2026-04-08T04:00:00+00:00 -> 2026-06-17T20:53:13+00:00
- **Base costs:** spread 0.20 + slippage 0.30 (USD, adverse)

## Exact mechanical rules

- **name:** trend_bos_fvg_retest
- **version:** v1
- **description:** H1 BOS sets trend -> first M5 displacement+FVG in trend direction -> continuation entry on FVG retest; stop beyond the displacement leg.
- **active_window_utc:** [07:00,16:00)
- **htf:** H1 BOS/CHOCH
- **displacement_factor:** 1.5
- **swing_strength:** 2
- **mitigation_within_bars:** 12
- **sl_buffer_usd:** 0.1
- **rr:** 2.0
- **session:** TREND_DAY

## Result table (base costs)

| metric | value |
|---|---|
| occurrences | 50 |
| trades | 35 |
| win_rate | 25.7% |
| avg_R | -0.338 |
| median_R | -1.080 |
| expectancy_R | -0.338 |
| profit_factor | 0.59 |
| total_R | -11.8 |
| max_DD_R | 18.1 |
| max_consec_losses | 10 |
| wins / losses / breakeven | 9 / 26 / 0 |
| cancelled before fill | 15 (invalidated=1, expired_unfilled=14) |
| best / worst R | +1.99 / -1.31 |

> ⚠️ **Only 35 filled trades** (< 100). Per lab policy this is **Insufficient Data**: no edge claim is valid from this sample. Load more history and re-run.

## Spread / slippage sensitivity

| cost profile | spread | slippage | trades | win rate | expectancy R | total R |
|---|---|---|---|---|---|---|
| tight | 0.10 | 0.10 | 35 | 25.7% | -0.269 | -9.4 |
| base | 0.20 | 0.30 | 35 | 25.7% | -0.338 | -11.8 |
| wide | 0.40 | 0.50 | 35 | 25.7% | -0.419 | -14.7 |
| stress | 0.70 | 0.80 | 35 | 25.7% | -0.542 | -19.0 |

## Session sensitivity

| session | trades | win rate | expectancy R | total R |
|---|---|---|---|---|
| TREND_DAY | 35 | 25.7% | -0.338 | -11.8 |

## Winning examples

- **2026-04-20** SHORT entry@4811.50 (2026-04-20T09:45:00+00:00) → +1.99R [TAKE_PROFIT] MFE +2.04R / MAE -1.01R — target hit (67.70 risk)
- **2026-04-28** SHORT entry@4604.50 (2026-04-28T12:20:00+00:00) → +1.93R [TAKE_PROFIT] MFE +2.18R / MAE -0.79R — target hit (11.80 risk)
- **2026-06-09** LONG entry@4355.60 (2026-06-09T08:30:00+00:00) → +1.93R [TAKE_PROFIT] MFE +3.08R / MAE -0.72R — target hit (10.70 risk)
- **2026-06-04** LONG entry@4512.60 (2026-06-04T11:35:00+00:00) → +1.89R [TAKE_PROFIT] MFE +2.58R / MAE -0.34R — target hit (7.60 risk)
- **2026-04-15** LONG entry@4831.90 (2026-04-15T12:00:00+00:00) → +1.87R [TAKE_PROFIT] MFE +2.00R / MAE -0.41R — target hit (6.40 risk)

## Losing examples (why they lost)

- **2026-04-27** SHORT entry@4719.20 (2026-04-27T09:35:00+00:00) → -1.31R [STOP_LOSS] MFE +1.65R / MAE -1.23R — stopped at swept low
- **2026-05-26** SHORT entry@4526.30 (2026-05-26T07:40:00+00:00) → -1.15R [STOP_LOSS] MFE +0.77R / MAE -1.48R — stopped at swept low
- **2026-06-02** LONG entry@4563.30 (2026-06-02T09:20:00+00:00) → -1.15R [STOP_LOSS] MFE +0.23R / MAE -1.53R — stopped at swept low
- **2026-04-17** LONG entry@4813.60 (2026-04-17T08:50:00+00:00) → -1.15R [STOP_LOSS] MFE +1.65R / MAE -1.15R — stopped at swept low
- **2026-04-22** SHORT entry@4770.20 (2026-04-22T10:15:00+00:00) → -1.14R [STOP_LOSS] MFE +0.58R / MAE -1.26R — stopped at swept low

## Automation verdict

- Automation is **NOT justified** (Insufficient Data). Execution stays retired. Refine rules as a NEW version or gather more data.
