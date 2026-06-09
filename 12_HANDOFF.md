# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 5: Order-Flow Proxy and Futures Context

## Current Task ID:
P5-002

## Current Task Goal:
Gold Futures Confirmation Layer — add optional gold futures confirmation context (confidence only, cannot trigger trades alone).

## Current Status:
P5-001 complete. Order-flow proxy engine implemented and tested.

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

## P5-001 Details

Files added/changed:
- src/orderflow/proxy.py — OrderFlowProxyEngine + OrderFlowProxy + ProxyPressure, VolumeState enums.
- src/orderflow/__init__.py — package exports.
- tests/test_orderflow_proxy.py — 10 tests.

Design notes:
- Computes broker-level PROXY metrics from candles: volume_ratio (vs baseline), volume_state (EXPANSION/EXHAUSTION/NORMAL), spread_ratio + spread_widening, aggression (body/range), delta_proxy (signed volume of last candle), cvd_proxy (cumulative signed volume), CVD divergence (price vs cvd disagree), abnormal_activity, plus confidence/uncertainty adjustments and a note (allowed policy language).
- pressure (ProxyPressure BULLISH/BEARISH/NEUTRAL) is a PROXY descriptor with a deadzone; it is NOT a trade signal.
- HARD RULE (INIT-005 / 16_ORDERFLOW_PROXY_POLICY.md): proxy can only adjust confidence/uncertainty; it NEVER triggers trades. OrderFlowProxy.is_trade_signal is always False; the result has no direction/signal/order/entry field; the engine has no decide/trade/buy/sell method. Tests enforce all of this.
- Optional structural_bias arg: when proxy pressure opposes structure -> conflict_with_structure True and uncertainty increased (policy Conflict Rule).
- No look-ahead: only the supplied window is used.

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 191 passed (10 orderflow + 7 regime + 10 htf-bias + 11 premium/discount + 11 zones + 8 sweep + 9 liquidity + 8 structure + 27 sessions + 22 aggregation + 17 validation + 21 adapter + 29 schema + 1 structure-dirs).

Errors: none.

---

# Next Task

## Task:
P5-002: Gold Futures Confirmation Layer

## Goal:
Add optional gold futures confirmation context.

## Rules (INIT-006 / 19_GOLD_FUTURES_CONFIRMATION_POLICY.md):
- no look-ahead bias,
- futures confirms confidence only,
- futures cannot trigger a trade alone,
- missing futures data must not break the core system.

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- likely src/orderflow/ (or a new module) + src/utils/ + tests/. Reuse src/data/ schemas and src/structure/ Bias. Do not touch src/execution|risk|strategy.

## Tests:
- confirmation boosts/reduces confidence,
- missing futures data does not break core system.

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

Continue P5-002 only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders.
Do not print credentials.
Do not bypass tests.
