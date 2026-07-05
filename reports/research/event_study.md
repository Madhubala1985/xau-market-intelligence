# Event study: post-announcement drift in XAUUSD (ALPHA-HUNT-001, Phase B2)

**Date: 2026-07-05. Train years only (2019–2024). 2026 untouched.**

## Design (declared before results)

Scheduled US macro releases hit at fixed ET clock times. Events are
identified from the data itself — the M1 bar at the release minute with
range > 5× the median M1 range (2.18 bps) — which a live strategy can
replicate causally (it knows the clock and sees the first reaction; entry
is 2 minutes after the release). Hypothesis: post-announcement drift —
the first 2-minute reaction direction continues.

Continuation = sign(2-min reaction) × subsequent return from the +2 min
entry, at horizons 15m/30m/1h/2h/4h.

## Results

| event clock | days | 15m | 30m | 1h | 2h | 4h |
|---|---|---|---|---|---|---|
| 08:30 ET (CPI/NFP/PPI/retail/GDP) | 533 | −0.49 (t=−0.45) | −0.71 (t=−0.53) | +0.04 (t=+0.02) | −0.34 (t=−0.14) | +0.40 (t=+0.13) |
| 14:00 ET (FOMC) | 82 | −0.07 (t=−0.02) | +0.69 (t=+0.21) | −0.17 (t=−0.03) | −0.19 (t=−0.03) | +6.66 (t=+0.86) |
| 10:00 ET (ISM/UMich/JOLTS) | 539 | +0.35 (t=+0.41) | +1.27 (t=+1.10) | +2.83 (t=+1.84) | +3.12 (t=+1.60) | +3.26 (t=+1.41) |

(mean continuation in bps; t-stats per cell; 15 cells tested — Bonferroni
z ≈ 2.94, nothing comes close.)

## Verdict

**No exploitable post-announcement drift or reversal in gold.** The largest
cell (10:00 ET, 1h, +2.83 bps, t=1.84) is insignificant AND below the
~4.5 bps cost bar. n=533 at 08:30 ET is decisive power for effects of the
size that would matter: gold digests macro prints efficiently within
minutes. This extends the no-edge result to the event space.
