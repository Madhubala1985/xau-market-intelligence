# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 12: Live Demo Readiness

## Current Task

LIVE-001: Connect Live/Replay Data to DecisionPipeline and ShadowRunner

## Last Completed Task

P0-P11 roadmap completed.
INT-001: DecisionPipeline integration completed.
RISK-001: Leverage-aware sizing and protected pyramiding completed.
LIVE-VERIFY-001: Implementation evidence pack generator completed.
WINMT5-001: MT5 demo connectivity validator + Windows runner completed
(tooling done; LIVE MT5 proof still PENDING the Windows host — see blocker below).

## Next Task

LIVE-001 (may use replay data until the Windows MT5 live bridge is available)

## Current Execution Mode

DEMO_CONFIGURED_BUT_NOT_YET_LIVE_VALIDATED

## Real Trading

FORBIDDEN

## Demo Trading

ALLOWED ONLY AFTER PHASE 12 GATES PASS

## Paper / Shadow Trading

ALLOWED

## Environment Status

- .env.example exists.
- .env is local only and ignored by git.
- Demo MT5 credentials may be stored only in .env.
- Real credentials are forbidden.
- MT5 live validation is NOT yet proven: this WSL/Linux host cannot import
  MetaTrader5 (ENVIRONMENT_ISSUE). The WINMT5-001 validator + runner are built
  and tested; live checks 3-9 must be proven by running
  `python scripts/winmt5_validate.py` on the Windows MT5 host.

## WINMT5-001 Blocker (carry-forward)

- The read-only connectivity validator (src/broker/connectivity.py) and runner
  (scripts/winmt5_validate.py) are complete and tested; no order_send is ever
  called and no credentials are printed.
- On WSL the runner correctly reports outcome ENVIRONMENT_ISSUE (MetaTrader5 not
  importable) and SKIPS live checks 3-9 instead of faking them.
- LIVE MT5 demo proof (init/login/account/symbol/candles/spread) is still PENDING
  a Windows host run. Re-run the runner there to obtain outcome VALIDATED.

## Next Exact Action

Start LIVE-001:
Feed real or REPLAYED XAU/USD data into DecisionPipeline and ShadowRunner. No
orders; ExecutionGateway must not send. Replay data may be used until the Windows
MT5 live bridge is available, so LIVE-001 is not blocked by the WINMT5-001 live
proof. Regenerate the evidence pack with `python scripts/generate_evidence_pack.py`.

## Safety Notes

- Do not commit .env.
- Do not enable real trading.
- Do not print credentials.
- Do not place orders. Do not call order_send.
- Do not start demo orders until WINMT5-001 (live proof), LIVE-001, LIVE-002, and
  DEMO-001 pass.
