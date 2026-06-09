# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 6: Trade Hypothesis and Scoring

## Current Task ID:
P6-001

## Current Task Goal:
Trade Hypothesis Engine — generate LONG/SHORT/WAIT/NO_TRADE hypotheses with thesis, invalidation, target logic.

## Current Status:
P5-002 complete. Gold futures confirmation layer implemented and tested. Phase 5 finished.

---

# Completed Work

- P0-000 completed: repository environment initialized.
- P0-001 completed: master control pack created.
- P0-002 completed: repository structure created.
- P0-003 completed: runtime directory structure preserved.
- P1-001 completed: core data schemas defined and tested.
- P1-002 completed: MT5 demo data adapter (data fetch only) implemented and tested.
- P1-003 completed: data validation engine implemented and tested.
- P2-001 completed: timeframe aggregation implemented and tested.
- P2-002 completed: session/kill-zone engine implemented and tested.
- P3-001 completed: swing & market-structure engine implemented and tested.
- P3-002 completed: liquidity map engine implemented and tested.
- P3-003 completed: liquidity sweep engine implemented and tested.
- P3-004 completed: FVG / order block / supply-demand engine implemented and tested.
- P3-005 completed: premium/discount engine implemented and tested.
- P4-001 completed: daily and 4H bias engine implemented and tested.
- P4-002 completed: regime engine implemented and tested.
- P5-001 completed: order-flow proxy engine implemented and tested.
- P5-002 completed: gold futures confirmation layer implemented and tested.

## P5-002 Details

Files added/changed:
- src/orderflow/futures_confirmation.py — FuturesConfirmationEngine + FuturesConfirmation + FuturesAlignment enum.
- src/orderflow/__init__.py — export futures API.
- tests/test_futures_confirmation.py — 11 tests.

Design notes:
- Derives futures directional bias from futures candles via the P3-001 structure engine (final_bias), then compares to the spot thesis bias.
- ALIGNED (same direction) -> confidence up; CONFLICT (opposite) -> confidence down + uncertainty up; NEUTRAL (either side neutral) -> no change; UNAVAILABLE (missing/insufficient futures, < min_candles=6) -> zero adjustment + note (graceful, no crash).
- HARD RULE (INIT-006 / 19_GOLD_FUTURES_CONFIRMATION_POLICY.md): futures is context/confidence only; never a trade trigger. FuturesConfirmation.is_trade_signal is always False; no direction/signal/order field; engine has no decide/trade/buy/sell method. Tests enforce this.
- Adjustments are bounded by max_adjustment (default 0.2). No look-ahead (structure prefix-stable).

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 202 passed (11 futures + 10 orderflow + 7 regime + 10 htf-bias + 11 premium/discount + 11 zones + 8 sweep + 9 liquidity + 8 structure + 27 sessions + 22 aggregation + 17 validation + 21 adapter + 29 schema + 1 structure-dirs).

Errors: none.

---

# Next Task

## Task:
P6-001: Trade Hypothesis Engine

## Goal:
Generate LONG, SHORT, WAIT, NO_TRADE hypotheses with thesis, invalidation, and target logic.

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- likely src/strategy/ + src/utils/ + tests/ (src/strategy/ exists and was previously FORBIDDEN under earlier tasks — it becomes the working area for P6-001). Reuse src/structure/, src/liquidity/, src/regime/, src/orderflow/, and the TradeDecision schema in src/data/. Do not touch src/execution|risk.

## Tests:
- no thesis = no trade,
- no invalidation = no trade.

## Notes for P6-001:
- Build hypotheses from the analysis stack (HTF bias, regime, structure, liquidity sweep, zones, premium/discount). Use the existing TradeDecision schema (src/data/schemas.py) which already enforces: actionable LONG/SHORT requires a non-empty thesis and an invalidation_price, and stop must be on the correct side of entry.
- Output WAIT/NO_TRADE when conditions are not met (regime NO_TRADE/CHOPPY, bias NO_TRADE/NEUTRAL, missing thesis/invalidation).
- Hypotheses are proposals only; the risk governor (P7) decides permission. No look-ahead.

---

# Current Known Risks

- Real-money trading is forbidden.
- Demo order execution must not be implemented (data / analysis only).
- Exness/MT5 credentials must not be committed and must never be printed.
- .env must remain local only.
- MetaTrader5 cannot be imported on this Linux/WSL host; keep using dependency injection for tests.
- Analysis engines must avoid look-ahead (only past/known candles); preserve prefix stability.
- Order-flow proxy and futures are confirmation/confidence only; they cannot trigger trades alone.
- No live self-mutation is allowed.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, and 10_TASK_QUEUE.md.

Continue P6-001 only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders.
Do not print credentials.
Do not bypass tests.
