# Research Result — fibonacci_retracement (v1)

- **Classification:** **Weak Edge**
- **Data span:** 2024-01-25T05:00:00+00:00 -> 2026-06-17T20:53:13+00:00
- **Base costs:** spread 0.20 + slippage 0.30 (USD, adverse)

## Exact mechanical rules

- **name:** fibonacci_retracement
- **version:** v1
- **description:** Mechanical Fib retracement: swing detection -> trend (LH+LL / HH+HL) -> tag 0.5-0.786 zone -> close back through 0.5 -> market entry; stop beyond swing, fixed RR.
- **exec_timeframe:** 1H
- **swing_strength:** 3
- **fib_zone:** [0.5, 0.786]
- **confirm_level:** 0.5
- **confirm_within_bars:** 24
- **sl_buffer_usd:** 0.1
- **rr:** 2.0
- **require_trend:** True
- **entry:** MARKET next bar
- **session:** ANY

## Result table (base costs)

| metric | value |
|---|---|
| occurrences | 404 |
| trades | 404 |
| win_rate | 37.9% |
| avg_R | +0.098 |
| median_R | -1.015 |
| expectancy_R | +0.098 |
| profit_factor | 1.15 |
| total_R | +39.7 |
| max_DD_R | 27.4 |
| max_consec_losses | 16 |
| wins / losses / breakeven | 153 / 251 / 0 |
| cancelled before fill | 0 (invalidated=0, expired_unfilled=0) |
| best / worst R | +2.00 / -1.18 |

## Spread / slippage sensitivity

| cost profile | spread | slippage | trades | win rate | expectancy R | total R |
|---|---|---|---|---|---|---|
| tight | 0.10 | 0.10 | 404 | 37.9% | +0.122 | +49.3 |
| base | 0.20 | 0.30 | 404 | 37.9% | +0.098 | +39.7 |
| wide | 0.40 | 0.50 | 404 | 37.9% | +0.070 | +28.2 |
| stress | 0.70 | 0.80 | 404 | 37.9% | +0.027 | +10.9 |

## Session sensitivity

| session | trades | win rate | expectancy R | total R |
|---|---|---|---|---|
| ANY | 404 | 37.9% | +0.098 | +39.7 |

## Winning examples

- **2026-01-29** SHORT entry@5334.30 (2026-01-29T20:00:00+00:00) → +2.00R [TAKE_PROFIT] MFE +2.07R / MAE -0.59R — target hit (246.60 risk)
- **2026-03-04** SHORT entry@5164.30 (2026-03-04T03:00:00+00:00) → +2.00R [TAKE_PROFIT] MFE +2.08R / MAE -0.37R — target hit (229.50 risk)
- **2026-03-20** SHORT entry@4679.50 (2026-03-20T02:00:00+00:00) → +2.00R [TAKE_PROFIT] MFE +2.72R / MAE -0.31R — target hit (188.80 risk)
- **2025-12-02** LONG entry@4251.30 (2025-12-02T02:00:00+00:00) → +1.99R [TAKE_PROFIT] MFE +2.04R / MAE -0.76R — target hit (110.90 risk)
- **2026-01-21** LONG entry@4829.10 (2026-01-21T18:00:00+00:00) → +1.99R [TAKE_PROFIT] MFE +2.05R / MAE -0.66R — target hit (108.70 risk)

## Losing examples (why they lost)

- **2024-02-02** LONG entry@2073.80 (2024-02-02T12:00:00+00:00) → -1.18R [STOP_LOSS] MFE +0.20R / MAE -6.30R — stopped at swept low
- **2024-03-27** SHORT entry@2174.80 (2024-03-27T06:00:00+00:00) → -1.17R [STOP_LOSS] MFE +0.00R / MAE -5.78R — stopped at swept low
- **2024-02-21** LONG entry@2039.50 (2024-02-21T10:00:00+00:00) → -1.16R [STOP_LOSS] MFE +0.61R / MAE -1.16R — stopped at swept low
- **2024-02-06** LONG entry@2045.80 (2024-02-06T06:00:00+00:00) → -1.15R [STOP_LOSS] MFE +0.00R / MAE -1.20R — stopped at swept low
- **2024-02-22** SHORT entry@2035.90 (2024-02-22T01:00:00+00:00) → -1.13R [STOP_LOSS] MFE +0.11R / MAE -1.55R — stopped at swept low

## Automation verdict

- Automation is **NOT justified** (Weak Edge). Execution stays retired. Refine rules as a NEW version or gather more data.
