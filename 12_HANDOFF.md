# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 3: Market Structure and Liquidity

## Current Task ID:
P3-005

## Current Task Goal:
Premium/Discount Engine — mark premium/discount areas using selected swing ranges and optional Gann-box-style segmentation.

## Current Status:
P3-004 complete. FVG / order block / supply-demand engine implemented and tested.

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

## P3-004 Details

Files added/changed:
- src/structure/zones.py — ZoneEngine + Zone + ZoneKind. (Placed in src/structure/ alongside market_structure.py since FVG/OB/SD are structural zones.)
- src/structure/__init__.py — export zones API.
- tests/test_zones.py — 11 tests (valid/invalid zones + mitigation).

Design notes:
- FAIR_VALUE_GAP: 3-candle imbalance. Bullish when candle[i+1].low - candle[i-1].high > min_gap; bearish when candle[i-1].low - candle[i+1].high > min_gap. Created at i+1.
- ORDER_BLOCK: last opposing candle before a structure-breaking move (reuses P3-001 MarketStructureEngine events). Bullish break -> last bearish candle = bullish OB; created at the break index. Each origin consumed once.
- SUPPLY_DEMAND: base candle immediately before a displacement candle (range >= displacement_factor * baseline). Up displacement -> demand (BULLISH); down -> supply (BEARISH). No structure break required.
- Bias: BULLISH = demand/support (below price); BEARISH = supply/resistance (above price). Zone.size = top - bottom.
- Mitigation: a later candle overlaps the zone range (low <= top and high >= bottom). Evaluated only from candles after created_index -> no look-ahead, prefix-stable. mitigated + mitigation_index recorded.
- build() returns all kinds sorted by created_index.

Tests run:
- `.venv/bin/python -m pytest tests/ -q` → 153 passed (11 zones + 8 sweep + 9 liquidity + 8 structure + 27 sessions + 22 aggregation + 17 validation + 21 adapter + 29 schema + 1 structure-dirs).

Errors: none.

---

# Next Task

## Task:
P3-005: Premium/Discount Engine

## Goal:
Mark premium/discount areas using selected swing ranges and optional Gann-box-style segmentation.

## Allowed Files (confirm against 10_TASK_QUEUE.md before starting):
- likely src/structure/ (new module) + src/utils/ + tests/. Reuse src/structure/ swings. Do not touch src/execution|risk|strategy.

## Tests:
- correct zone mapping.

## Notes for P3-005:
- Premium = upper half of a selected swing range (above the 50% equilibrium); discount = lower half. Equilibrium = midpoint of the chosen swing high/low range.
- Optional Gann-box-style segmentation = subdividing the range into bands (e.g., quartiles or configurable fractions).
- Range selection should use confirmed swings (no look-ahead).

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

Continue P3-005 only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders.
Do not print credentials.
Do not bypass tests.
