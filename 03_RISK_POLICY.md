# 03_RISK_POLICY.md

## Purpose

This file defines the risk policy for the XAU/USD adaptive trading intelligence system.

Risk control has final authority. No signal, confidence score, model output, Claude suggestion, backtest result, futures confirmation, or order-flow proxy may override risk protection.

## Core Risk Philosophy

The system must survive first, protect capital second, seek profit third, and scale only after evidence.

The system must never behave like a gambler, martingale bot, revenge trader, or overconfident prediction engine.

## Capital Assumption

Expected future real-money capital: $1,500 to $2,000.

The system must be designed for small-account survival.

## Execution Stage Rules

Demo MT5 order execution is allowed after the system can connect to MT5 demo and pass execution safety checks.

Real-money execution is forbidden until explicit real-mode approval.

## Adaptive Demo Risk Policy (decision 2026-06-10-08; supersedes the fixed demo profile)

In demo mode, risk is EVIDENCE-DRIVEN, not fixed. The AdaptiveRiskEngine
decides the per-trade budget from confluence, multi-timeframe alignment,
setup class, volatility state, spread, uncertainty, drawdown, recent
performance, news state, and capital phase.

Bounds (the engine may only stay under them):

- absolute demo per-trade ceiling: 1.00%,
- per-phase ceilings and bases (ceilings reached only via evidence expansion):
  - Phase 1 (equity <  $10,000): base 0.40%, ceiling 1.00%,
  - Phase 2 ($10,000 - $15,000): base 0.35%, ceiling 0.80%,
  - Phase 3 ($15,000 - $25,000): base 0.30%, ceiling 0.60%,
  - Phase 4 (>= $25,000):        base 0.20%, ceiling 0.50%,
- maximum daily loss: 2.00% (UNCHANGED - survival anchor),
- maximum weekly loss: 5.00% (UNCHANGED - survival anchor),
- maximum trades per day: condition-driven (see the Adaptive Exposure
  Policy, decision 2026-06-10-11; ordinary bound 3, hard maximum 6 only in
  AGGRESSIVE conditions on the growth_evaluation profile),
- maximum open trades: 1 plus at most one protected add-on (UNCHANGED).

Mathematical rationale: per-trade expectancy E = r(pR - (1-p)). At p=0.45,
R=2, a flat 0.50% risk yields E ~ 0.18%/trade (~900 compounding trades to 5x
the account). Concentrating 0.8-1.0% on the elite-evidence subset roughly
halves the trades required without changing the tail bound, because the
DAILY and WEEKLY loss limits - not the per-trade cap - bound the worst
day/week: two maximum-risk losses still stop the day at -2%.

Risk must contract multiplicatively after losses, drawdown, uncertainty,
degraded spread, or open exposure; it may never expand after a loss
(no martingale structurally). Unclear news or an untradeable regime means
ZERO budget.

This policy is for demo validation only and does not approve the same risk
for real-money trading.

## Initial Real-Money Risk

When real-money mode is eventually allowed:

- maximum risk per trade: 0.25%,
- maximum daily loss: 0.50%,
- maximum weekly loss: 1.50%,
- maximum consecutive losses before shutdown: 2,
- maximum trades per day: 2,
- maximum open trades: 1,
- no scaling after early wins.

Risk may not be increased without validated live-paper and real-mode evidence.

## Adaptive Exposure Policy (decision 2026-06-10-11)

Trade-frequency limits are CONDITION-DRIVEN, not fixed. The Adaptive
Exposure Governor decides the entry allowance per cycle:

- LOCKDOWN (daily/weekly loss limit reached): 0 entries,
- BLOCKED (news block/unknown, dangerous volatility, spread at max): 0,
- DEFENSIVE (loss streak >= 2, daily drawdown >= 1%, weekly >= 3%, or news
  caution): at most 1 careful entry, single position,
- NORMAL: up to 3 entries/day, 1 position + 1 protected add-on,
- AGGRESSIVE (confluence >= 0.70 AND MTF alignment >= 0.75 in a kill-zone
  session with a clean day): up to 6 entries/day — ONLY within the
  profile's hard maximum (growth_evaluation: 6; all other profiles: 3).

Unchanged survival anchors: maximum daily loss 2.00%, maximum weekly loss
5.00%, 1 position + at most 1 protected add-on, stop-loss mandatory,
loss-at-stop risk math, no martingale/grid/averaging/revenge structurally
(adverse conditions can only SHRINK the allowance). Open positions are
always still managed regardless of exposure state.

## Mandatory Risk Checks Before Trade

Before every trade, the risk governor must check:

1. account balance,
2. available margin,
3. symbol validity,
4. lot-size validity,
5. spread,
6. slippage risk,
7. stop-loss distance,
8. broker minimum stop distance,
9. risk percentage,
10. daily loss status,
11. weekly loss status,
12. consecutive loss status,
13. open exposure,
14. news-risk status,
15. system health,
16. logging health,
17. broker connection health,
18. state persistence health.

If any critical check fails, the trade must be blocked.

## Volatility Risk Policy

The system must not block all high-volatility conditions automatically.

XAU/USD often produces opportunity during volatility.

The system must classify volatility into:

1. Tradable Volatility:
   - structure is clear,
   - liquidity sweep or displacement is valid,
   - spread is acceptable,
   - stop-loss can be placed logically,
   - risk/reward is valid.

2. Dangerous Volatility:
   - spread is abnormal,
   - candles are erratic,
   - broker feed is unstable,
   - news spike is active,
   - stop distance becomes irrational,
   - structure is unclear.

Tradable volatility may increase opportunity confidence.

Dangerous volatility must block trading.

Volatility alone may not trigger trades.

## Stop-Loss Requirement

Every trade must have a stop-loss before execution.

Trades without stop-loss are forbidden.

Removing stop-loss after entry is forbidden.

Widening stop-loss after entry to avoid a loss is forbidden.

## Position Sizing Rule

Position size must be calculated from:

- account balance,
- risk percentage,
- stop-loss distance,
- symbol contract size,
- broker lot rules,
- spread,
- slippage buffer.

The system must never reduce stop-loss distance only to increase position size.

If the logical stop is too wide, the system must reduce size or skip the trade.

## Shutdown Rules

The system must stop trading if:

- daily loss limit is reached,
- weekly loss limit is reached,
- consecutive loss limit is reached,
- broker execution becomes inconsistent,
- logging fails,
- state persistence fails,
- spread exceeds safe threshold,
- critical system error occurs.

## Forbidden Risk Behavior

The system must never use:

- martingale,
- grid trading,
- averaging down,
- revenge trading,
- no-stop-loss trading,
- oversized lots,
- emotional recovery trades,
- trade doubling after loss,
- automatic risk increase after wins.

## Final Rule

If the Risk Governor says NO TRADE, the system must not execute.
