#!/usr/bin/env bash
set -euo pipefail

fail=0

echo "Running pre-demo safety checks..."

if [ -f ".env" ]; then
  if git check-ignore -q .env; then
    echo "OK: .env is ignored."
  else
    echo "FAIL: .env exists but is not ignored."
    fail=1
  fi
else
  echo "WARN: .env not found. Demo MT5 credentials not configured locally."
fi

if git status --short | grep -E '(^A|^M|^\?\?)\s+\.env$' >/dev/null 2>&1; then
  echo "FAIL: .env appears in git status."
  fail=1
else
  echo "OK: .env is not staged/tracked."
fi

echo "Checking tracked files for forbidden real-trading enablement..."
# Scan only git-tracked files (so .env and untracked generators are not scanned)
# and exclude this checker, whose own pattern definition would self-match.
real_pat='REAL_TRADING_ENABLED''=true|ALLOW_REAL_ORDERS''=true'
real_scope=(-- . ':(exclude)scripts/pre_demo_safety_check.sh')
if git grep -nE "$real_pat" "${real_scope[@]}" >/dev/null 2>&1; then
  echo "FAIL: tracked files contain real-trading enablement."
  git grep -nE "$real_pat" "${real_scope[@]}"
  fail=1
else
  echo "OK: no real-trading enablement found in tracked files."
fi

echo "Checking required Phase 12 files..."
for file in \
  20_LEVERAGE_AND_PYRAMIDING_POLICY.md \
  21_LIVE_DEMO_VALIDATION_PLAN.md \
  22_MT5_WINDOWS_VALIDATION.md \
  23_DEMO_TRADING_RUNBOOK.md; do
  if [ ! -s "$file" ]; then
    echo "FAIL: missing or empty $file"
    fail=1
  else
    echo "OK: $file"
  fi
done

if [ "$fail" -ne 0 ]; then
  echo "Pre-demo safety check failed."
  exit 1
fi

echo "Pre-demo safety check passed."
