# 02_ARCHITECTURE.md

## High-Level Architecture

XAU/USD MT5/Exness Data
→ Data Validation + Broker Health
→ Session/Kill-Zone Engine
→ Daily + 4H Bias Engine
→ Liquidity Map Engine
→ Market Structure Engine
→ FVG / Order Block / Supply-Demand Engine
→ Order-Flow Proxy Engine
→ Gold Futures Confirmation Layer
→ Regime Engine
→ Trade Hypothesis Engine
→ Confidence + Uncertainty Engine
→ Stop Placement Intelligence
→ Risk Governor
→ Execution Gateway
→ Trade Management + Trailing Stop Engine
→ Journal + State Persistence
→ Reflection Engine
→ Offline Validation
→ Controlled Improvement

## Core Separation

The system has two major parts:

1. Intelligence Brain:
   - market structure,
   - regime,
   - liquidity,
   - session behavior,
   - order-flow proxy,
   - futures confirmation,
   - confidence,
   - uncertainty,
   - reflection.

2. Execution Governor:
   - risk,
   - broker safety,
   - order validation,
   - position tracking,
   - kill switch,
   - state persistence.

The Intelligence Brain may propose. The Risk Governor decides permission.

## Layer Responsibilities

### 1. Market Data Engine

Collects and normalizes XAU/USD data including tick data, candle data, bid/ask, spread, session labels, and broker execution information.

### 2. Data Validation Engine

Detects missing candles, duplicate candles, malformed timestamps, abnormal spread, corrupted data, and inconsistent broker data.

No trading decision is allowed if data quality is invalid.

### 3. Session/Kill-Zone Engine

Classifies Asian, London, New York, London-New-York overlap, rollover, low-liquidity, and closed-market periods.

### 4. Daily + 4H Bias Engine

Defines higher-timeframe context, major liquidity, major supply/demand, premium/discount location, and directional preference.

### 5. Liquidity Map Engine

Tracks buy-side liquidity, sell-side liquidity, equal highs/lows, session highs/lows, previous day/week levels, and obvious retail stop areas.

### 6. Market Structure Engine

Detects swing highs/lows, BOS, CHOCH, liquidity sweeps, failed breakouts, range boundaries, and trend structure.

### 7. FVG / Order Block / Supply-Demand Engine

Detects fair value gaps, order-block-like zones, supply/demand areas, mitigation status, and imbalance quality.

### 8. Order-Flow Proxy Engine

Uses tick volume, spread behavior, CVD proxy, delta proxy, and tick activity carefully as broker-level proxy data, not guaranteed institutional truth.

### 9. Gold Futures Confirmation Layer

Uses gold futures data only as context, confirmation, confidence adjustment, uncertainty adjustment, or risk adjustment.

Gold futures cannot trigger trades alone.

### 10. Regime Engine

Classifies the current XAU/USD market condition as bullish trend, bearish trend, range, compression, expansion, high-volatility, choppy, liquidity-sweep environment, or no-trade environment.

### 11. Trade Hypothesis Engine

Creates structured trade hypotheses with direction, setup type, reason, invalidation level, target logic, and expected market behavior.

### 12. Confidence and Uncertainty Engine

Assigns confidence and uncertainty scores to each trade hypothesis.

High confidence alone is not enough. If uncertainty is high, the trade must be reduced, delayed, or blocked.

### 13. Stop Placement Intelligence

Places stops where the thesis is invalidated, not where retail stops commonly cluster.

### 14. Risk Governor

Approves, reduces, or blocks trades based on risk per trade, daily loss, weekly loss, consecutive losses, spread, slippage, volatility, stop-loss validity, exposure, and system health.

The risk governor has final authority over execution.

### 15. Execution Gateway

Places demo or later live trades only after risk approval. It must verify symbol, lot size, margin, stop-loss, take-profit/exit logic, spread, broker connection, order status, and state persistence.

### 16. Trade Management + Trailing Stop Engine

Manages open positions using structure-based, volatility-based, and liquidity-target trailing.

### 17. Trade Journal and State Persistence

Records every trade and every no-trade decision with timestamp, market state, regime, confidence, uncertainty, thesis, risk, execution result, and outcome.

### 18. Reflection Engine

Reviews trades and non-trades after the session. It identifies mistake patterns, regime weakness, execution problems, overconfidence, revenge behavior, poor timing, and missed opportunities.

### 19. Offline Validation Engine

Tests proposed improvements through backtests, walk-forward validation, paper trading, and comparison against the existing baseline.

### 20. Controlled Policy Update

Allows improvements to enter execution only after evidence confirms that the change improves performance without increasing unacceptable risk.

## Final Rule

All intelligence layers support the decision process but cannot bypass the Risk Governor.
