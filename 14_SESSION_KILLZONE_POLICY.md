# 14_SESSION_KILLZONE_POLICY.md

## Purpose

This file defines session and kill-zone behavior for XAU/USD.

The system must understand that a setup depends not only on price, but also on when price appears.

## Session Model

The system must classify market time into:

- Asian session,
- London session,
- New York session,
- London-New-York overlap,
- low-liquidity periods,
- rollover period,
- weekend/closed market.

## Session Hypothesis

The system may use this working hypothesis:

- Asian session often forms range/consolidation.
- London may sweep Asian high/low.
- New York may sweep London high/low.
- Expansion may follow manipulation.
- Low-liquidity periods can create poor signals.

This is a hypothesis, not a guaranteed rule.

## Session Levels To Track

The system must track:

- Asian high,
- Asian low,
- London high,
- London low,
- New York high,
- New York low,
- previous day high,
- previous day low,
- previous week high,
- previous week low.

## Kill-Zone Rules

The system may prefer trading during active market windows only when structure confirms.

The system must not trade only because a kill zone is active.

Kill zone can increase attention but cannot trigger trades alone.

## London Sweep Logic

A London sweep is valid only when:

1. Asian high/low is taken,
2. price rejects or reclaims,
3. displacement appears,
4. lower timeframe structure confirms,
5. risk placement is valid.

## New York Sweep Logic

A New York sweep is valid only when:

1. London high/low or key liquidity is taken,
2. price rejects or continues with structure,
3. 15M/5M confirms,
4. spread is acceptable,
5. risk governor approves.

## Low-Liquidity Block

The system must reduce or block trading during:

- rollover,
- abnormal spread,
- illiquid market hours,
- unstable broker feed,
- major news release window unless news module is validated.

## Friday and Monday Caution

The system must treat Friday late sessions and Monday open as higher-risk until validated.

## Final Rule

Session context modifies confidence.

Session context cannot bypass structure, liquidity, or risk.
