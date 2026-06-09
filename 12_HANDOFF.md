# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 7: Risk and Execution

## Current Task ID:
P7-002

## Current Task Goal:
Position Sizing — calculate lot size from risk, stop distance, broker contract rules, spread/slippage buffer.

## Current Status:
P7-001 complete. Risk Governor implemented and tested (all 9 mandatory blocks proven).

---

# Completed Work

- P0-000..P0-003 completed: environment, control pack, repo structure, runtime dirs.
- P1-001 completed: core data schemas.
- P1-002 completed: MT5 demo data adapter (data fetch only).
- P1-003 completed: data validation engine.
- P2-001 completed: timeframe aggregation.
- P2-002 completed: session/kill-zone engine.
- P3-001 completed: swing & market-structure engine.
- P3-002 completed: liquidity map engine.
- P3-003 completed: liquidity sweep engine.
- P3-004 completed: FVG / order block / supply-demand engine.
- P3-005 completed: premium/discount engine.
- P4-001 completed: daily and 4H bias engine.
- P4-002 completed: regime engine.
- P5-001 completed: order-flow proxy engine.
- P5-002 completed: gold futures confirmation layer.
- P6-001 completed: trade hypothesis engine (committed bb97d28).
- P6-002 completed: confidence and uncertainty engine.
- P7-001 completed: risk governor.

## P7-001 Details

Files added/changed:
- src/risk/governor.py — RiskGovernor + RiskLimits + RiskContext + RiskDecision + RiskAction + RiskCheck.
- src/risk/__init__.py — export risk API.
- tests/test_risk_governor.py — 19 tests.

Design notes:
- evaluate(decision: TradeDecision, context: RiskContext) -> RiskDecision (APPROVE / REDUCE / BLOCK). Never places orders (test asserts no order/send/execute/buy/sell/place method).
- Accumulates ALL failing checks then BLOCKs if any. RiskCheck codes: NON_ACTIONABLE, WRONG_SYMBOL, BROKER_STATE_UNKNOWN, NO_STOP_LOSS, INVALID_LOT_SIZE, SPREAD_TOO_HIGH, RISK_TOO_HIGH, DAILY_LOSS_REACHED, WEEKLY_LOSS_REACHED, MAX_TRADES_REACHED, MAX_OPEN_TRADES, DUPLICATE_TRADE, CONSECUTIVE_LOSSES, SCORING_BLOCKED.
- RiskLimits defaults = demo profile (INIT-007): max_risk_per_trade 0.005, max_daily_loss 0.02, max_weekly_loss 0.05, max_trades_per_day 3, max_open_trades 1, max_spread 50, lot min/step 0.01/max 100, max_consecutive_losses None (off by default).
- RiskContext: broker (BrokerState), current_spread, lot_size, intended_risk_pct, daily/weekly_loss_pct, trades_today, consecutive_losses, open_symbols, size_factor_hint (from P6-002 scoring).
- Broker state unknown = connection != CONNECTED, or trade_allowed False, or balance None.
- Duplicate = decision.symbol already in open_symbols; exposure = broker.open_positions >= max_open_trades (separate codes).
- size_factor_hint <= 0 -> BLOCK (scoring vetoed); < 1 -> REDUCE; else APPROVE. Confidence cannot bypass a hard block (test-proven).
- intended_risk_pct is provided by the caller (position sizing is P7-002); the governor validates it against max_risk_per_trade.

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 242 passed (19 risk-governor + 10 scoring + 11 hypothesis + 11 futures + 10 orderflow + 7 regime + 10 htf-bias + 11 premium/discount + 11 zones + 8 sweep + 9 liquidity + 8 structure + 27 sessions + 22 aggregation + 17 validation + 21 adapter + 29 schema + 1 structure-dirs).

Errors: none.

---

# Next Task

## Task:
P7-002: Position Sizing

## Goal:
Calculate lot size from risk, stop distance, broker contract rules, spread/slippage buffer.

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- src/risk/ + src/utils/ + tests/. Reuse TradeDecision and RiskLimits. Do not touch src/execution.

## Tests:
- correct lot calculation,
- excessive risk blocked.

## Notes for P7-002 (03_RISK_POLICY.md Position Sizing Rule):
- lot = (account_balance * risk_pct) / (stop_distance_in_price * contract_value_per_price_unit), then snap DOWN to lot_step and clamp to [min_lot, max_lot]. Include a spread/slippage buffer in the effective stop distance.
- NEVER reduce stop distance to increase size. If the logical stop is too wide (computed lot < min_lot), reduce size or skip (return a no-trade/blocked sizing result), do not shrink the stop.
- Excessive resulting risk (e.g., min_lot still exceeds max_risk_per_trade) must be blocked.
- Output feeds the Risk Governor's lot_size / intended_risk_pct. No order placement.

---

# Current Known Risks

- Real-money trading is forbidden.
- Demo order execution must not be implemented (data / analysis only).
- Exness/MT5 credentials must not be committed and must never be printed.
- .env must remain local only.
- MetaTrader5 cannot be imported on this Linux/WSL host; keep using dependency injection for tests.
- Analysis engines must avoid look-ahead (only past/known candles); preserve prefix stability.
- Proxy/futures are confidence-only; hypotheses are proposals; the risk governor (P7) has final authority.
- No live self-mutation is allowed.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, and 10_TASK_QUEUE.md.

Continue P6-002 only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders.
Do not print credentials.
Do not bypass tests.
