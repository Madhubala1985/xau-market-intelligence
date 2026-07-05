# Intraday conditional-return map (Phase B, ALPHA-HUNT-001)

Sample: Dukascopy M1 2019-01..2025-12 (2026 = untouched holdout).
Cells tested: 212; Bonferroni z threshold (alpha=0.05, two-sided): **3.68**.
Return unit: bps (1bp = 0.01%). MAP ONLY — survivors go to Phase C/D (costs, random baseline, holdout).

## All cells ranked by |z|

| group | cell | n | mean bps | sem | z | sig |
|---|---|---|---|---|---|---|
| momentum_M5 | M5 k=1 m=1 | 493051 | -0.07 | 0.01 | -8.56 | **YES** |
| hour_of_day | hour=23 | 1807 | +2.23 | 0.34 | +6.50 | **YES** |
| momentum_M5 | M5 k=3 m=1 | 494947 | -0.05 | 0.01 | -5.88 | **YES** |
| dow_hour | dow=2,hour=22 | 238 | +5.13 | 0.95 | +5.43 | **YES** |
| momentum_M5 | M5 k=1 m=3 | 164351 | -0.13 | 0.03 | -5.13 | **YES** |
| dow_hour | dow=3,hour=23 | 355 | +2.56 | 0.54 | +4.76 | **YES** |
| momentum_M5 | M5 k=6 m=1 | 495601 | -0.03 | 0.01 | -3.88 | **YES** |
| dow_hour | dow=0,hour=22 | 238 | +2.81 | 0.73 | +3.82 | **YES** |
| dow_hour | dow=2,hour=23 | 364 | +2.36 | 0.69 | +3.42 |  |
| dow_hour | dow=1,hour=23 | 362 | +2.55 | 0.75 | +3.39 |  |
| dow_hour | dow=4,hour=21 | 117 | +3.33 | 1.00 | +3.33 |  |
| hour_of_day | hour=22 | 1183 | +2.02 | 0.62 | +3.24 |  |
| vol_conditioning | midvol,after_up | 1909 | +2.54 | 0.79 | +3.22 |  |
| dow_hour | dow=0,hour=23 | 365 | +1.80 | 0.57 | +3.15 |  |
| dow_hour | dow=3,hour=22 | 231 | +2.40 | 0.78 | +3.09 |  |
| vol_conditioning | lowvol,after_up | 1970 | +1.87 | 0.69 | +2.72 |  |
| momentum_H1 | H1 k=1 m=1 | 41359 | -0.26 | 0.10 | -2.66 |  |
| momentum_H1 | H1 k=24 m=6 | 6896 | +1.52 | 0.58 | +2.60 |  |
| momentum_M5 | M5 k=12 m=1 | 495897 | -0.02 | 0.01 | -2.58 |  |
| momentum_M5 | M5 k=24 m=1 | 496089 | -0.02 | 0.01 | -2.41 |  |
| dow_hour | dow=2,hour=17 | 362 | -1.91 | 0.82 | -2.34 |  |
| hour_of_day | hour=20 | 1751 | -0.72 | 0.32 | -2.29 |  |
| dow_hour | dow=4,hour=02 | 355 | +1.74 | 0.77 | +2.26 |  |
| momentum_H1 | H1 k=12 m=12 | 3449 | +2.62 | 1.17 | +2.25 |  |
| momentum_H1 | H1 k=24 m=12 | 3448 | +2.60 | 1.17 | +2.23 |  |
| dow_hour | dow=3,hour=06 | 364 | +2.05 | 0.92 | +2.21 |  |
| dow_hour | dow=0,hour=01 | 361 | +3.02 | 1.39 | +2.18 |  |
| dow_hour | dow=2,hour=20 | 360 | -1.80 | 0.83 | -2.16 |  |
| momentum_H1 | H1 k=12 m=6 | 6897 | +1.23 | 0.58 | +2.12 |  |
| session_block | asia_00_07 | 1807 | +1.95 | 0.94 | +2.07 |  |
| momentum_H1 | H1 k=24 m=1 | 41371 | +0.20 | 0.10 | +2.04 |  |
| hour_of_day | hour=02 | 1807 | +0.73 | 0.37 | +1.98 |  |
| dow_hour | dow=1,hour=20 | 362 | -1.31 | 0.69 | -1.91 |  |
| dow_hour | dow=0,hour=16 | 361 | +1.56 | 0.82 | +1.90 |  |
| momentum_H1 | H1 k=24 m=3 | 13790 | +0.56 | 0.30 | +1.88 |  |
| momentum_H1 | H1 k=12 m=3 | 13793 | +0.54 | 0.30 | +1.84 |  |
| dow_hour | dow=3,hour=17 | 364 | +1.74 | 0.96 | +1.82 |  |
| dow_hour | dow=2,hour=21 | 123 | -1.52 | 0.84 | -1.80 |  |
| dow_hour | dow=2,hour=12 | 362 | +2.50 | 1.42 | +1.76 |  |
| dow_hour | dow=3,hour=10 | 364 | +1.57 | 0.90 | +1.74 |  |
| dow_hour | dow=0,hour=00 | 361 | -1.75 | 1.02 | -1.72 |  |
| dow_hour | dow=2,hour=14 | 362 | -2.61 | 1.53 | -1.71 |  |
| momentum_H1 | H1 k=3 m=12 | 3449 | +2.00 | 1.18 | +1.70 |  |
| momentum_H1 | H1 k=12 m=1 | 41382 | +0.17 | 0.10 | +1.69 |  |
| hour_of_day | hour=01 | 1807 | +0.89 | 0.53 | +1.68 |  |
| dow_hour | dow=1,hour=21 | 125 | -1.28 | 0.77 | -1.67 |  |
| hour_of_day | hour=06 | 1807 | +0.69 | 0.43 | +1.61 |  |
| dow_hour | dow=1,hour=22 | 238 | +1.71 | 1.09 | +1.56 |  |
| dow_hour | dow=0,hour=15 | 361 | -1.83 | 1.18 | -1.56 |  |
| dow_hour | dow=4,hour=13 | 355 | -2.81 | 1.81 | -1.55 |  |
| momentum_H1 | H1 k=48 m=1 | 41344 | +0.15 | 0.10 | +1.52 |  |
| momentum_M5 | M5 k=3 m=6 | 82479 | -0.07 | 0.05 | -1.50 |  |
| dow_hour | dow=0,hour=03 | 361 | -0.99 | 0.66 | -1.50 |  |
| momentum_M5 | M5 k=48 m=3 | 165402 | +0.04 | 0.02 | +1.49 |  |
| dow_hour | dow=3,hour=01 | 364 | -1.55 | 1.04 | -1.49 |  |
| momentum_H1 | H1 k=48 m=6 | 6891 | +0.85 | 0.58 | +1.47 |  |
| momentum_M5 | M5 k=24 m=24 | 20669 | +0.28 | 0.19 | +1.46 |  |
| dow_hour | dow=0,hour=02 | 361 | +1.33 | 0.93 | +1.43 |  |
| dow_hour | dow=2,hour=07 | 362 | +1.40 | 1.02 | +1.37 |  |
| dow_hour | dow=1,hour=16 | 365 | +1.42 | 1.05 | +1.36 |  |
| dow_hour | dow=0,hour=10 | 361 | -1.63 | 1.20 | -1.36 |  |
| dow_hour | dow=2,hour=05 | 362 | +1.02 | 0.75 | +1.35 |  |
| dow_hour | dow=2,hour=01 | 362 | +1.40 | 1.04 | +1.35 |  |
| dow_hour | dow=4,hour=18 | 352 | +1.12 | 0.87 | +1.29 |  |
| momentum_M5 | M5 k=48 m=24 | 20672 | +0.25 | 0.19 | +1.29 |  |
| momentum_H1 | H1 k=3 m=24 | 1724 | +3.07 | 2.38 | +1.29 |  |
| dow_hour | dow=2,hour=03 | 362 | -0.78 | 0.61 | -1.28 |  |
| dow_hour | dow=4,hour=07 | 355 | +1.15 | 0.90 | +1.27 |  |
| dow_hour | dow=2,hour=10 | 362 | -1.10 | 0.86 | -1.27 |  |
| dow_hour | dow=1,hour=19 | 362 | +0.99 | 0.78 | +1.27 |  |
| dow_hour | dow=2,hour=15 | 362 | +1.55 | 1.23 | +1.26 |  |
| dow_hour | dow=4,hour=04 | 355 | +0.80 | 0.63 | +1.26 |  |
| dow_hour | dow=1,hour=05 | 365 | -1.10 | 0.90 | -1.22 |  |
| dow_hour | dow=2,hour=06 | 362 | +1.25 | 1.05 | +1.20 |  |
| dow_hour | dow=1,hour=12 | 365 | -1.52 | 1.30 | -1.16 |  |
| dow_hour | dow=2,hour=09 | 362 | +1.09 | 0.94 | +1.16 |  |
| dow_hour | dow=4,hour=06 | 355 | +1.05 | 0.91 | +1.15 |  |
| momentum_H1 | H1 k=3 m=1 | 41364 | -0.11 | 0.10 | -1.14 |  |
| dow_hour | dow=4,hour=11 | 355 | -1.07 | 0.95 | -1.13 |  |
| dow_hour | dow=0,hour=08 | 361 | +1.06 | 0.93 | +1.13 |  |
| dow_hour | dow=2,hour=00 | 362 | -0.87 | 0.77 | -1.12 |  |
| session_block | london_07_12 | 1807 | +1.04 | 0.94 | +1.10 |  |
| hour_of_day | hour=09 | 1807 | +0.41 | 0.37 | +1.10 |  |
| dow_hour | dow=1,hour=18 | 365 | -0.82 | 0.75 | -1.09 |  |
| dow_hour | dow=1,hour=01 | 365 | +1.35 | 1.24 | +1.09 |  |
| momentum_M5 | M5 k=12 m=24 | 20661 | -0.21 | 0.20 | -1.08 |  |
| hour_of_day | hour=03 | 1807 | -0.31 | 0.29 | -1.05 |  |
| dow_hour | dow=4,hour=14 | 355 | +1.92 | 1.85 | +1.04 |  |
| momentum_H1 | H1 k=6 m=12 | 3448 | +1.20 | 1.17 | +1.03 |  |
| dow_hour | dow=3,hour=11 | 364 | +0.91 | 0.89 | +1.02 |  |
| dow_hour | dow=4,hour=19 | 349 | -0.81 | 0.80 | -1.01 |  |
| momentum_M5 | M5 k=3 m=3 | 164995 | -0.02 | 0.02 | -1.00 |  |
| momentum_M5 | M5 k=24 m=12 | 41342 | +0.10 | 0.10 | +0.99 |  |
| momentum_M5 | M5 k=6 m=6 | 82599 | -0.05 | 0.05 | -0.98 |  |
| dow_hour | dow=3,hour=12 | 364 | -1.58 | 1.62 | -0.98 |  |
| hour_of_day | hour=16 | 1807 | +0.45 | 0.47 | +0.96 |  |
| vol_conditioning | lowvol,after_dn | 1477 | +0.79 | 0.83 | +0.94 |  |
| momentum_M5 | M5 k=48 m=6 | 82705 | +0.05 | 0.05 | +0.94 |  |
| dow_hour | dow=3,hour=05 | 364 | -0.69 | 0.75 | -0.93 |  |
| dow_hour | dow=3,hour=21 | 118 | -0.69 | 0.74 | -0.93 |  |
| dow_hour | dow=4,hour=08 | 355 | -0.82 | 0.88 | -0.92 |  |
| dow_hour | dow=1,hour=02 | 365 | +0.70 | 0.76 | +0.92 |  |
| dow_hour | dow=0,hour=06 | 361 | -0.81 | 0.88 | -0.92 |  |
| dow_hour | dow=0,hour=17 | 355 | -0.76 | 0.83 | -0.92 |  |
| momentum_M5 | M5 k=24 m=3 | 165364 | -0.02 | 0.02 | -0.92 |  |
| momentum_M5 | M5 k=1 m=6 | 82217 | -0.04 | 0.05 | -0.89 |  |
| dow_hour | dow=3,hour=08 | 364 | +0.80 | 0.92 | +0.87 |  |
| dow_hour | dow=1,hour=13 | 365 | +1.49 | 1.73 | +0.86 |  |
| momentum_M5 | M5 k=12 m=3 | 165305 | -0.02 | 0.02 | -0.86 |  |
| dow_hour | dow=1,hour=00 | 365 | +0.60 | 0.71 | +0.85 |  |
| dow_hour | dow=0,hour=21 | 109 | -0.55 | 0.66 | -0.84 |  |
| momentum_H1 | H1 k=6 m=24 | 1724 | +1.93 | 2.40 | +0.80 |  |
| dow_hour | dow=0,hour=18 | 347 | +0.64 | 0.81 | +0.80 |  |
| momentum_H1 | H1 k=48 m=3 | 13782 | +0.23 | 0.30 | +0.79 |  |
| dow_hour | dow=3,hour=00 | 364 | +0.62 | 0.79 | +0.78 |  |
| hour_of_day | hour=19 | 1763 | +0.33 | 0.43 | +0.78 |  |
| momentum_H1 | H1 k=12 m=24 | 1724 | +1.82 | 2.34 | +0.78 |  |
| dow_hour | dow=4,hour=12 | 355 | +1.29 | 1.73 | +0.74 |  |
| vol_conditioning | highvol,after_dn | 1721 | +0.98 | 1.33 | +0.74 |  |
| hour_of_day | hour=07 | 1807 | +0.33 | 0.45 | +0.74 |  |
| dow_hour | dow=4,hour=17 | 353 | -0.70 | 0.95 | -0.74 |  |
| dow_hour | dow=4,hour=16 | 355 | -0.86 | 1.20 | -0.72 |  |
| hour_of_day | hour=18 | 1787 | +0.31 | 0.44 | +0.71 |  |
| dow_hour | dow=0,hour=20 | 329 | -0.45 | 0.64 | -0.70 |  |
| hour_of_day | hour=08 | 1807 | +0.31 | 0.43 | +0.70 |  |
| momentum_H1 | H1 k=6 m=1 | 41378 | +0.07 | 0.10 | +0.68 |  |
| momentum_H1 | H1 k=24 m=24 | 1724 | +1.63 | 2.39 | +0.68 |  |
| dow_hour | dow=3,hour=19 | 357 | +0.62 | 0.93 | +0.67 |  |
| momentum_H1 | H1 k=6 m=6 | 6896 | +0.39 | 0.58 | +0.67 |  |
| dow_hour | dow=1,hour=14 | 365 | +1.24 | 1.86 | +0.67 |  |
| momentum_M5 | M5 k=6 m=24 | 20644 | +0.13 | 0.20 | +0.66 |  |
| dow_hour | dow=3,hour=04 | 364 | -0.37 | 0.57 | -0.65 |  |
| momentum_M5 | M5 k=48 m=1 | 496220 | -0.01 | 0.01 | -0.64 |  |
| momentum_H1 | H1 k=1 m=12 | 3444 | -0.75 | 1.18 | -0.63 |  |
| momentum_H1 | H1 k=1 m=24 | 1722 | +1.48 | 2.38 | +0.62 |  |
| hour_of_day | hour=00 | 1807 | -0.22 | 0.36 | -0.62 |  |
| dow_hour | dow=4,hour=05 | 355 | +0.52 | 0.86 | +0.61 |  |
| dow_hour | dow=1,hour=10 | 365 | +0.44 | 0.73 | +0.61 |  |
| momentum_M5 | M5 k=3 m=24 | 20627 | +0.12 | 0.19 | +0.60 |  |
| dow_hour | dow=3,hour=20 | 354 | -0.36 | 0.60 | -0.59 |  |
| dow_hour | dow=1,hour=17 | 365 | +0.54 | 0.95 | +0.57 |  |
| momentum_H1 | H1 k=48 m=12 | 3445 | +0.66 | 1.17 | +0.57 |  |
| momentum_H1 | H1 k=1 m=6 | 6890 | -0.33 | 0.59 | -0.57 |  |
| momentum_M5 | M5 k=48 m=12 | 41349 | +0.06 | 0.10 | +0.56 |  |
| dow_hour | dow=4,hour=09 | 355 | +0.43 | 0.78 | +0.56 |  |
| momentum_M5 | M5 k=3 m=12 | 41257 | -0.05 | 0.10 | -0.55 |  |
| hour_of_day | hour=10 | 1807 | -0.22 | 0.41 | -0.54 |  |
| vol_conditioning | highvol,after_up | 1727 | +0.60 | 1.16 | +0.52 |  |
| dow_hour | dow=4,hour=20 | 346 | +0.38 | 0.73 | +0.52 |  |
| hour_of_day | hour=17 | 1799 | -0.21 | 0.40 | -0.52 |  |
| dow_hour | dow=4,hour=15 | 355 | -0.88 | 1.71 | -0.52 |  |
| dow_hour | dow=3,hour=09 | 364 | +0.38 | 0.76 | +0.50 |  |
| dow_hour | dow=4,hour=10 | 355 | -0.43 | 0.86 | -0.50 |  |
| dow_hour | dow=0,hour=04 | 361 | -0.29 | 0.60 | -0.49 |  |
| dow_hour | dow=1,hour=04 | 365 | -0.25 | 0.51 | -0.48 |  |
| dow_hour | dow=3,hour=15 | 364 | +0.62 | 1.32 | +0.47 |  |
| hour_of_day | hour=21 | 592 | -0.17 | 0.37 | -0.45 |  |
| dow_hour | dow=1,hour=07 | 365 | -0.47 | 1.06 | -0.45 |  |
| dow_hour | dow=0,hour=19 | 335 | +0.38 | 0.87 | +0.44 |  |
| session_block | late_17_21 | 1799 | -0.31 | 0.76 | -0.41 |  |
| dow_hour | dow=1,hour=03 | 365 | +0.30 | 0.73 | +0.41 |  |
| momentum_H1 | H1 k=3 m=3 | 13787 | -0.12 | 0.30 | -0.41 |  |
| dow_hour | dow=4,hour=00 | 355 | +0.28 | 0.69 | +0.41 |  |
| momentum_M5 | M5 k=6 m=12 | 41290 | -0.04 | 0.10 | -0.41 |  |
| dow_hour | dow=1,hour=08 | 365 | +0.45 | 1.12 | +0.40 |  |
| hour_of_day | hour=13 | 1807 | -0.31 | 0.76 | -0.40 |  |
| dow_hour | dow=1,hour=11 | 365 | +0.31 | 0.79 | +0.39 |  |
| momentum_M5 | M5 k=1 m=12 | 41106 | +0.04 | 0.10 | +0.38 |  |
| dow_hour | dow=2,hour=19 | 360 | +0.45 | 1.29 | +0.35 |  |
| momentum_H1 | H1 k=3 m=6 | 6894 | +0.19 | 0.59 | +0.33 |  |
| dow_hour | dow=2,hour=16 | 362 | +0.31 | 0.95 | +0.32 |  |
| dow_hour | dow=0,hour=07 | 361 | -0.35 | 1.10 | -0.32 |  |
| dow_hour | dow=2,hour=18 | 362 | +0.43 | 1.46 | +0.29 |  |
| momentum_M5 | M5 k=12 m=12 | 41326 | -0.03 | 0.10 | -0.28 |  |
| dow_hour | dow=3,hour=18 | 361 | +0.23 | 0.85 | +0.27 |  |
| hour_of_day | hour=14 | 1807 | +0.19 | 0.78 | +0.24 |  |
| dow_hour | dow=4,hour=03 | 355 | -0.16 | 0.67 | -0.24 |  |
| session_block | ny_12_17 | 1807 | +0.35 | 1.57 | +0.23 |  |
| momentum_M5 | M5 k=24 m=6 | 82680 | -0.01 | 0.05 | -0.22 |  |
| vol_conditioning | midvol,after_dn | 1538 | -0.18 | 0.84 | -0.22 |  |
| dow_hour | dow=0,hour=13 | 361 | -0.32 | 1.49 | -0.21 |  |
| dow_hour | dow=4,hour=01 | 355 | +0.25 | 1.21 | +0.21 |  |
| momentum_M5 | M5 k=6 m=3 | 165208 | -0.00 | 0.02 | -0.20 |  |
| dow_hour | dow=0,hour=09 | 361 | +0.17 | 0.87 | +0.19 |  |
| dow_hour | dow=3,hour=16 | 364 | -0.22 | 1.14 | -0.19 |  |
| hour_of_day | hour=05 | 1807 | -0.07 | 0.37 | -0.19 |  |
| dow_hour | dow=1,hour=15 | 365 | +0.29 | 1.62 | +0.18 |  |
| hour_of_day | hour=04 | 1807 | -0.04 | 0.26 | -0.17 |  |
| dow_hour | dow=2,hour=13 | 362 | +0.30 | 1.73 | +0.17 |  |
| dow_hour | dow=2,hour=04 | 362 | -0.09 | 0.55 | -0.17 |  |
| dow_hour | dow=3,hour=03 | 364 | +0.09 | 0.57 | +0.16 |  |
| dow_hour | dow=2,hour=11 | 362 | -0.14 | 0.93 | -0.15 |  |
| dow_hour | dow=0,hour=12 | 361 | -0.20 | 1.39 | -0.15 |  |
| dow_hour | dow=3,hour=13 | 364 | -0.25 | 1.75 | -0.14 |  |
| momentum_M5 | M5 k=1 m=24 | 20543 | +0.03 | 0.20 | +0.14 |  |
| hour_of_day | hour=12 | 1807 | +0.09 | 0.67 | +0.13 |  |
| dow_hour | dow=3,hour=14 | 364 | +0.22 | 1.78 | +0.12 |  |
| dow_hour | dow=0,hour=14 | 361 | +0.20 | 1.69 | +0.12 |  |
| dow_hour | dow=1,hour=06 | 365 | -0.11 | 0.98 | -0.11 |  |
| momentum_M5 | M5 k=12 m=6 | 82657 | -0.01 | 0.05 | -0.11 |  |
| momentum_H1 | H1 k=48 m=24 | 1722 | -0.24 | 2.40 | -0.10 |  |
| dow_hour | dow=0,hour=05 | 361 | -0.06 | 0.81 | -0.08 |  |
| dow_hour | dow=2,hour=02 | 362 | -0.06 | 0.84 | -0.07 |  |
| hour_of_day | hour=15 | 1807 | -0.04 | 0.64 | -0.07 |  |
| dow_hour | dow=3,hour=02 | 364 | -0.05 | 0.81 | -0.07 |  |
| dow_hour | dow=0,hour=11 | 361 | +0.05 | 1.01 | +0.05 |  |
| dow_hour | dow=3,hour=07 | 364 | -0.04 | 0.94 | -0.04 |  |
| hour_of_day | hour=11 | 1807 | +0.02 | 0.41 | +0.04 |  |
| momentum_H1 | H1 k=6 m=3 | 13794 | +0.01 | 0.30 | +0.03 |  |
| momentum_H1 | H1 k=1 m=3 | 13787 | -0.00 | 0.30 | -0.01 |  |
| dow_hour | dow=1,hour=09 | 365 | -0.01 | 0.82 | -0.01 |  |
| dow_hour | dow=2,hour=08 | 362 | +0.01 | 0.96 | +0.01 |  |
