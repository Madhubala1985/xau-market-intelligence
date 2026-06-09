# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 7: Risk and Execution

## Current Task ID:
P7-001

## Current Task Goal:
Risk Governor — full risk checks; final authority over execution.

## Current Status:
P6-002 complete. Confidence/uncertainty engine implemented and tested. Phase 6 finished.

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
- P6-002 completed: confidence and uncertainty engine.

## P6-002 Details

Files added/changed:
- src/strategy/scoring.py — ConfidenceEngine + ComponentScores + ConfidenceResult + ScoreRecommendation.
- src/strategy/__init__.py — export scoring API.
- tests/test_scoring.py — 10 tests.

Design notes:
- ComponentScores: structure, liquidity, regime, volatility, session, execution_quality, each validated in [0,1].
- confidence = clamp(mean(components) + proxy.confidence_adjustment + futures.confidence_adjustment, 0, 1).
- uncertainty = clamp((1-mean)*0.5 + spread*0.5 + proxy.uncertainty_adjustment + futures.uncertainty_adjustment, 0, 1); spread = max-min component (disagreement raises uncertainty).
- Reuses P5-001 OrderFlowProxy and P5-002 FuturesConfirmation adjustment outputs (optional args).
- Recommendation: uncertainty >= block_uncertainty(0.7) OR confidence < min_confidence(0.3) -> BLOCK (size 0); uncertainty >= reduce_uncertainty(0.4) -> REDUCE (size 0.5); else ALLOW (size 1).
- HARD RULE: confidence alone cannot bypass risk. ConfidenceResult always has authorizes_trade=False and risk_governor_required=True; no approval/authorization field; engine has no approve/authorize/execute method (test-enforced). Recommendation is eligibility only; risk governor (P7) has final authority. No look-ahead.

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 223 passed (10 scoring + 11 hypothesis + 11 futures + 10 orderflow + 7 regime + 10 htf-bias + 11 premium/discount + 11 zones + 8 sweep + 9 liquidity + 8 structure + 27 sessions + 22 aggregation + 17 validation + 21 adapter + 29 schema + 1 structure-dirs).

Errors: none.

P6-001 was committed in this session as bb97d28 (its closeout commit had been missed before the resume).

---

# Next Task

## Task:
P7-001: Risk Governor

## Goal:
Implement full risk checks; the risk governor has final authority over execution (INIT-003).

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- src/risk/ + src/utils/ + tests/. Reuse TradeDecision, BrokerState (src/data/) and risk settings. Do not touch src/execution (P7-003) or src/strategy.

## Tests (07_TEST_POLICY.md Risk Tests — must all be proven):
- no stop-loss = blocked,
- too much risk = blocked,
- daily loss reached = blocked,
- weekly loss reached = blocked,
- spread too high = blocked,
- invalid lot size = blocked,
- broker state unknown = blocked,
- duplicate trade = blocked,
- wrong symbol = blocked.

## Notes for P7-001 (03_RISK_POLICY.md):
- The governor APPROVES / REDUCES / BLOCKS a TradeDecision against account/broker state and risk limits. It must NEVER place orders (that is P7-003 execution gateway).
- Do NOT weaken risk checks; do NOT delete/bypass risk tests (07_TEST_POLICY.md, 08_ERROR_POLICY.md).
- Read 03_RISK_POLICY.md and INIT-007 (demo risk: 0.50%/trade, 2% daily, 5% weekly, 3 trades/day, 1 open) before implementing.

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
