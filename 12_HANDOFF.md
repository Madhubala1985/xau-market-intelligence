# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 6: Trade Hypothesis and Scoring

## Current Task ID:
P6-002

## Current Task Goal:
Confidence and Uncertainty Engine — score structure, liquidity, regime, volatility, session, order-flow proxy, futures confirmation, execution quality.

## Current Status:
P6-001 complete. Trade hypothesis engine implemented and tested.

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
- P6-001 completed: trade hypothesis engine.

## P6-001 Details

Files added/changed:
- src/strategy/hypothesis.py — TradeHypothesisEngine + HypothesisInput.
- src/strategy/__init__.py — package exports.
- tests/test_hypothesis.py — 11 tests.

Design notes:
- Composes analysis context (HypothesisInput: symbol, time, current_price, htf_bias, regime, thesis_reason, invalidation_price, entry_price, target_price, setup_type, confidence, uncertainty) into a TradeDecision (status PROPOSED).
- Gates (return WAIT/NO_TRADE, never an invalid actionable): htf_bias NO_TRADE -> NO_TRADE; regime in {NO_TRADE, NEWS_RISK, CHOPPY} -> NO_TRADE; htf_bias NEUTRAL -> WAIT.
- Direction from bias: BULLISH->LONG, BEARISH->SHORT.
- HARD RULES: no thesis (empty thesis_reason) -> NO_TRADE; no invalidation_price -> NO_TRADE; invalidation on wrong side of entry -> NO_TRADE. These are also enforced structurally by the TradeDecision schema.
- Target logic: explicit target_price if it sits in the trade direction, else a default risk-reward target (default_rr=2.0) from entry/invalidation. Stop placed at the invalidation level.
- Hypotheses are proposals only (PROPOSED); risk governor (P7) decides permission. No look-ahead (composition only).
- NOTE: src/strategy/ was "forbidden" only in earlier data/analysis tasks; it is the working area for P6-001+.

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 213 passed (11 hypothesis + 11 futures + 10 orderflow + 7 regime + 10 htf-bias + 11 premium/discount + 11 zones + 8 sweep + 9 liquidity + 8 structure + 27 sessions + 22 aggregation + 17 validation + 21 adapter + 29 schema + 1 structure-dirs).

Errors: none.

---

# Next Task

## Task:
P6-002: Confidence and Uncertainty Engine

## Goal:
Score structure, liquidity, regime, volatility, session, order-flow proxy, futures confirmation, execution quality.

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- likely src/strategy/ + src/utils/ + tests/. Reuse src/orderflow/ (proxy + futures confidence/uncertainty adjustments), src/regime/, src/structure/, and TradeDecision. Do not touch src/execution|risk.

## Tests:
- high uncertainty blocks/reduces trade,
- confidence alone cannot bypass risk.

## Notes for P6-002:
- Aggregate component scores (structure, liquidity, regime, volatility, session, order-flow proxy, futures confirmation, execution quality) into an overall confidence in [0,1] and uncertainty in [0,1].
- Reuse the confidence_adjustment / uncertainty_adjustment outputs from the order-flow proxy (P5-001) and futures (P5-002).
- Enforce: when uncertainty exceeds a threshold, the trade is blocked or reduced (size factor); confidence alone must NOT bypass risk — output a recommendation that still defers to the risk governor (P7). No look-ahead.

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
