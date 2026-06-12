# 26_SMC_V2_DESIGN.md

## Purpose

Design contract for the SMC v2 decision brain (decision 2026-06-12-10,
owner-directed). Replaces the per-candle gate model's DECISION LAYER only.
The execution chassis (gateway, MT5-truth accounting, equity sizing,
tactical stops, trailing, all brakes) is unchanged and authoritative.

## Why v1 lost (live evidence, 24 trades, -4.8%)

v1 re-evaluated four gates on every candle with no memory:

1. No day-level concept: it probed whipsaw candle-by-candle (15 stops,
   most in post-spike consolidation and violent reversal phases) instead
   of classifying the DAY and standing down as a day.
2. No conviction: a stale D1/H4 bias proposed counter-trend candidates
   all day (D3/D5 had to be bolted on as guards).
3. No self-awareness: it re-tried the same failing idea (same-zone churn
   — H8 had to be bolted on); it never noticed "my playbook is losing
   today."
4. Wins were real but structural: trend-leg pullbacks taken WITH the day
   direction (+84.61 Thursday rollover, +44.93 new-doctrine morning).
   The edge exists in exactly one narrative: aligned continuation after
   a confirmed liquidity event. v1 spent most of its risk budget outside
   that narrative.

## v2 architecture (three layers above the chassis)

### 1. DayNarrative (state machine, persists across candles)

States: OPENING (pre-Asian-range), ASIAN_RANGE, LONDON_OPEN_SWEEP,
TREND_DAY_UP, TREND_DAY_DOWN, RANGE_DAY, TRAP_REVERSAL, POST_SPIKE_CHOP,
EXHAUSTED, NO_TRADE_REGIME (news/dangerous volatility).

Transition evidence (all computable from M5/M1 + session levels):
- Asian range set -> expansion ratio at London/NY,
- sweeps of PDH/PDL/Asian H-L/session H-L and whether the sweep HELD
  (reclaim) or CONTINUED (run),
- displacement legs (count, direction, size vs ATR baseline),
- ATR regime vs 20-day baseline (spike day vs normal),
- failed-break count (range evidence), consecutive opposing legs
  (trap/reversal evidence).

Each state carries: allowed playbooks, allowed direction(s), pyramid
permission, and an explicit re-arm condition for blocked states.

### 2. Conviction ledger (replaces stale-bias candidates)

Directional conviction in [-1, +1] accumulated from weighted evidence:
HTF alignment contributes once per session (decayed when LTF disagrees),
each confirmed liquidity event (sweep+reclaim, BOS with displacement)
adds in its direction, opposing displacement subtracts. Entries require
|conviction| >= threshold AND direction agreement with the active
state's allowed directions. NO entry on conviction sign-flips within
the same session without a fresh liquidity event (anti-whipsaw).

### 3. Playbooks (setup menu per state, NOT per candle)

- TREND_DAY_*: continuation pullback into FVG/OB with the trend;
  pyramids allowed onto protected winners (2-leg cap, H7).
- LONDON_OPEN_SWEEP / TRAP_REVERSAL: sweep-reclaim entry against the
  swept side ONLY after reclaim holds N candles; stop beyond the
  engineered extreme (H1 hypothesis, now doctrine).
- RANGE_DAY: fade only at range extremes after a sweep+reclaim of the
  boundary; no mid-range entries; no pyramids.
- POST_SPIKE_CHOP / EXHAUSTED / NO_TRADE_REGIME: no entries; explicit
  re-arm condition printed every cycle.

Trade memory (within-day): H8 zone consumption (ported); max 2 probes
per directional thesis per session — a third attempt requires a NEW
liquidity event; a playbook that takes 2 losses in a day stands down
for the day (playbook-level cooldown, distinct from the account-level
loss cooldown which is unchanged).

### 4. Quality score (replaces binary gate pass)

score = w·(narrative alignment) + w·(liquidity event quality) +
w·(structure freshness) + w·(stop quality: beyond engineered extreme vs
naked swing) + w·(session timing) — entry requires score >= S_normal,
STRONG tier at >= S_strong. Weights fixed in code, tuned ONLY by replay
evidence, never live.

## What is reused unchanged

Tactical stop construction (FVG/OB boundary, sweep extreme, swing +
buffer, 8 USD ceiling), 2R targets + trailing/BE chassis, equity-risk
tiers (1.0%/1.5%, 3% cap), ChallengeTradePlanner, ExecutionGateway,
RiskGovernor, all envelope brakes (daily 5% net pause, weekly 10% stop,
25/day, max 3 open, loss cooldown), kill switch, news/volatility
fail-closed gates, H8 zone consumption.

## Validation gate (before ANY live demo trading)

scripts/decision_replay.py: replay real MT5 history (>= 10 trading
days, M5+M1+HTF) through v1 and v2 head-to-head with conservative
simulated fills (entry next candle open; intrabar SL-first when SL and
TP are both touched; spread + 0.3 slippage charged). Report per model:
trades, net R, win rate, max drawdown (R), per-day and per-state
breakdown. v2 ships only if: net R(v2) > net R(v1) AND max DD(v2) <=
max DD(v1) AND v2 does not lose on the days v1 won big (no edge
destruction). Otherwise iterate or stay on v1.

## Profile

--profile smc_v2 (same envelope as smc_challenge; envelope numbers are
shared, not duplicated). smc_challenge remains available as fallback.
