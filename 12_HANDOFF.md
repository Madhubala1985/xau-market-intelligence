# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 7: Risk and Execution

## Current Task ID:
P7-003

## Current Task Goal:
MT5 Demo Execution Gateway — place MT5 demo trades only after risk approval, with full safety checks.

## Current Status:
P7-002 complete. Position sizing implemented and tested.

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
- P7-002 completed: position sizing.

## P7-002 Details

Files added/changed:
- src/risk/position_sizing.py — PositionSizer + SizingResult + SizingStatus.
- src/risk/__init__.py — export sizing API.
- tests/test_position_sizing.py — 10 tests.

Design notes:
- size(decision, balance, requested_risk_pct, spread_price=0, slippage_price=0) -> SizingResult.
- lot = (balance * risk_pct) / (effective_stop * contract_size); effective_stop = |entry-stop| + spread_price + slippage_price (buffer WIDENS effective risk distance; the real stop is never shrunk). contract_size default 100 (XAU oz/lot).
- Lot snapped DOWN to lot_step, clamped to max_lot, so realized risk never exceeds target.
- STOP_TOO_WIDE: if snapped lot < min_lot -> block (skip), never shrink the stop.
- RISK_TOO_HIGH: requested_risk_pct > max_risk_per_trade -> block (excessive risk not silently capped).
- INVALID_INPUT: bad balance/risk/stop/buffers.
- SizingResult feeds RiskGovernor (lot_size + risk_pct); integration test confirms an APPROVE. No order placement.

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 252 passed (10 position-sizing + 19 risk-governor + ... prior).

Errors: none.

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
P7-003: MT5 Demo Execution Gateway

## Goal:
Place MT5 demo trades only after risk approval, with full execution safety checks.

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- src/execution/ + src/utils/ + tests/. Reuse RiskGovernor (src/risk/), TradeDecision/BrokerState (src/data/), and the MT5 client pattern from src/broker/ (injected/lazy MetaTrader5). Do not touch src/risk internals.

## Tests (10_TASK_QUEUE.md P7-003):
- wrong symbol blocked,
- no SL blocked,
- duplicate blocked,
- order state logged,
- no credentials printed.

## Notes for P7-003 (CLAUDE.md Trading Safety Rule + 05_EXECUTION_POLICY.md):
- The gateway places a demo order ONLY when: the Risk Governor APPROVES/REDUCES, AND all safety flags are on (TRADING_MODE=DEMO, REAL_TRADING_ENABLED=false, ALLOW_DEMO_ORDERS=true, ALLOW_MT5_ORDER_SEND=true, ALLOW_REAL_ORDERS=false).
- DEFAULT must never send (dry-run/paper). Real orders are forbidden. order_send only ever reached for DEMO with all gates passed.
- Use an injected/mock MT5 client (MetaTrader5 is Windows-only and not importable here). Tests inject a fake and assert order_send is called only in the allowed case, and never with real-order parameters.
- Verify symbol, stop-loss present, no duplicate (open positions), lot/spread, broker connection; log order state; never print credentials.

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
