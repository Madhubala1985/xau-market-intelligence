# WINMT5-001 — MT5 Demo Connectivity Runner

Read-only validation of MT5 demo connectivity for XAU/USD. **No orders are ever
placed** (the runner and validator never call `order_send` / `order_check`), and
**no credential values are printed**.

## What it proves

1. terminal path configured,
2. demo credentials load from `.env` (by NAME; values never shown),
3. MT5 initializes — or a clear **Environment Issue** is reported,
4. demo login succeeds,
5. account verified as demo / non-real (REAL accounts are refused),
6. XAU/USD symbol detected,
7. `symbol_info` read (contract size, digits, point, volume min/step),
8. latest candles fetched,
9. spread read,
10. no `order_send` is called.

Output is written to `reports/runtime/winmt5_validation.md` + `.json`
(a git-ignored runtime artifact; re-run to refresh).

## Why a Windows runner

`MetaTrader5` is a Windows-only package. In WSL / Linux it cannot be imported, so
running the script there produces an honest **ENVIRONMENT_ISSUE** report
(checks 1–2 + 10 resolved, checks 3–9 skipped pending the Windows host). Live
validation is never faked.

## Run on the Windows MT5 host

1. Install MetaTrader5 in the Windows Python:
   ```
   pip install MetaTrader5
   ```
2. Create a local `.env` on that host (never commit it) with the demo values:
   ```
   TRADING_MODE=DEMO
   REAL_TRADING_ENABLED=false
   MT5_LOGIN=<demo login>
   MT5_PASSWORD=<demo password>
   MT5_SERVER=<demo server>
   MT5_PATH=<optional path to terminal64.exe>
   MT5_SYMBOL=XAUUSD
   ```
3. Run:
   ```
   python scripts/winmt5_validate.py --stdout
   ```
4. Confirm the report shows outcome `VALIDATED` with all checks `PASS`.

## WSL → Windows bridge options

If the bot runs in WSL while MT5 runs on Windows:

- Invoke the Windows Python from WSL (e.g. call `python.exe` on the Windows side)
  to run this read-only validator.
- Or run a small Windows-side service that exposes **read-only** data only. Never
  expose an order/trade endpoint over the bridge.
- Fallback: export replay data from the terminal and validate the pipeline on
  replay (no live order path) until a live bridge is ready.

## Safety

- Demo only. Real-money trading is forbidden; a REAL account is refused.
- `.env` is local and git-ignored; credentials are never printed or committed.
- The runner exits non-zero only on a safety/connectivity failure on a host that
  has MT5; a cleanly-classified environment issue exits 0.
