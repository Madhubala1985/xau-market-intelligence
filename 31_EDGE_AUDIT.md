# 31_EDGE_AUDIT.md — what rests on disproven vs never-tested edges

Built from `02_ARCHITECTURE.md` (layers 3–18) and the RESEARCH-LAB-001 record
(Phases 5–11 in `30_RESEARCH_FINDINGS.md`), cross-referenced against what each
setup actually tested.

**Legend:** ✗ **DISPROVEN** (tested, failed gate) · ◑ **NEVER ISOLATED** (only
tested inside a composite that was No Edge — cannot credit the factor) · ⛔ **NEVER
TESTED** · ⚠ **WEAK / NON-TRADEABLE** (real effect, no edge over costs/noise)

| # | Component (arch layer / SMC factor) | Edge it assumes | Tested in RL-001? | Result / gate classification | Flag |
|---|---|---|---|---|---|
| 1 | BOS / structural breakout (L6) | a structure break predicts continuation | Yes — Donchian breakout, trend_bos_fvg_retest, momentum | No Edge; 15y non-stationary | ✗ |
| 2 | CHOCH (L6) | change-of-character predicts reversal | No — only in london_asian_high_short, which fired 0 trades in 60d | none — zero occurrences | ⛔ |
| 3 | FVG / fair value gap (L7) | price returns to & reacts at the gap | Only bundled in setups 1,2,3,4,6 | composites No Edge / Insufficient; never isolated | ◑ |
| 4 | Liquidity sweeps (L6) | sweep of resting liquidity precedes reversal | Bundled in setups 1 (8 tr), 2 (0), 3 (9) | Insufficient Data; never properly tested | ◑/⛔ |
| 5 | Displacement (L6) | impulsive candle = institutional intent/continuation | Bundled in setups 1,3,6 | No Edge composites; never isolated | ◑ |
| 6 | Order blocks (L7) | price reacts at last opposing candle pre-move | No — never used in any tested setup | none | ⛔ |
| 7 | Supply/Demand zones (L7) | price reverses at S/D zones | No — never used in any tested setup | none | ⛔ |
| 8 | Premium/Discount (L4) | longs in discount / shorts in premium | Not directly; closest proxy = Fib 0.5–0.786 zone | Fib levels inert vs random baseline (z=+0.57) | ✗ (by proxy) |
| 9 | Liquidity Map — equal H/L, prev day/week, retail stops (L5) | these levels attract & reverse price | No — only simple Asian/London session H/L tested | broader map never tested | ⛔ |
| 10 | Session / kill-zones (L3) | London/NY killzone setups have an edge | Yes — setups 1,2,3 session-boxed | No Edge / Insufficient; also missed the live move | ✗ |
| 11 | Asian-range levels (session_levels) | Asian H/L get swept then reverse | Yes — setups 1,2 | Insufficient / 0 trades | ✗/⛔ |
| 12 | HTF / Daily+4H bias (trend) (L4) | trade with higher-TF trend | Yes — momentum, Donchian trend filter, trend_bos | No Edge / fragile | ✗ |
| 13 | Regime engine — vol/chop classify (L10) | filtering by regime improves trades | Partial — ATR vol-filter on Donchian; post_spike_chop | Weak Edge but lookback-fragile; chop uplift ≈ 0/neg | ⚠ |
| 14 | Order-Flow Proxy — tick vol, CVD/delta (L8) | broker tick flow reveals institutional intent | No | never tested; spot XAU has no consolidated tape (unsound) | ⛔ |
| 15 | Gold Futures Confirmation (L9) | futures lead/confirm spot | No — GC=F used as the price proxy, not a confirming signal | none | ⛔ |
| 16 | Confidence/Uncertainty + EV confluence (L11–12) | weighting/combining factors yields good trades | Yes (in practice) — this was gold_alpha | Replay −15.93R, 17% win → SHIP: NO | ✗ |
| 17 | Stop-placement intelligence (L13) | stops "beyond thesis" beat retail-cluster stops | Indirectly — fwd-return-without-stops + ATR vs structural | not the limiter; signals lacked edge regardless of stop | (tested, not cause) |
| 18 | Trailing / trade-management (L16) | structure/vol/liquidity trailing captures more | No — setups used fixed stop/target or time-exit | never tested | ⛔ |
| 19 | Macro regime — real yields + dollar | tightening regime predicts gold | Yes — regime scan + multi-factor walk-forward | real descriptive effect; no tradeable alpha (OOS IC +0.08, < buy&hold); risk overlay only | ⚠ |
| 20 | COT positioning | spec positioning predicts gold | Yes — inside multi-factor model | weak; part of the no-edge model | ⚠ |

