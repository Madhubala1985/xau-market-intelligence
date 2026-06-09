# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 5: Order-Flow Proxy and Futures Context

## Current Task ID:
P5-001

## Current Task Goal:
Order-Flow Proxy Engine — use MT5 tick volume, spread behavior, tick movement, and optional delta/CVD proxy cautiously.

## Current Status:
P4-002 complete. Regime engine implemented and tested. Phase 4 finished.

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

## P4-002 Details

Files added/changed:
- src/regime/regime_engine.py — RegimeEngine + RegimeResult + Regime enum.
- src/regime/__init__.py — export regime API.
- tests/test_regime.py — 7 tests (regime cases).

Design notes:
- Classifies a candle window into one Regime: TREND, RANGE, COMPRESSION, EXPANSION, CHOPPY, NEWS_RISK, NO_TRADE.
- Reuses P3-001 structure events: bos_count, choch_count, and direction flips (consecutive event-bias changes). Volatility ratio = avg range of the second half / first half of the window.
- Priority-ordered decision (one regime per window): data(<min_candles)->NO_TRADE; news_risk flag->NEWS_RISK; flips>=choppy_flips(2)->CHOPPY; events & flips==0 & bos>=1 & directional->TREND; ratio>=expansion_factor(1.5)->EXPANSION; ratio<=compression_factor(0.67)->COMPRESSION; no events->RANGE; else NO_TRADE.
- NEWS_RISK is an external flag input (news module integration comes later); default off.
- RegimeResult exposes final_bias, bos_count, choch_count, flips, volatility_ratio, reason.
- No look-ahead: structure prefix-stable; volatility uses only the window.

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 181 passed (7 regime + 10 htf-bias + 11 premium/discount + 11 zones + 8 sweep + 9 liquidity + 8 structure + 27 sessions + 22 aggregation + 17 validation + 21 adapter + 29 schema + 1 structure-dirs).

Errors: none.

---

# Next Task

## Task:
P5-001: Order-Flow Proxy Engine

## Goal:
Use MT5 tick volume, spread behavior, tick movement, and an optional delta/CVD proxy cautiously.

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- likely src/orderflow/ + src/utils/ + tests/ (src/orderflow/ exists). Reuse src/data/ schemas (Candle, Tick, SpreadSnapshot). Do not touch src/execution|risk|strategy.

## Tests:
- proxy values calculated,
- no direct trade signal from proxy alone.

## Notes for P5-001 (see 16_ORDERFLOW_PROXY_POLICY.md and INIT-005):
- MT5 volume/CVD/delta are PROXIES, not guaranteed institutional order flow.
- Compute proxy metrics (tick-volume trends, spread behavior, tick movement, optional delta/CVD proxy from candle direction * volume) but the engine must NOT emit a trade direction/signal by itself — only proxy values / confidence adjustments.
- No look-ahead.

---

# Current Known Risks

- Real-money trading is forbidden.
- Demo order execution must not be implemented (data / analysis only).
- Exness/MT5 credentials must not be committed and must never be printed.
- .env must remain local only.
- MetaTrader5 cannot be imported on this Linux/WSL host; keep using dependency injection for tests.
- Analysis engines must avoid look-ahead (only past/known candles); preserve prefix stability.
- Order-flow proxy is a proxy only (INIT-005); it cannot trigger trades alone.
- No live self-mutation is allowed.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, and 10_TASK_QUEUE.md.

Continue P5-001 only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders.
Do not print credentials.
Do not bypass tests.
