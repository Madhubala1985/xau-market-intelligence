# 27_LIQUIDITY_INTEL_DESIGN.md

## Purpose

Design contract for the rebuild (Task LIQUIDITY-INTEL-001, owner-directed,
2026-06-15). The project was rebuilt into ONE clean autonomous XAU/USD model.
Every prior decision profile (demo_challenge, smc_challenge, smc_v2) and the
dual/institutional execution paths are RETIRED. There is now exactly one
account source (`.env`), one execution path, one journal, one accounting
source (MT5), one trading service, and one decision engine.

New model / profile name: **liquidity_intel**
Exact run command (Windows MT5 host):
`py -3.12 scripts\trading_service.py --profile liquidity_intel --stdout-progress`

## Why the rebuild

The repo had grown three overlapping decision profiles plus an institutional
path; `scripts/trading_service.py` forked on profile name into two different
pipeline+planner stacks. Replay evidence had already retired the SMC/challenge
family (-82.7R/25d). The owner directed a from-scratch single autonomous model
under one new name. Demo-only and all risk anchors remain absolute.

## Architecture (one engine on the proven chassis)

REUSED UNCHANGED (proven chassis — not rewritten):
- Account/connection/accounting (MT5 = source of truth):
  `src/broker/mt5_data_adapter.py` (`verify_demo_account`,
  `fetch_closed_position(position=ticket)`, `fetch_realized_pnl_since`,
  `fetch_entry_count_since`, `fetch_balance_ops_since`).
- Order pathway & safety: `ExecutionGateway` (the ONLY order path: open +
  modify_stop; no market-close path by design), `RiskGovernor` (final
  authority), kill switch, preflight, news guard, `lot_sizer`.
- Cycle loop & management: `TradingService` + `SupervisedDemoSession`
  (reconciliation, MT5 close detection, break-even/trailing protection).
- Analytics primitives: SessionEngine, AsianRangeEngine, HtfBiasEngine,
  MtfAlignmentEngine, MarketStructureEngine (BOS/CHOCH), ZoneEngine
  (FVG/OB), PremiumDiscountEngine, LiquidityMapEngine, SweepEngine,
  VolatilityClassifier, ChopClassifier, OrderFlowProxyEngine, DataValidator.

NEW (the single decision layer):
- `src/strategy/liquidity_intel.py` — `LiquidityIntelEngine.decide(
  PipelineInput) -> PipelineResult` (same contract the chassis drives).
- `src/execution/intel_planner.py` — `IntelTradePlanner`, the ONE planner;
  equity-scaled sizing via the proven leverage sizer; mandatory SL; protected
  add-ons only; no hedging / averaging-down / martingale; never sends.

## The decision engine: a market POSTURE model

Each cycle the engine reads the full D1/H4/H1/M15/M5/M1 picture and classifies
the market posture, then decides for itself:

- **TREND** — HTF+LTF aligned with displacement -> continuation pullbacks into
  an aligned FVG/OB WITH the trend; 3R runner target + trailing.
- **LIQUIDITY_REVERSAL** — an engineered pool was swept AND reclaimed (the
  reclaim held) -> fade the swept side; stop BEYOND the rejection extreme
  (past the hunted pool); 2R target.
- **RANGE_SCALP** — tradeable range at a premium/discount extreme after a
  boundary sweep -> fade toward equilibrium; 1.5R target.
- **WAIT** — no qualified posture: prints an explicit re-arm condition and
  rescans next candle (never a silent permanent block).
- **FLAT** — dangerous volatility / structureless chop / news risk: no
  entries, explicit re-arm condition.

A fixed-weight QUALITY score (posture alignment + liquidity-event quality +
stop quality + session timing + MTF magnitude + orderflow agreement) gates
entry; STRONG tier above the strong bar selects 1.5% equity risk, else 1.0%.
Weights/bars are tuned ONLY by replay evidence, never live.

## Stop-loss doctrine (non-negotiable)

The stop is REAL invalidation, never the naked liquidity pool.
`_protect_stop_from_pool` places the stop beyond the engineered extreme +
buffer, then pushes it past any resting liquidity pool it would otherwise sit
at/inside (the market hunts those). If the protected stop is wider than the
budget allows, the engine reduces size (risk tier) or WAITs/SKIPs — risk is
never widened into the trap (hard 8 USD ceiling).

## Exit / reverse mechanics (deliberate scope boundary)

The gateway exposes ONE order pathway (open) plus stop modification — there is
no market-close order path, by design (one execution path; stops never widen).
So: protective exits are expressed through the proven break-even/trailing
protection engine and the mandatory SL/TP; a REVERSE is a fresh opposite entry
once the position is flat. The engine surfaces MANAGE/EXIT/REVERSE intent in
the cycle output for transparency; the chassis executes it with proven
mechanics. (A dedicated gateway close path is a separate, tested change.)

## Risk envelope (anchors absolute — demo only)

One envelope in `session_profiles.py`: 3%/trade survival cap, daily 5% net
pause, weekly 10% net stop, max 3 open, a 25/day survival CEILING (the quality
bar governs the real cadence — there is NO artificial fixed per-day trade
cap), spread <= 1.0. Mandatory SL, kill switch, loss cooldown,
accounting-unverified blocks new entries, REAL accounts refused. Profiles can
only tighten 03_RISK_POLICY.

## Single-path guarantees (enforced + tested)

- `get_profile()` raises for every retired name with a pointer to
  `liquidity_intel`; the registry holds exactly one profile.
- The deleted modules (`smc_v2`, `smc_execution`, `day_narrative`,
  `challenge_planner`) cannot be imported.
- `scripts/trading_service.py` builds exactly one pipeline + one planner (no
  fork; the old fork symbols are gone).
- `tests/test_single_path.py` asserts all of the above.

## Validation gate (before ANY live demo trading)

`scripts/decision_replay.py --days 25` (Windows MT5 host) replays the engine
over real MT5 history under the conservative fill model and writes
`reports/runtime/liquidity_intel_replay.md/.json`. SHIP BAR: net R positive,
max drawdown <= 12R, >= 10 trades. Otherwise the engine stays FLAT live —
protecting capital is the position. Edge must be validated from zero (this is
a from-scratch engine; no inherited expectancy).

## Tests

810 pass. New: `test_liquidity_intel.py` (protected-stop doctrine, reclaim
detection, six-TF usage, news-FLAT, anti-silence WAIT, consumed-stop guard),
`test_intel_planner.py` (mandatory SL, no hedging/averaging-down, protected
add-ons, equity sizing, survival cap), `test_single_path.py`. Retargeted:
`test_smc_accounting.py`, `test_broker_execution.py`, `test_session_profiles.py`,
`test_trading_service.py`, `test_decision_replay.py`.

## Known limitations (honest)

- No gateway market-close path (exits via SL/TP + trailing; reverse = fresh
  entry once flat).
- NEWS-001 (real calendar), MACRO-001 (DXY/yields), FUTURES-001 (gold
  futures) remain provider stubs / fail-closed.
- Replay fills are conservative proxies; week-1 live measures true fills.
- The edge is unproven until the real-history replay passes the ship bar.
