# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

---

# Current Project State

## Current Phase:
Phase 12: Live Demo Readiness

## Current Task ID:
WINMT5-LIVE-001

## Current Task Goal:
Execute Windows MT5 demo validation against the real Exness demo terminal.

## Current Status:
MT5 validation tooling exists, but live MT5 proof is not complete because WSL/Linux cannot import MetaTrader5. The next action is to run the Windows-side validator against the actual MT5 terminal.

---

# Completed Work

- P0-P11 roadmap completed.
- INT-001 completed.
- RISK-001 completed.
- LIVE-VERIFY-001 completed.
- WINMT5-001 tooling completed.
- Windows-side validation script exists: scripts/winmt5_validate.py.
- Windows runner instructions exist: scripts/winmt5_runner_README.md.
- Case-sensitivity bug fixed: MT5_SYMBOL keeps exact broker case (e.g. XAUUSDm)
  for symbol_select / symbol_info / copy_rates / symbol_info_tick; uppercase is
  used only for canonical XAU/USD validation (commit WINMT5-001 case fix).

---

# Current Blocker

LIVE-001 replay/live pipeline work is paused until Windows MT5 demo validation is proven.

---

# Required Proof

WINMT5-LIVE-001 must prove:

1. MT5 terminal path configured.
2. Demo credentials load from .env without printing values.
3. MT5 initializes.
4. Demo login succeeds.
5. Account is verified as demo / non-real.
6. XAU/USD symbol is detected.
7. symbol_info is read.
8. Latest candles are fetched.
9. Spread is read.
10. no order_send is called.

---

# Allowed Files

- scripts/
- reports/runtime/
- CURRENT_STATE.md
- 12_HANDOFF.md
- 11_DECISION_LOG.md
- tests/ only if validator test needs a small update

---

# Forbidden Files

- .env
- src/execution/
- src/risk/
- src/strategy/
- real-money configuration

---

# Safety Rules

- No real trading.
- No demo orders.
- No order_send.
- No credentials printed.
- Do not fake live validation.
- If Windows runner fails, record exact environment issue and next fix.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, 10_TASK_QUEUE.md, 22_MT5_WINDOWS_VALIDATION.md, and scripts/winmt5_runner_README.md.

Continue WINMT5-LIVE-001 only.

Do not continue LIVE-001.
Do not use replay data yet.
Do not trade real money.
Do not place demo orders.
Do not call order_send.
Do not print credentials.
Do not commit .env.
Do not fake live validation.

Guide the user to run the Windows-side MT5 validator and then record the result.