## One-page verdict

- **✗ Disproven (6):** BOS/breakout, premium/discount (via Fib), session/kill-zones, Asian-range, HTF trend bias, EV-confluence (gold_alpha).
- **◑ Never isolated (3):** FVG, liquidity sweeps, displacement — the load-bearing SMC entry triggers were only ever tested glued together inside composites that scored No Edge / Insufficient. We never learned if any one of them does anything.
- **⛔ Never tested at all (7):** CHOCH (0 trades), order blocks, supply/demand zones, full liquidity map, order-flow proxy, gold-futures confirmation, trade-management/trailing.
- **⚠ Real but non-tradeable (3):** volatility-regime filtering, macro real-yield/dollar regime, COT positioning.

**Bottom line:** Of ~16 edge-bearing intelligence components, roughly a third are
disproven, a third were never isolated (only tested inside failing composites),
and a third were never tested at all. The architecture diagram implies a stack of
confirming edges; the evidence shows almost none has a demonstrated, isolated
edge — and the two SMC concepts the strategies leaned on hardest (FVG mitigation,
liquidity sweeps) sit in the "never isolated" column, while CHOCH, order blocks,
supply/demand, order-flow, and futures confirmation were never tested even once.

## Single-factor isolation battery (2026-06-25) — gap CLOSED

`scripts/factor_isolation.py` + `research/setups/single_factor.py`. One minimal
rule per factor (factor appears → MARKET next bar in its implied direction; fixed
1.5×ATR stop, 2R target; no other confluence), on GC=F H1 (~2y), 5-fold
walk-forward, cost-stressed, vs a random-entry baseline with identical
stop/target/RR/direction mix. Multiple-comparisons: Bonferroni z≥2.39 (α=0.05/6).
HIT = Proven gate AND z≥2.39 AND positive expectancy in the untouched holdout fold.

| factor | trades | expectancy | PF | max DD | z vs random | holdout exp | gate | HIT |
|---|---|---|---|---|---|---|---|---|
| FVG | 1214 | +0.004R | 1.01 | 72.7R | +0.74 | −0.017 | Weak Edge | **no** |
| liquidity sweep | 1461 | −0.247R | 0.68 | 372.4R | **−5.77** | −0.006 | No Edge | **no** |
| displacement | 1007 | −0.083R | 0.88 | 129.0R | −0.84 | +0.109 | No Edge | **no** |
| CHOCH | 493 | −0.013R | 0.98 | 35.6R | +0.65 | +0.149 | No Edge | **no** |
| order block | 998 | −0.002R | 1.00 | 64.4R | +0.54 | +0.100 | No Edge | **no** |
| supply/demand | 1138 | −0.047R | 0.93 | 100.6R | +0.19 | +0.071 | No Edge | **no** |

**Result: 0 of 6 factors is a hit.** Five are statistically indistinguishable
from random (|z|<1); **liquidity sweep is significantly WORSE than random
(z=−5.77)** — the most-relied-on SMC concept actively loses in isolation. FVG's
"Weak Edge" gate label is exposed as noise (+0.004R, z=+0.74, negative holdout).
Four factors show a *positive holdout* (recent fold) — but all fail the
full-sample gate and the z-test, so the correction + replication rule correctly
rejects them as recency artifacts (precisely the trap the discipline exists to
catch).

## Updated flags (isolation supersedes the pre-test map above)

Rows 2–7 are upgraded from ◑/⛔ to **✗ DISPROVEN IN ISOLATION**: CHOCH, FVG,
liquidity sweep, displacement, order block, and supply/demand each tested alone
on 490–1460 trades → No Edge / indistinguishable-from-or-worse-than random.

**Revised bottom line:** the "never isolated" gap is closed and the answer is
uniform — **none of the six core SMC entry factors has a standalone edge.** The
architecture's intelligence stack now rests on: ✗ disproven factors (the SMC core
+ BOS/sessions/HTF/EV-confluence), ⛔ a few still-untested *non-price* layers
(order-flow proxy, futures confirmation, full liquidity map, trade-management),
and ⚠ macro factors that are real but non-tradeable. No surviving price-based
edge remains to build on.
