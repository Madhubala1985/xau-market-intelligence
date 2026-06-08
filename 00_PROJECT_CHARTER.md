# 00_PROJECT_CHARTER.md

## Project Identity

This project builds an XAU/USD-only adaptive liquidity intelligence system.

The system is not a retail indicator bot, not a fixed algorithmic bot, not a martingale/grid system, and not an LLM-controlled gambling agent.

The system is designed as a self-observing, evidence-gated trading intelligence that studies XAU/USD market behavior, classifies regime, understands liquidity and structure, controls risk, executes only when conditions are valid, records every decision, reflects on mistakes, and improves through validated offline learning.

## Core Objective

The objective is not to maximize trade frequency.

The objective is to achieve long-term survival and risk-adjusted profitability by taking only high-quality XAU/USD opportunities where structure, regime, liquidity, volatility, execution quality, and risk are aligned.

## Non-Negotiable Rules

1. XAU/USD is the only tradable instrument.
2. Demo execution through MT5 is allowed after connection and execution safety checks.
3. Real-money execution is forbidden until explicit real-readiness approval.
4. Every trade must have a clear thesis, invalidation level, stop-loss, risk amount, and reason code.
5. No trade is allowed if the risk governor blocks it.
6. No live self-modification of trading logic is allowed during market hours.
7. No martingale, grid trading, averaging down, or no-stop-loss logic is allowed.
8. No trade may be placed if logging, state persistence, broker connection, or position tracking is inconsistent.
9. The system must treat NO TRADE as a valid intelligent decision.
10. The system must preserve capital before seeking profit.
11. The system must adapt only through evidence-gated review, testing, and validation.

## System Philosophy

The system must behave better than a human trader by avoiding emotional failure modes such as fear, greed, revenge trading, overconfidence, panic after losses, and uncontrolled strategy changes.

The system must not revenge trade after losses.

The system must not become overconfident after wins.

The system must not surrender when the market becomes difficult.

The system must protect capital, observe, classify failure, learn from evidence, and return only when conditions are safe.

## Definition of Intelligence

In this project, intelligence means:

- understanding market context,
- knowing when not to trade,
- measuring confidence and uncertainty,
- protecting capital,
- detecting its own mistakes,
- improving only after validation,
- refusing action when evidence is insufficient.

Intelligence does not mean predicting every candle or forcing trades.
