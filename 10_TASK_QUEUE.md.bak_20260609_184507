# 10_TASK_QUEUE.md

## Purpose

This file defines the ordered implementation roadmap.

Claude must complete tasks in order unless explicitly instructed otherwise.

---

# Phase 0: Project Foundation

## Task P0-001: Create Project Control Pack

Goal:
Create and verify all control-pack files.

Expected output:
- all control-pack files completed,
- CLAUDE.md completed,
- CURRENT_STATE.md completed,
- verification script passes.

Tests:
- scripts/verify_control_pack.sh

Stop condition:
- commit P0-001.

---

## Task P0-002: Create Repository Structure

Status:
Completed in commit P0-002.

Expected folders:
- src/data
- src/broker
- src/execution
- src/risk
- src/structure
- src/regime
- src/liquidity
- src/orderflow
- src/strategy
- src/trade_management
- src/journal
- src/reflection
- src/backtest
- src/utils
- tests
- configs
- data/raw
- data/processed
- logs
- reports
- scripts

---

# Phase 1: Data Foundation

## Task P1-001: Define Core Data Schemas

Goal:
Create schemas for Candle, Tick, SpreadSnapshot, SessionState, BrokerState, TradeDecision, TradeRecord.

Allowed files:
- src/data
- src/utils
- tests

Tests:
- schema validation tests.

Stop condition:
- schemas pass tests.

---

## Task P1-002: MT5 Demo Data Adapter

Goal:
Connect to MT5 demo terminal and fetch XAU/USD candles safely.

Rules:
- demo credentials loaded from .env,
- no real trading,
- order sending disabled unless explicit demo execution task,
- symbol must be XAU/USD mapped carefully.

Tests:
- adapter initializes,
- fetches latest candles,
- rejects wrong symbols,
- does not print credentials.

Stop condition:
- validated sample candle output.

---

## Task P1-003: Data Validation Engine

Goal:
Detect missing candles, duplicate candles, stale data, bad OHLC, spread anomalies, timestamp issues.

Tests:
- malformed data is rejected,
- valid data passes,
- invalid data produces NO_TRADE status.

---

# Phase 2: Session and Timeframe Context

## Task P2-001: Timeframe Aggregation

Goal:
Build reliable 1M to 5M/15M/1H/4H/Daily aggregation.

Tests:
- aggregation correctness,
- no future leakage.

---

## Task P2-002: Session/Kill-Zone Engine

Goal:
Classify Asian, London, New York, London-New-York overlap, low-liquidity periods.

Tests:
- timestamp-to-session mapping,
- session highs/lows tracking.

---

# Phase 3: Market Structure and Liquidity

## Task P3-001: Swing and Structure Engine

Goal:
Detect swing highs/lows, BOS, CHOCH.

Tests:
- fixed candle examples.

---

## Task P3-002: Liquidity Map Engine

Goal:
Detect buy-side liquidity, sell-side liquidity, equal highs/lows, session highs/lows, previous day/week highs/lows.

Tests:
- known examples.

---

## Task P3-003: Liquidity Sweep Engine

Goal:
Detect sweep, rejection, reclaim, displacement confirmation.

Tests:
- true sweep,
- false sweep,
- no sweep.

---

## Task P3-004: FVG / Order Block / Supply-Demand Engine

Goal:
Detect FVGs, order-block-like zones, supply/demand zones, mitigation status.

Tests:
- valid/invalid zones.

---

## Task P3-005: Premium/Discount Engine

Goal:
Mark premium/discount areas using selected swing ranges and optional Gann-box-style segmentation.

Tests:
- correct zone mapping.

---

# Phase 4: Regime and Bias

## Task P4-001: Daily and 4H Bias Engine

Goal:
Classify higher-timeframe bias as bullish, bearish, neutral, or no-trade.

Tests:
- bias cases.

---

## Task P4-002: Regime Engine

Goal:
Classify trend, range, compression, expansion, choppy, news-risk, no-trade.

Tests:
- regime cases.

---

# Phase 5: Order-Flow Proxy and Futures Context

## Task P5-001: Order-Flow Proxy Engine

Goal:
Use MT5 tick volume, spread behavior, tick movement, and optional delta/CVD proxy cautiously.

Tests:
- proxy values calculated,
- no direct trade signal from proxy alone.

---

## Task P5-002: Gold Futures Confirmation Layer

Goal:
Add optional gold futures confirmation context.

Rules:
- no look-ahead bias,
- futures confirms confidence only,
- futures cannot trigger trade alone.

Tests:
- confirmation boosts/reduces confidence,
- missing futures data does not break core system.

---

# Phase 6: Trade Hypothesis and Scoring

## Task P6-001: Trade Hypothesis Engine

Goal:
Generate LONG, SHORT, WAIT, NO_TRADE hypotheses with thesis, invalidation, target logic.

Tests:
- no thesis = no trade,
- no invalidation = no trade.

---

## Task P6-002: Confidence and Uncertainty Engine

Goal:
Score structure, liquidity, regime, volatility, session, order-flow proxy, futures confirmation, execution quality.

Tests:
- high uncertainty blocks/reduces trade,
- confidence alone cannot bypass risk.

---

# Phase 7: Risk and Execution

## Task P7-001: Risk Governor

Goal:
Implement full risk checks.

Tests:
- all risk-blocking cases.

---

## Task P7-002: Position Sizing

Goal:
Calculate lot size from risk, stop distance, broker contract rules, spread/slippage buffer.

Tests:
- correct lot calculation,
- excessive risk blocked.

---

## Task P7-003: MT5 Demo Execution Gateway

Goal:
Place MT5 demo trades only after risk approval.

Tests:
- wrong symbol blocked,
- no SL blocked,
- duplicate blocked,
- order state logged,
- no credentials printed.

---

# Phase 8: Trade Management

## Task P8-001: Stop Placement Intelligence

Goal:
Place stop beyond thesis invalidation using volatility and liquidity buffer.

Tests:
- obvious stop rejected,
- logical stop accepted.

---

## Task P8-002: Trailing Stop Engine

Goal:
Implement structure-based, volatility-based, and liquidity-target trailing.

Tests:
- no premature trailing,
- no widening stop,
- valid partial/runners.

---

# Phase 9: Journal and Reflection

## Task P9-001: Trade Journal

Goal:
Log every trade and no-trade decision.

Tests:
- decisions persisted,
- restart-safe.

---

## Task P9-002: Reflection Engine

Goal:
Classify mistakes and generate daily review.

Tests:
- mistake categories assigned.

---

# Phase 10: Backtest and Validation

## Task P10-001: Backtesting Engine

Goal:
Backtest with spread, slippage, risk, stop logic, session logic.

Tests:
- no future leakage,
- realistic fills.

---

## Task P10-002: Walk-Forward Validation

Goal:
Validate on unseen periods.

Tests:
- train/test split,
- no leakage.

---

# Phase 11: Live Shadow and Real Readiness

## Task P11-001: Live Shadow Mode

Goal:
Run live market analysis without sending real-money orders.

Tests:
- live decisions logged,
- real orders not sent.

---

## Task P11-002: Real-Mode Readiness Review

Goal:
Verify all gates before real money.

Rules:
- no real execution without manual approval.

Stop condition:
- readiness report only.
