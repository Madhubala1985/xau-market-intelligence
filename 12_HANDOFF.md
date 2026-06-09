# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 9: Journal and Reflection

## Current Task ID:
P9-002

## Current Task Goal:
Reflection Engine — classify mistakes and generate daily review.

## Current Status:
P9-001 complete. Trade journal implemented and tested.

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
- P7-003 completed: MT5 demo execution gateway.
- P8-001 completed: stop placement intelligence.
- P8-002 completed: trailing stop engine.
- P9-001 completed: trade journal.

## P9-001 Details

Files added/changed:
- src/journal/journal.py — TradeJournal + JournalEntry + EntryKind + DEFAULT_JOURNAL_PATH.
- src/journal/__init__.py — export journal API.
- tests/test_journal.py — 8 tests.

Design notes:
- Append-only JSON Lines store; each line wraps a TradeDecision or TradeRecord (via model_dump(mode="json")) plus logged_at_utc. Restart-safe: a fresh TradeJournal on the same path reloads all entries (entries()/decisions()/records()).
- log_decision logs trades AND no-trade decisions; log_record logs outcomes. Round-trip equality holds (frozen pydantic models compare by value).
- Only credential-free schemas are written; test asserts no credential tokens in the file.
- DEFAULT_JOURNAL_PATH = logs/trade_journal.jsonl (logs/ is gitignored); tests use tmp_path.

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 302 passed (8 journal + 294 prior).

Errors: none.

## P8-002 Details

Files added/changed:
- src/trade_management/trailing.py — TrailingStopEngine + PositionState + TrailResult + TrailMethod + RunnerConditions + PartialPlan.
- src/trade_management/__init__.py — export trailing API.
- tests/test_trailing.py — 14 tests.

Design notes:
- update_stop(state, method, last_swing=, protect_level=) -> TrailResult. Methods: VOLATILITY (price ∓ atr*mult), STRUCTURE (last_swing ∓ buffer), LIQUIDITY (protect_level ∓ buffer), BREAK_EVEN (entry).
- No premature trailing: holds the current stop until profit_r >= be_trigger_r (default 1R); break-even only after confirmation.
- Never widen: a candidate is applied only if it improves the stop toward price (LONG up, SHORT down) and is on the correct side of price; otherwise the stop is held (moved=False).
- partial_plan(state, next_liquidity=, conditions=) -> PartialPlan: take_levels = [1R, then next_liquidity if beyond 1R]; runner_allowed = structure_valid and not opposite_displacement and spread_safe.
- No order placement; no look-ahead.

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 294 passed (14 trailing + 280 prior).

Errors: none.

## P8-001 Details

Files added/changed:
- src/trade_management/stop_placement.py — StopPlacementEngine + StopPlacement + StopEvaluation + StopVerdict.
- src/trade_management/__init__.py — export API.
- tests/test_stop_placement.py — 14 tests.

Design notes:
- Scope is stop PLACEMENT only (trailing is P8-002). No order placement; no look-ahead.
- clearance(atr) = max(atr*atr_multiple(0.5), min_buffer(1.0)). place(): LONG stop = min(invalidation - (clearance+spread), entry - broker_min_stop); pushed beyond any liquidity pool within clearance; SHORT mirrored.
- evaluate(): REJECTED_WRONG_SIDE, REJECTED_NOT_BEYOND_INVALIDATION, REJECTED_OBVIOUS (on/too near invalidation OR on a liquidity pool, gap < clearance), REJECTED_TOO_TIGHT (distance from entry < max(broker_min_stop, min_buffer)), else ACCEPTED.
- place_for_decision / evaluate_decision read entry/invalidation/stop from a TradeDecision.
- A computed stop always passes its own evaluate() (tested).

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 280 passed (14 stop-placement + 266 prior).

Errors: none.

## P7-003 Details

Files added/changed:
- src/execution/gateway.py — ExecutionGateway + ExecutionFlags + ExecutionResult + ExecutionStatus + OrderState + ExecutionCheck + load_execution_flags.
- src/execution/__init__.py — export execution API.
- tests/test_execution_gateway.py — 14 tests.

Design / safety notes:
- execute(decision, context) runs: hard real-money refusal -> pre-execution checks -> Risk Governor (final authority) -> safe-default dry-run -> demo order_send.
- order_send is reached ONLY when ExecutionFlags.demo_send_enabled (TRADING_MODE=DEMO, REAL_TRADING_ENABLED=false, ALLOW_DEMO_ORDERS=true, ALLOW_MT5_ORDER_SEND=true, ALLOW_REAL_ORDERS=false) AND the governor approves AND all pre-checks pass. DEFAULT ExecutionFlags() sends nothing (DRY_RUN). Real requested (allow_real_orders / real_trading_enabled / non-DEMO mode) -> REAL_FORBIDDEN, never sends.
- Pre-checks (ExecutionCheck): NOT_ACTIONABLE, WRONG_SYMBOL, NO_STOP_LOSS, NO_TAKE_PROFIT, BROKER_DISCONNECTED, DUPLICATE; plus RISK_BLOCKED from the governor. Any failure -> BLOCKED, no send.
- Order lifecycle logged in result.states: SIGNAL_CREATED -> RISK_APPROVED -> ORDER_PREPARED -> ORDER_SENT -> ORDER_ACCEPTED/ORDER_REJECTED (or -> BLOCKED).
- MT5 client is injected (Windows-only); tests use a FakeMT5 and assert order_send is only called in the allowed case. The gateway holds/logs NO credentials (order request contains only symbol/volume/type/price/sl/tp/deviation/magic/comment); verified by test and grep.
- size_factor from a REDUCE verdict scales the sent volume.

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 266 passed (14 execution + 252 prior).

Errors: none.

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
P9-002: Reflection Engine

## Goal:
Classify mistakes and generate a daily review from journaled trades/decisions.

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- src/reflection/ + src/utils/ + tests/. Reuse TradeRecord/TradeDecision (src/data/) and the journal (src/journal/). Do not touch src/execution|risk internals.

## Tests (10_TASK_QUEUE.md P9-002):
- mistake categories assigned.

## Notes for P9-002 (09? see 01_SYSTEM_MINDSET.md / 04_ADAPTATION_POLICY.md; 02_ARCHITECTURE.md section 18):
- Classify mistakes mechanically from TradeRecords: e.g., overconfidence (high confidence + loss), revenge/overtrading (many trades/day), poor timing, chasing (no thesis), ignored uncertainty (high uncertainty + loss), no-stop/early-exit, missed opportunity.
- Generate a daily review summary (counts, win/loss, pnl, mistake categories) over a set of records (optionally pulled from the journal).
- Offline only: reflection produces a report; it must NOT change live policy (no self-mutation, INIT-004). Never write credentials.

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
