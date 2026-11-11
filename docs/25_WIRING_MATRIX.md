# 25_WIRING_MATRIX.md

## Purpose

The explicit, evidence-backed wiring status of every intelligence layer in
the LIVE continuous service path (INTELLIGENCE-002 audit, 2026-06-10):

    MT5 data -> DecisionPipeline -> confluence engines -> AdaptiveRiskEngine
      -> DemoTradePlanner/Sizer/PyramidingGuard -> RiskGovernor
      -> ExecutionGateway -> MT5 account (.env) -> journal/reports

Statuses: LIVE (wired into the continuous path, tested), PARTIAL (real but
limited, limitation stated), PLACEHOLDER (interface only, honestly absent),
MISSING (not present). Nothing below is fake-wired: every PARTIAL/PLACEHOLDER
limitation is visible at runtime (terminal/banner) instead of pretended away.

## Matrix

| # | Layer | Status | Evidence (code -> live call site -> test) |
|---|---|---|---|
| 1 | MTF alignment (D1/H4/H1/M15/M5, M1 trigger) | LIVE | `strategy/confluence.py:MtfAlignmentEngine`; true MT5 fetches in `execution/demo_session.py:_cycle` (M15/H1/M1) + `pipeline._mtf_frames` (honest aggregation fallback, labelled in `sources`); tests `test_demo_session.py::test_session_fetches_true_mtf_timeframes`, `test_intelligence_pipeline.py::test_true_mt5_timeframes_are_used_when_supplied`, degradation test |
| 2 | Liquidity sweep | LIVE | `liquidity/sweep.py` -> `pipeline.decide` (setup driver + confluence component + chop subtype input); `test_confluence.py::test_sweep_evidence_raises_the_score` |
| 3 | BOS/CHOCH | LIVE | `structure/market_structure.py` -> structure bias, confluence `bos_choch`, continuation setup gate; `test_intelligence_pipeline.py::test_bos_continuation_setup_trades_without_a_sweep` |
| 4 | FVG | LIVE | `structure/zones.py` -> `pipeline.decide` zones -> confluence `fvg`; `test_confluence.py::test_fvg_evidence_raises_the_score` |
| 5 | Order blocks (+ supply/demand) | LIVE | same wiring, confluence `order_block`; `test_order_block_evidence_raises_the_score` |
| 6 | Premium/discount | LIVE | `structure/premium_discount.py` -> `pipeline.decide` -> confluence `premium_discount`; `test_premium_discount_location_matters` |
| 7 | Displacement | LIVE | `pipeline._displacement_ratio` -> confluence component + continuation gate + chop classifier; `test_displacement_raises_the_score` |
| 8 | Session logic (kill zones) | LIVE | `data/sessions.py` -> scoring + confluence `session`; CycleStat.session |
| 9 | Asian range | LIVE (new) | `data/session_levels.py:AsianRangeEngine` -> `pipeline.decide` -> confluence `asian_range` + terminal line; `test_session_levels.py`, `test_confluence.py::test_asian_sweep_supports_the_trap_direction` |
| 10 | London/NY expansion | LIVE (new) | same module: sweep-of-Asian-liquidity + expansion ratio; `test_london_expansion_below_the_range` |
| 11 | Tick-volume / orderflow PROXY | LIVE (labelled proxy) | `orderflow/proxy.py` -> pipeline scoring + confluence `orderflow`; never a trade signal (`is_trade_signal=False`) |
| 12 | Volatility regime | LIVE | `regime/regime_engine.py` (recent-window) + graded chop subtypes (`regime/chop_classifier.py`) |
| 13 | Dangerous volatility classifier | LIVE (new) | `regime/volatility_classifier.py` -> hard gate in `pipeline.decide`; EXPANSION never blocks alone; `test_volatility_classifier.py`, `test_dangerous_volatility_blocks_despite_full_bearish_evidence` |
| 14 | News/macro risk | PARTIAL (honest) | NewsProvider architecture (`risk/news_guard.py`): manual block + StaticCalendarProvider with impact/category; 5 states (CLEAR/BLOCK/UNKNOWN/HIGH_IMPACT_SOON/ACTIVE); HIGH active blocks, MEDIUM/soon reduce risk (adaptive contraction); open positions still managed. Real feed = NEWS-001 |
| 15 | Futures confirmation | PARTIAL (honest) | `FileMacroProvider` (configs/macro_context.json, stale-aware) feeds the confluence `futures` component; candle engine remains placeholder; UNAVAILABLE_BY_CONFIG when the operator file is absent/stale. Real feed = FUTURES-001 |
| 16 | Stop placement | LIVE | `trade_management/stop_placement.py` -> `pipeline.decide` step 6; stop mandatory end-to-end (schema+gateway+governor) |
| 17 | Trailing / break-even | LIVE | `trade_management/position_manager.py` -> `demo_session._manage_positions` -> `gateway.modify_stop` (never widens); `test_break_even_protection_applied_via_gateway` |
| 18 | Adaptive risk | LIVE | `risk/adaptive_risk.py` -> pipeline sizing + planner hard cap (`demo_session._try_entry` risk_budget); per-phase ceilings per the Adaptive Demo Risk Policy; `test_adaptive_risk.py` (20) |
| 19 | Opportunity audit | LIVE | `reflection/opportunity_audit.py` -> `trading_service._track_opportunity` (60 active-session no-trade cycles); verdicts NO_TRADE_CORRECT / MISSED_SWEEP_REVERSAL / MISSED_CONTINUATION / POSSIBLY_TOO_STRICT / DATA_INSUFFICIENT / MIXED; `test_opportunity_audit.py` |
| 20 | Reflection / evaluation loop | LIVE | `reflection/demo_evaluation.py` -> daily rollover reports in `trading_service._write_day_reports` + `scripts/demo_eval_report.py` / `demo_reflection.py`; offline only, no self-mutation |
| 21 | Macro DXY/yields | PARTIAL (honest) | `FileMacroProvider` + `gold_pressure()` -> confluence `macro` component + adaptive macro-conflict contraction; UNAVAILABLE_BY_CONFIG without the operator file. Real feed = MACRO-001 |
| 22 | M1 refinement | LIVE (new) | `strategy/m1_refinement.py` -> pipeline veto-or-pass AFTER a setup exists; delay/avoid only, never creates trades (`test_m1_refinement.py`) |
| 23 | Wiring verification | LIVE (new) | `reflection/wiring_verification.py` + `scripts/verify_wiring.py`: EXECUTED pipeline decision + class introspection; current result 16 LIVE / 1 PARTIAL / 2 UNAVAILABLE_BY_CONFIG / 0 MISSING |

## Executable verification

Run `python scripts/verify_wiring.py` any time — it executes a real pipeline
decision on synthetic candles and writes
reports/runtime/wiring_verification.md with per-layer evidence. Exit 2 if any
layer reads MISSING.

## Remaining PARTIAL / PLACEHOLDER (honest backlog)

- NEWS-001: real economic-calendar HTTP feed. Until then: manual block +
  impact/category static calendar (fail-closed; HIGH blocks, MEDIUM/soon
  reduce).
- MACRO-001 / FUTURES-001: live DXY/yields/futures feeds. Until then: the
  stale-aware operator file configs/macro_context.json (UNAVAILABLE when
  absent/stale; never guessed).
- BACKTEST-001: the calibration replay now reports drawdown, false
  positives, missed sweep/continuation decomposition, per-segment
  expectancies, and a KEEP/TIGHTEN/LOOSEN/NEED_MORE_DATA verdict; the
  actual real-history run + walk-forward decision is the pending work.
- M1 refinement is live as a delay/avoid layer; it still carries no
  alignment weight (calibrate before weighting).
