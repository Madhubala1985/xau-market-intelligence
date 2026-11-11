# 28_GOLD_ALPHA_DESIGN.md

## Purpose

Design contract for GOLD-ALPHA-001 (owner-directed, 2026-06-16): a single
XAU/USD profit-maximisation model built from scratch. All prior profiles are
retired. One model, one profile (`gold_alpha`), one execution path, one MT5
account source from `.env`, one journal, one accounting system.

Objective: maximise account growth through profitable trading — decide from
live market evidence, not hardcoded hope; trade aggressively when an edge is
present, stay flat when it is not; protect winners; exit fast when the thesis
fails; learn from every closed trade. No fixed balance target, no artificial
daily trade cap, no "only 1–2 trades/day" rule.

Exact run command (Windows MT5 host):
`py -3.12 scripts\trading_service.py --profile gold_alpha --stdout-progress`

## Architecture

REUSED (proven chassis + analytics primitives — not reinvented):
MT5 adapter (source of truth), ExecutionGateway (only order path, mandatory
SL, kill switch), RiskGovernor, journal, SupervisedDemoSession/TradingService
loop, and the SMC analytics that compute the features (sessions, Asian range,
HTF/MTF bias, market structure BOS/CHOCH, liquidity map + sweeps, FVG/OB
zones, premium/discount, volatility, chop, order-flow proxy).

NEW (the model):
- `src/strategy/gold_alpha.py` — `GoldAlphaEngine.decide(PipelineInput) ->
  PipelineResult` (the chassis contract) + `manage_stop()` (exit/trail) +
  `note_stop_loss()` / `note_trade_closed()` (learning hooks).
- `src/strategy/trade_attribution.py` — post-trade WHY classifier +
  `PerformanceStore` that down-weights failing setups before the next trade.
- Single planner `IntelTradePlanner` (equity-scaled, mandatory SL, no
  martingale/averaging). Single profile `gold_alpha` (session_profiles).

## How it decides entries (the EV objective)

Each cycle the engine enumerates EVERY setup actually present:
SWEEP_RECLAIM (liquidity grab + reclaim), TREND_CONTINUATION (pullback into an
aligned FVG/OB with HTF direction), RANGE_FADE (premium/discount extreme in a
range), BOS_RETEST (break + retest + displacement). Each candidate gets a
protected stop and a draw-on-liquidity target, then is SCORED into an expected
value:

    p_win  = base + MTF alignment + regime fit + confirmation strength
                  + premium/discount fit + displacement + order-flow agreement
                  + session timing - stop-not-beyond-pool - spread/vol
                  - account-state(drawdown/consec losses)
                  + recent-realised-performance (the learning loop)
    target_R = distance(entry -> opposing liquidity) / distance(entry -> stop)
    EV       = p_win * target_R - (1 - p_win) * 1.0

It trades the highest-EV candidate when `EV >= EV_BAR` and `p_win >= P_WIN_MIN`
— sizing up (STRONG tier) when EV is high. No fixed cadence: many trades on a
strong day, none on a dead one. Below the bar it WAITs and prints exactly what
it is waiting for (never silent).

## How it exits

`manage_stop()` runs every cycle for open positions and returns a TIGHTEN-ONLY
stop (the gateway never widens):
- **Break-even** once +1R in profit (a winner can no longer become a full loss);
- **Adaptive trail** an ATR multiple behind price once running;
- **Fast thesis-failure exit**: on a CHOCH against the position, the stop is
  tightened to just beyond current price so it exits on the next adverse tick.
Plus the mandatory SL and the draw-on-liquidity TP.

## How it trails

After +1R, the stop trails `TRAIL_ATR_MULT` (1.5) × M5-ATR behind price,
ratcheting only in the favourable direction — aggressive enough to bank an
expansion, loose enough not to be wicked out of a valid run.

## How it avoids stupid SL placement

`_protect_stop` places the stop beyond real invalidation (sweep rejection
extreme / zone far boundary / structural swing) + buffer, then **pushes it past
any resting liquidity pool** (equal highs/lows, session/PDH-PDL) it would
otherwise sit at — because that is exactly where gold hunts stops. If the
protected stop is wider than the budget allows, the candidate is dropped
(reduce/skip) rather than planting the stop in the pool. The
`stop_beyond_pool` flag feeds both the EV score (penalised if false) and the
loss attribution (a stop hunt is logged as LIQUIDITY_TRAP / BAD_SL_PLACEMENT).

## Account-growth logic (no target chasing)

Size is equity-scaled (compounds as the balance grows) and edge-scaled (STRONG
EV risks more, up to the 6% cap); there is NO target balance anywhere in the
code — the objective is per-trade expected value, so the model never "chases
10k" and never over-trades to hit a number. Account state feeds back: in
drawdown / after consecutive losses it lowers p_win (gets selective);
recovering, it re-expands. Daily/weekly loss circuit-breakers are OFF for this
DEMO growth profile (owner directive); structural safety is absolute.

## The learning loop

On every close the session calls the engine: `note_stop_loss` /
`note_trade_closed`. The engine attributes WHY (bad entry, bad SL, liquidity
trap, wrong regime, late entry, spread/volatility, weak confirmation, invalid
thesis) from the recorded entry context vs. the outcome, and records it in the
`PerformanceStore` keyed by (setup_type, regime). The EV score reads that store
via `p_win_adjustment` — a setup/regime that is repeatedly failing (especially
to the same cause) is down-weighted before the next decision, so the model
stops repeating losing ideas instead of re-trying on hope.

## Minimum correctness (kept absolute)

MT5 balance/equity/deals are the only source of truth; losing trades are
logged as losses; no order without SL; no martingale/grid/averaging; kill
switch; one service; demo-only (real forbidden); retired profiles refused.

## Terminal output (every cycle)

account balance/equity, realized/floating PnL, D1/H4/H1/M15/M5/M1 read,
regime, liquidity map + sweep status, structure/FVG-OB/premium-discount/
order-flow, candidate list with per-setup EV, the chosen setup + entry trigger,
EV/p_win/target_R + score breakdown + recent performance, SL price/source/
reason (beyond_pool), TP/trail plan, decision + why.

## Validation

`scripts/decision_replay.py --days N` replays gold_alpha over real MT5 history
(conservative fills) -> reports/runtime/liquidity_intel_replay.md (legacy
filename). SHIP BAR: positive net R, drawdown <= 12R, >= 10 trades — else stay
flat live. Tests: test_gold_alpha, test_trade_attribution, test_single_path,
plus retargeted accounting/broker/planner/profile/service tests.

## Known limitations (honest)

The edge must be earned out-of-sample; a brand-new engine has no inherited
expectancy. News/macro/futures remain fail-closed stubs. Replay fills are
conservative proxies. The attribution heuristics are first-pass and will be
refined from live evidence.
