# 22_MT5_WINDOWS_VALIDATION.md

## Purpose

This file defines MT5 demo validation requirements.

Claude Code may run in WSL, while MT5 is installed on Windows. Therefore direct MT5 integration may require a Windows-side Python runner or bridge.

## Required Behavior

Claude must not force unsafe integration.

If MetaTrader5 cannot import in WSL, classify it as Environment Issue and create a safe adapter boundary.

## MT5 Validation Requirements

The system must prove:

1. MT5 terminal path is configured,
2. demo credentials are loaded from .env without printing values,
3. MT5 initializes,
4. demo login succeeds,
5. account is demo or not real-money,
6. XAU/USD symbol mapping is correct,
7. symbol_info is available,
8. latest candles can be fetched,
9. spread can be read,
10. no order_send is called during data validation.

## Host Options

Allowed approaches:

1. Windows Python runner,
2. WSL-to-Windows bridge,
3. future MT5 EA/socket bridge,
4. manual exported replay data if live bridge is not ready.

## Forbidden Behavior

Claude must not:

- print credentials,
- commit credentials,
- call order_send in data-validation tasks,
- enable real trading,
- bypass missing MT5 by faking live validation,
- mark MT5 live validation complete without real evidence.

## Final Rule

MT5 validation is not complete until real demo terminal data is proven.
