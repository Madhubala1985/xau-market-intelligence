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

## Continuous Trading Service (CONTINUOUS-001, Windows PowerShell)

The MAIN way to run the system. It trades the MT5 account configured in
.env (currently Exness DEMO, so orders are demo orders) and keeps running
until you stop it. All commands from the repository root.

1. Preflight (also runs automatically at every service start):

    py -3.12 scripts\demo_preflight.py

2. Continuous dry-run rehearsal (identical loop, sending disabled):

    py -3.12 scripts\trading_service.py --profile continuous --dry-run --stdout-progress

3. Continuous MT5 execution on the .env account (sending requires the .env
   flags: TRADING_MODE=DEMO, REAL_TRADING_ENABLED=false,
   ALLOW_DEMO_ORDERS=true, ALLOW_MT5_ORDER_SEND=true, ALLOW_REAL_ORDERS=false):

    py -3.12 scripts\trading_service.py --profile continuous --stdout-progress

4. Stop safely (service halts at the next check; Ctrl+C also stops cleanly):

    New-Item -ItemType File control\KILL_SWITCH

5. Resume after review (remove the switch, start the service again):

    Remove-Item control\KILL_SWITCH
    py -3.12 scripts\trading_service.py --profile continuous --stdout-progress

6. Evaluation report (daily service_eval_* are written automatically; this
   evaluates a bounded session report):

    py -3.12 scripts\demo_eval_report.py

7. Reflection report:

    py -3.12 scripts\demo_reflection.py

8. View the latest journal / reports from PowerShell:

    Get-Content logs\demo_trade_journal.jsonl -Tail 20
    Get-Content logs\service_heartbeat.jsonl -Tail 5
    Get-Content reports\runtime\trading_service.md
    Get-ChildItem reports\runtime\service_eval_*.md | Sort-Object Name | Select-Object -Last 1 | Get-Content

Where trades appear: MT5 terminal -> Toolbox -> Trade tab (open positions)
and History tab (closed trades). Every sent order prints its ticket in the
terminal and journals it (notes="ticket=<n>").

What you see immediately after start: the startup banner (service name,
profile, masked login, account type, server, symbol, mode, risk limits,
news, kill switch, journal/report paths, stop instructions) followed by a
"[cycle 1]" progress block within one poll interval. While the market is
closed you see "MARKET CLOSED (...) — waiting" lines instead of silence.
