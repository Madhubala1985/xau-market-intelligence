# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 4: Regime and Bias

## Current Task ID:
P4-002

## Current Task Goal:
Regime Engine — classify trend, range, compression, expansion, choppy, news-risk, no-trade.

## Current Status:
P4-001 complete. Daily and 4H bias engine implemented and tested.

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

## P4-001 Details

Files added/changed:
- src/regime/htf_bias.py — HtfBiasEngine + BiasResult + HtfBias enum.
- src/regime/__init__.py — package exports.
- tests/test_htf_bias.py — 10 tests (bias cases).

Design notes:
- Each timeframe's directional bias = market-structure final_bias (P3-001, the trend after the latest BOS/CHOCH).
- Daily is the primary authority; 4H confirms. Combination matrix:
  - daily None (no data) -> NO_TRADE.
  - daily NEUTRAL -> NEUTRAL.
  - daily BULLISH: 4H BEARISH -> NO_TRADE (conflict); else BULLISH.
  - daily BEARISH: 4H BULLISH -> NO_TRADE (conflict); else BEARISH.
  - Missing 4H is treated as "not opposing" (daily leads).
- Output enum HtfBias: BULLISH / BEARISH / NEUTRAL / NO_TRADE. BiasResult also carries daily_bias, h4_bias (Optional[Bias], None == insufficient), and a reason string.
- No look-ahead: structure bias is prefix-stable.

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 174 passed (10 htf-bias + 11 premium/discount + 11 zones + 8 sweep + 9 liquidity + 8 structure + 27 sessions + 22 aggregation + 17 validation + 21 adapter + 29 schema + 1 structure-dirs).

Errors: none.

---

# Next Task

## Task:
P4-002: Regime Engine

## Goal:
Classify trend, range, compression, expansion, choppy, news-risk, no-trade.

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- likely src/regime/ + src/utils/ + tests/. Reuse src/structure/ (structure events / swings) and src/data/. Do not touch src/execution|risk|strategy.

## Tests:
- regime cases.

## Notes for P4-002:
- Trend: clear directional structure (consistent BOS in one direction). Range: bounded between swing high/low, no BOS. Compression: contracting volatility/range (narrowing). Expansion: widening range / displacement. Choppy: frequent alternating CHOCH / conflicting structure. News-risk and no-trade may be flagged from external/uncertain conditions (news-risk likely needs a news input later; for now allow a no-trade/unclear default).
- Reuse structure events (BOS/CHOCH counts), swing-range width, and candle range statistics. No look-ahead.

---

# Current Known Risks

- Real-money trading is forbidden.
- Demo order execution must not be implemented (data / analysis only).
- Exness/MT5 credentials must not be committed and must never be printed.
- .env must remain local only.
- MetaTrader5 cannot be imported on this Linux/WSL host; keep using dependency injection for tests.
- Analysis engines must avoid look-ahead (only past/known candles); preserve prefix stability.
- No live self-mutation is allowed.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, and 10_TASK_QUEUE.md.

Continue P4-002 only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders.
Do not print credentials.
Do not bypass tests.
