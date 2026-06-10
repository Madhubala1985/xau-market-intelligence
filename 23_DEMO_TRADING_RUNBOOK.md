# 23_DEMO_TRADING_RUNBOOK.md

## Purpose

This file defines how supervised demo trading may be started after all gates pass.

## Pre-Demo Checklist

Before demo orders:

- all tests pass,
- .env is ignored,
- real trading disabled,
- demo account verified,
- XAU/USD symbol verified,
- risk governor tested,
- position sizing tested,
- stop-loss mandatory,
- journal writable,
- state persistence healthy,
- live shadow mode completed,
- manual user approval given.

## Demo Trading Mode

Demo trading may use:

- 0.01,
- 0.05,
- 0.10 lot,

only when risk calculation confirms the implied loss remains within the allowed tier.

## Demo Trading Goals

The goal of demo trading is not profit first.

The goal is to verify:

- signal quality,
- no-trade behavior,
- order correctness,
- stop placement,
- trailing logic,
- pyramiding safety,
- broker execution,
- state recovery,
- risk blocking,
- reflection reports.

## Demo Shutdown Conditions

Stop demo trading if:

- risk limit hit,
- two consecutive invalid trades,
- broker state mismatch,
- order state mismatch,
- journal failure,
- stop-loss attachment failure,
- unexpected order,
- spread abnormal,
- data stale,
- user kill switch activated.

## Final Rule

Demo mode is for validation.

Real mode remains forbidden.

## Serious Demo Evaluation Commands (DEMO-EVAL, Windows PowerShell)

All commands run on the Windows MT5 host from the repository root.
Real trading is forbidden in every mode below.

Preflight (13 gates, required fresh before every session):

    python scripts/demo_preflight.py

Dry-run rehearsal (full loop, plans simulated, order_send unreachable):

    python scripts/demo_session_run.py --dry-run --profile evaluation

Short smoke run (the ONLY one-order mode; first-evidence runs):

    python scripts/demo_session_run.py --confirm "START SUPERVISED DEMO" --profile smoke

1-hour supervised evaluation (policy-governed, NO artificial order cap):

    python scripts/demo_session_run.py --confirm "START SUPERVISED DEMO" --profile evaluation

London session evaluation (start at the London open):

    python scripts/demo_session_run.py --confirm "START SUPERVISED DEMO" --profile london

New York session evaluation (start at the NY open):

    python scripts/demo_session_run.py --confirm "START SUPERVISED DEMO" --profile newyork

Full-day supervised evaluation (8h hard ceiling):

    python scripts/demo_session_run.py --confirm "START SUPERVISED DEMO" --profile full_day

Stop / kill switch (halts at the next cycle; gateway also refuses sends):

    New-Item -ItemType File control\KILL_SWITCH

Release the kill switch after review:

    Remove-Item control\KILL_SWITCH

Manual news block (engage before a known event, release after):

    New-Item -ItemType File control\NEWS_BLOCK
    Remove-Item control\NEWS_BLOCK

Post-session evaluation report (offline; works on Windows or WSL):

    python scripts/demo_eval_report.py

Post-session reflection report (offline; evidence only, no self-mutation):

    python scripts/demo_reflection.py

Review order:
1. reports/runtime/demo_session.md (verdict must be CLEAN),
2. reports/runtime/demo_evaluation.md (performance + classified findings),
3. reports/runtime/demo_reflection.md (what to backtest vs fix),
4. logs/demo_trade_journal.jsonl (tickets, P&L),
5. MT5 Toolbox -> Trade/History tabs must match the journal.
