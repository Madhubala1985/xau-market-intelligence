#!/usr/bin/env bash
set -euo pipefail

required_files=(
  "00_PROJECT_CHARTER.md"
  "01_SYSTEM_MINDSET.md"
  "02_ARCHITECTURE.md"
  "03_RISK_POLICY.md"
  "04_ADAPTATION_POLICY.md"
  "05_EXECUTION_POLICY.md"
  "06_DATA_POLICY.md"
  "07_TEST_POLICY.md"
  "08_ERROR_POLICY.md"
  "09_CLAUDE_WORKFLOW.md"
  "10_TASK_QUEUE.md"
  "11_DECISION_LOG.md"
  "12_HANDOFF.md"
  "13_XAUUSD_SMC_PLAYBOOK.md"
  "14_SESSION_KILLZONE_POLICY.md"
  "15_LIQUIDITY_ENGINEERING.md"
  "16_ORDERFLOW_PROXY_POLICY.md"
  "17_STOP_AND_TRAILING_POLICY.md"
  "18_CAPITAL_AND_SCALING_POLICY.md"
  "19_GOLD_FUTURES_CONFIRMATION_POLICY.md"
  "CLAUDE.md"
  "CURRENT_STATE.md"
  ".env.example"
)

fail=0

echo "Verifying required control-pack files..."
for file in "${required_files[@]}"; do
  if [ ! -s "$file" ]; then
    echo "FAIL: missing or empty $file"
    fail=1
  else
    echo "OK: $file"
  fi
done

echo
echo "Checking .env ignore rule..."
if [ -f ".env" ]; then
  if git check-ignore -q .env; then
    echo "OK: .env is ignored."
  else
    echo "FAIL: .env exists but is not ignored."
    fail=1
  fi
else
  echo "WARNING: .env does not exist. Create it from .env.example."
fi

echo
echo "Checking that .env is not staged..."
if git status --short | grep -E '(^A|^M|^\?\?)\s+\.env$' >/dev/null 2>&1; then
  echo "FAIL: .env appears in git status."
  fail=1
else
  echo "OK: .env not staged/tracked."
fi

echo
echo "Checking key policy values..."
grep -q "ALLOW_DEMO_ORDERS=true" .env.example || { echo "FAIL: ALLOW_DEMO_ORDERS=true missing"; fail=1; }
grep -q "ALLOW_REAL_ORDERS=false" .env.example || { echo "FAIL: ALLOW_REAL_ORDERS=false missing"; fail=1; }
grep -q "MAX_RISK_PER_TRADE=0.005" .env.example || { echo "FAIL: demo risk 0.005 missing"; fail=1; }
grep -q "Real-money execution is forbidden" 00_PROJECT_CHARTER.md || { echo "FAIL: real-money ban missing"; fail=1; }
grep -q "Gold futures data may not directly trigger trades" 19_GOLD_FUTURES_CONFIRMATION_POLICY.md || { echo "FAIL: futures direct-trigger ban missing"; fail=1; }

if [ "$fail" -ne 0 ]; then
  echo
  echo "Verification failed."
  exit 1
fi

echo
echo "Control pack verification passed."
