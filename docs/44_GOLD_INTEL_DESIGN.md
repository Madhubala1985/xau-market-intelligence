# 44_GOLD_INTEL_DESIGN.md — GOLD-INTEL-001: the three-brain gold model

**Status: BUILT 2026-07-07; live-trading gated by the pre-registered replay
ship gate (reports/research/gold_intel_gate_protocol.md).**

## Owner directive (2026-07-07)

"No years of training — make the model superintelligent: many trades,
opportunity-based, or anyhow — decided by you."

## Standing interpretation (recorded here + decision log)

Intelligence cannot beat arithmetic. At ~2 bps per spread crossing, a model
that fires constantly must earn >5 bps per trade, and 7.5 years of validated
M1 says no intraday gold signal that size exists (42_ALPHA_HUNT results).
Every high-cadence attempt in this repo lost (v1 −82.7R @ 636 trades; posture
engine −27R @ ~9/day; entries/day sweep NEGATIVE at 4+/day). Therefore:
**opportunity-based, exactly as directed — trade count is an OUTPUT of
opportunity, never a target.** The superintelligence budget is spent on
WHICH hours, WHICH setups, and WHEN TO SIT OUT.

## Architecture: ONE engine, three brains, one path

`src/strategy/gold_intel.py :: GoldIntelEngine` — the single decision engine
behind the unchanged chassis (gateway-only sending, RiskGovernor final
authority, MT5 truth, kill switch, demo-only).

### 1. Opportunity brain (restored, not invented)
The day-narrative decision logic (day_narrative.py -> smc_v2.py ->
smc_execution.py, restored from commit 0137446) — the ONLY decision layer in
this repo's history with a positive real-history replay record
(+2.43R/10d punitive fills; +7.0R/8.5mo; +8.16R unseen validation days).
Day classified first (TREND/RANGE/TRAP/POST_SPIKE/EXHAUSTED), playbooks per
state, conviction ledger, quality bar 0.70 / strong 0.78, within-day trade
memory, 2 entries/day institutional cadence (the replay optimum; 4+/day
measured negative). Knobs frozen from the June tuning — never tuned on gate
data.

### 2. Risk brain (the one artifact that survived the research gauntlet)
The macro regime dial (research/regime.py: real-yield + broad-dollar trend
ensemble) feeds `set_regime()`. TIGHTEN-ONLY: dial < 0.34 demotes STRONG
entries to NORMAL size; it can never upsize and never creates trades; stale/
missing macro reads UNAVAILABLE and changes nothing. Fed at service start
(cached FRED, 10-day staleness cutoff) and causally per-day in replay.

### 3. Cost brain (ALPHA-HUNT-001's measured lessons as gates)
- NO ENTRIES 16:55-18:20 ET (COMEX close/reopen: measured ~5.7 bps spread;
  the reopen drift itself lives inside the spread — decision 2026-07-05-02).
- ONE price-level-independent rule: estimated round-trip cost (live spread +
  0.30 slippage allowance) must stay ≤ 0.40 of the stop distance (1R);
  beyond that the trade is structurally unwinnable. (A fixed-USD stop floor
  was tried and removed: it wrongly blocked correct 7-8 bps tactical stops
  at 2021-2024 price levels.)
- A cost-blocked approval RESTORES the brain's daily entry slot (the block
  is not a trade).

### Exit model (chassis-validated)
`manage_stop`: break-even at +1R, 1.5×ATR(M5) trail beyond, fast
thesis-failure exit on a fresh CHOCH against the position. Tighten-only;
the gateway also refuses widening. `note_trade_closed` clears per-direction
exit memory.

## Envelope (reinstated brakes — the gold_alpha era's removals are reversed)

3%/trade cap (planner tiers 3% STRONG / 2% NORMAL), daily 5% pause, weekly
10% stop, max 3 open, 25/day survival ceiling, spread ≤ 1.0. Evidence:
drawdown control IS the growth lever; the aggressive 8%/5% uncapped era
weekly-stopped its account in days.

## Validation (in this environment — no Windows wait)

`scripts/intel_replay.py` drives the engine through the standard
DecisionReplay fill model (conservative: spread 0.50 + 0.30 slippage
adverse, stop-first ambiguity, BE at +1R) over the validated 7.5y Dukascopy
M1 archive, all timeframes aggregated causally, regime dial per-day causal.

**Ship gate (pre-registered, frozen before the run):** 14 fixed windows
(Mar + Sep, 2019-2025), PASS = total net R > 0 AND ≥8/14 windows
non-negative AND pooled DD ≤ 20R AND ≥100 trades. On PASS → 2026 holdout
(Feb/Apr/Jun) must be ≥ 0. Only then demo forward (owner starts the
service), with a pre-registered live kill at −15R book or the weekly −10%.
On FAIL → gold_intel stays FLAT; the negative result is recorded and any
re-tune is a NEW protocol on 2019-2023 only.

## Run (Windows MT5 host, only after a PASS)

    py -3.12 scripts\trading_service.py --profile gold_intel --stdout-progress

Retired and refused: gold_alpha, liquidity_intel, smc_v2, smc_challenge,
demo_challenge, continuous, growth_evaluation (get_profile raises).
