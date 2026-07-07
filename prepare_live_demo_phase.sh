#!/usr/bin/env bash
set -euo pipefail

cd ~/XAU_Model

echo "Preparing Phase 12: Risk upgrade + live demo readiness workflow..."

if [ ! -d ".git" ]; then
  echo "ERROR: Not a git repository."
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: Working tree has uncommitted changes. Commit or stash first."
  git status
  exit 1
fi

timestamp="$(date +%Y%m%d_%H%M%S)"
mkdir -p reports/runtime scripts configs

backup_file() {
  local file="$1"
  if [ -f "$file" ]; then
    cp "$file" "${file}.bak_${timestamp}"
    echo "Backup: ${file}.bak_${timestamp}"
  fi
}

backup_file CURRENT_STATE.md
backup_file 12_HANDOFF.md
backup_file 10_TASK_QUEUE.md
backup_file 11_DECISION_LOG.md
backup_file .env.example

cat > 20_LEVERAGE_AND_PYRAMIDING_POLICY.md <<'EOF'
# 20_LEVERAGE_AND_PYRAMIDING_POLICY.md

## Purpose

This file defines leverage-aware XAU/USD position sizing and protected pyramiding.

The system may use leverage in demo, but leverage must never bypass max-loss rules.

The system must calculate actual loss at stop-loss before every trade.

## Core Rule

Stop distance comes from structure.

Lot size comes from allowed risk.

Leverage only affects margin requirement. Leverage does not reduce trade loss if stop-loss is hit.

## Required Calculations

Before any trade, the system must calculate:

- account balance,
- free margin,
- symbol contract size,
- tick size,
- tick value,
- minimum lot,
- lot step,
- maximum lot,
- requested lot,
- stop-loss distance,
- loss per lot at stop,
- implied USD loss,
- implied account risk percentage,
- margin required,
- total open XAU/USD risk,
- same-direction exposure,
- correlated exposure.

## Demo Confidence Risk Tiers

Demo may use higher risk than real mode for validation.

Allowed demo tiers:

### NO_TRADE

Used when setup is weak, unclear, conflicting, or invalid.

Risk: 0.

### NORMAL_SETUP

Used when setup is valid but not elite.

Maximum loss: $40.

### HIGH_CONFLUENCE_SETUP

Used when structure, liquidity, session, regime, and execution quality are strongly aligned.

Maximum loss: $80.

### ELITE_A_PLUS_SETUP

Used only in demo and only when all confluence conditions are present.

Maximum loss: $100.

## Real Risk Separation

Real-money launch risk remains conservative.

Real mode must not inherit demo tier limits.

Initial real-money risk remains controlled by 03_RISK_POLICY.md and 18_CAPITAL_AND_SCALING_POLICY.md.

## Fixed Lot Rule

The system may consider 0.01, 0.05, or 0.10 lot in demo only after calculating implied loss at the structural stop.

Fixed lot size may never bypass max-loss rules.

If 0.10 lot creates excessive loss, reduce or block.

If broker minimum lot creates excessive risk, block.

## Protected Pyramiding

Adding another same-direction trade is allowed only when:

1. the existing trade is already protected at break-even or locked profit,
2. the first trade is not moving toward its original stop-loss,
3. the add-on trade has a fresh valid setup,
4. the add-on trade has its own thesis, invalidation, stop-loss, and risk calculation,
5. HTF bias, liquidity direction, and regime still support continuation,
6. total combined XAU/USD exposure remains within the allowed demo cap.

## Forbidden Pyramiding

The system must not:

- add to a losing trade,
- add when price is moving toward original stop-loss,
- add to recover a bad entry,
- add only because leverage is available,
- add if total open risk exceeds the cap,
- add if the first trade is not protected,
- add if the new trade lacks its own setup.

## After Stop-Loss

If original stop-loss is hit, the model may trade again only after a fresh independent setup forms.

A new trade after stop-loss must not be a revenge trade.

## Final Rule

Add to winners only.

Never add to losers.

Every add-on is a new trade thesis.

Total exposure remains controlled.
EOF

cat > 21_LIVE_DEMO_VALIDATION_PLAN.md <<'EOF'
# 21_LIVE_DEMO_VALIDATION_PLAN.md

## Purpose

This file defines the next phase after the completed P0-P11 roadmap.

The goal is to move from tested architecture to live demo validation.

## Phase 12 Goal

Connect the completed DecisionPipeline to real or replayed XAU/USD data, validate MT5 demo connectivity, run live shadow mode, and only then allow supervised demo order execution.

## Non-Negotiable Safety Rules

1. Real-money trading remains forbidden.
2. Demo order execution is allowed only after required gates pass.
3. No credentials may be printed or committed.
4. .env must remain ignored.
5. The pipeline must not execute orders directly.
6. ExecutionGateway remains the only order pathway.
7. Risk Governor remains final authority.
8. The system must stop safely on broker/data/state inconsistency.

## Required Gate Sequence

### Gate 1: RISK-001

Implement leverage-aware confidence-tiered sizing and protected pyramiding.

### Gate 2: LIVE-VERIFY-001

Generate an evidence pack showing what is implemented, what is tested, what is stubbed, and what is not live-proven.

This is not a broad rewrite or re-audit.

### Gate 3: WINMT5-001

Validate MT5 demo connection on the correct host.

Required proof:

- MT5 initializes,
- demo login works,
- XAU/USD symbol is detected,
- symbol info is read,
- latest candles are fetched,
- spread is read,
- account info is read without printing credentials,
- no order_send is called.

### Gate 4: LIVE-001

Create live/replay adapter feeding DecisionPipeline into ShadowRunner.

No orders.

### Gate 5: LIVE-002

Run live shadow mode for XAU/USD.

No orders.

Required output:

- pipeline decisions,
- rejected trade reasons,
- confidence/uncertainty,
- risk decisions,
- journal entries,
- session report.

### Gate 6: DEMO-001

Run demo execution preflight.

Allowed only after live shadow is stable.

### Gate 7: DEMO-002

Run supervised MT5 demo order execution.

Demo orders only.

No real orders.

## Demo Order Permission

Demo orders are allowed only when:

- TRADING_MODE=DEMO,
- REAL_TRADING_ENABLED=false,
- ALLOW_REAL_ORDERS=false,
- ALLOW_DEMO_ORDERS=true,
- ALLOW_MT5_ORDER_SEND=true,
- Risk Governor approves,
- ExecutionGateway approves,
- broker account is verified as demo,
- state persistence is healthy,
- journal is writable.

## Final Rule

The project may proceed to demo execution.

The project may not proceed to real-money execution.
EOF

cat > 22_MT5_WINDOWS_VALIDATION.md <<'EOF'
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
EOF

cat > 23_DEMO_TRADING_RUNBOOK.md <<'EOF'
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
EOF

# Append Phase 12 queue once.
if ! grep -q "Phase 12: Live Demo Readiness" 10_TASK_QUEUE.md; then
cat >> 10_TASK_QUEUE.md <<'EOF'

---

# Phase 12: Live Demo Readiness

## Task RISK-001: Leverage-Aware Sizing and Protected Pyramiding

Goal:
Update risk/position-sizing logic so the system understands XAU/USD lot size, contract size, min lot, lot step, margin, leverage, stop distance, implied USD loss, total open risk, confidence-tiered demo sizing, and protected add-on trades.

Rules:
- Do not enable real trading.
- Do not place orders.
- Do not print credentials.
- Do not touch .env.
- Demo may allow higher loss caps than real mode.
- Real-money initial risk remains conservative.
- 0.05 and 0.10 lot may be allowed in demo only if calculated stop-loss risk is inside the demo tier cap.
- Fixed lot size must never bypass calculated risk.
- Leverage/margin availability must never bypass max-loss rules.
- Adding another same-direction trade is allowed only when the existing trade is protected at break-even or locked profit.
- Adding to a losing trade is forbidden.

Required tests:
- 0.01, 0.05, and 0.10 lot XAU/USD scenarios,
- leverage/margin cannot bypass max-loss rules,
- pyramiding allowed only into protected winning trades,
- averaging down / adding into loss is blocked,
- total open XAU/USD exposure enforced.

Stop condition:
- all tests pass,
- docs updated,
- commit RISK-001.

---

## Task LIVE-VERIFY-001: Generate Implementation Evidence Pack

Goal:
Create a compact report showing implemented modules, tested modules, stubbed/mocked modules, live-proven modules, and not-yet-live-proven modules.

Rules:
- No broad rewrite.
- No strategy changes.
- No order placement.

Stop condition:
- evidence report created under reports/runtime/,
- commit LIVE-VERIFY-001.

---

## Task WINMT5-001: Validate MT5 Demo Connectivity

Goal:
Validate MT5 demo terminal connectivity and XAU/USD read-only data.

Rules:
- No orders.
- No order_send.
- No credentials printed.
- If WSL cannot import MetaTrader5, create a Windows-side runner or safe bridge plan.

Required proof:
- MT5 init/login,
- demo account verified,
- XAU/USD symbol detected,
- symbol info read,
- candles fetched,
- spread read,
- account info read safely.

Stop condition:
- validation report created,
- commit WINMT5-001.

---

## Task LIVE-001: Connect Live/Replay Data to DecisionPipeline and ShadowRunner

Goal:
Feed real or replayed XAU/USD data into DecisionPipeline and ShadowRunner.

Rules:
- No orders.
- Pipeline may generate decisions.
- ShadowRunner may log would-trade decisions.
- ExecutionGateway must not send orders.

Stop condition:
- end-to-end shadow run works on replay/live data,
- tests pass,
- commit LIVE-001.

---

## Task LIVE-002: Run Live Shadow Session

Goal:
Run supervised XAU/USD live shadow mode with real market data.

Rules:
- No orders.
- Log every decision and no-trade.
- Produce session report.

Stop condition:
- shadow session report created,
- commit LIVE-002.

---

## Task DEMO-001: Demo Execution Preflight

Goal:
Verify all demo execution gates before order_send is allowed.

Rules:
- No real orders.
- Demo only.
- Check all env flags.
- Verify account is demo.
- Verify stop-loss enforcement.
- Verify risk governor.
- Verify journal/state persistence.

Stop condition:
- preflight report created,
- commit DEMO-001.

---

## Task DEMO-002: Supervised MT5 Demo Trading Run

Goal:
Run supervised MT5 demo trading with XAU/USD only.

Rules:
- Demo only.
- Real trading forbidden.
- Risk governor final authority.
- Stop-loss mandatory.
- Protected pyramiding only.
- Manual kill switch required.
- Session report required.

Stop condition:
- supervised demo session completed,
- journal and reflection report created,
- commit DEMO-002.
EOF
fi

cat > CURRENT_STATE.md <<'EOF'
# CURRENT_STATE.md

## Project

XAU/USD Adaptive Liquidity Intelligence System

## Current Phase

Phase 12: Live Demo Readiness

## Current Task

RISK-001: Leverage-Aware Sizing and Protected Pyramiding

## Last Completed Task

P0-P11 roadmap completed.
INT-001: DecisionPipeline integration completed.

## Next Task

RISK-001

## Current Execution Mode

DEMO_CONFIGURED_BUT_NOT_YET_LIVE_VALIDATED

## Real Trading

FORBIDDEN

## Demo Trading

ALLOWED ONLY AFTER PHASE 12 GATES PASS

## Paper / Shadow Trading

ALLOWED

## Environment Status

- .env.example exists.
- .env is local only and ignored by git.
- Demo MT5 credentials may be stored only in .env.
- Real credentials are forbidden.
- MT5 live validation is not yet proven in this phase.

## Next Exact Action

Start RISK-001:
Implement leverage-aware confidence-tiered sizing and protected pyramiding.

## Safety Notes

- Do not commit .env.
- Do not enable real trading.
- Do not print credentials.
- Do not place orders in RISK-001.
- Do not start demo orders until WINMT5-001, LIVE-001, LIVE-002, and DEMO-001 pass.
EOF

cat > 12_HANDOFF.md <<'EOF'
# 12_HANDOFF.md

## Purpose

This file allows Claude sessions to resume without losing direction.

Claude must update this file before stopping, before token/session exhaustion, after major task completion, or after unresolved errors.

---

# Current Project State

## Current Phase:
Phase 12: Live Demo Readiness

## Current Task ID:
RISK-001

## Current Task Goal:
Implement leverage-aware confidence-tiered sizing and protected pyramiding.

## Current Status:
P0-P11 roadmap is complete. INT-001 DecisionPipeline is complete. Next phase prepares the system for live shadow and supervised MT5 demo execution.

---

# Completed Work

- P0-P11 roadmap completed and tested.
- INT-001 completed: engines wired into DecisionPipeline.
- Real-money execution remains forbidden.

---

# Next Task

## Task:
RISK-001: Leverage-Aware Sizing and Protected Pyramiding

## Goal:
Update risk/position-sizing logic so the system understands XAU/USD lot size, contract size, min lot, lot step, margin, leverage, stop distance, implied USD loss, total open risk, confidence-tiered demo sizing, and protected add-on trades.

## Required Behavior:
1. Stop distance comes from structure, not desired dollar loss.
2. Lot size is calculated from allowed risk and stop distance.
3. Fixed lot size may never bypass calculated risk.
4. 0.05 and 0.10 lot are allowed in demo only if implied stop-loss risk is inside the demo tier cap.
5. Leverage/margin availability cannot bypass max-loss rules.
6. Add-on trades are allowed only when the existing trade is protected at break-even or locked profit.
7. Adding to a losing trade is forbidden.
8. Total open XAU/USD exposure must remain capped.
9. Real-money initial risk remains conservative.

## Allowed Files:
- src/risk/
- src/strategy/
- src/trade_management/
- src/data/
- tests/
- CURRENT_STATE.md
- 12_HANDOFF.md
- 11_DECISION_LOG.md

## Forbidden Files:
- .env
- real-money configuration
- uncontrolled execution code

## Required Tests:
- 0.01, 0.05, and 0.10 lot XAU/USD scenarios,
- leverage/margin cannot bypass max-loss rules,
- pyramiding allowed only into protected winning trades,
- averaging down / adding into loss is blocked,
- total open XAU/USD exposure enforced.

---

# Current Known Risks

- Real-money trading is forbidden.
- Demo order execution must wait for Phase 12 gates.
- Exness/MT5 credentials must not be committed.
- .env must remain local only.
- MT5 live terminal validation is not yet proven.
- No live self-mutation is allowed.

---

# Resume Prompt For Claude

Read CLAUDE.md, CURRENT_STATE.md, 12_HANDOFF.md, 10_TASK_QUEUE.md, 20_LEVERAGE_AND_PYRAMIDING_POLICY.md, and 21_LIVE_DEMO_VALIDATION_PLAN.md.

Continue the current task only.

Do not broaden scope.
Do not trade real money.
Do not place demo orders unless the current task explicitly allows it and all gates pass.
Do not print credentials.
Do not bypass tests.
EOF

cat >> 11_DECISION_LOG.md <<'EOF'

---

## Decision ID:
PHASE12-001

## Date:
2026-06-09

## Area:
Live Demo Readiness / Risk / Execution

## Decision:
After P0-P11 and INT-001, the next phase is Phase 12: Live Demo Readiness.

## Reason:
The architecture and pipeline are implemented, but real MT5 demo connectivity, live shadow behavior, leverage-aware sizing, protected pyramiding, and supervised demo execution still require controlled validation.

## Risk:
Starting demo trading without these gates could create unsafe order behavior, over-risking, credential exposure, or false confidence.

## Mitigation:
Use staged gates: RISK-001, LIVE-VERIFY-001, WINMT5-001, LIVE-001, LIVE-002, DEMO-001, DEMO-002.

## Status:
Accepted
EOF

# Add env example values if missing.
append_env_if_missing() {
  local key="$1"
  local value="$2"
  if ! grep -q "^${key}=" .env.example; then
    echo "${key}=${value}" >> .env.example
  fi
}

append_env_if_missing "DEMO_RISK_PROFILE" "aggressive_validation"
append_env_if_missing "DEMO_MAX_LOSS_NORMAL" "40"
append_env_if_missing "DEMO_MAX_LOSS_HIGH_CONFLUENCE" "80"
append_env_if_missing "DEMO_MAX_LOSS_ELITE" "100"
append_env_if_missing "DEMO_MAX_TOTAL_OPEN_RISK" "100"
append_env_if_missing "ALLOW_PROTECTED_PYRAMIDING" "true"
append_env_if_missing "MAX_PYRAMID_TRADES" "2"

cat > scripts/pre_demo_safety_check.sh <<'EOF'
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
if grep -R "REAL_TRADING_ENABLED=true\|ALLOW_REAL_ORDERS=true" -n \
  --exclude-dir=.git --exclude=".env" . >/dev/null 2>&1; then
  echo "FAIL: tracked files contain real-trading enablement."
  grep -R "REAL_TRADING_ENABLED=true\|ALLOW_REAL_ORDERS=true" -n \
    --exclude-dir=.git --exclude=".env" .
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
EOF

chmod +x scripts/pre_demo_safety_check.sh

bash scripts/pre_demo_safety_check.sh
python -m pytest tests/ -q

git add \
20_LEVERAGE_AND_PYRAMIDING_POLICY.md \
21_LIVE_DEMO_VALIDATION_PLAN.md \
22_MT5_WINDOWS_VALIDATION.md \
23_DEMO_TRADING_RUNBOOK.md \
10_TASK_QUEUE.md \
CURRENT_STATE.md \
12_HANDOFF.md \
11_DECISION_LOG.md \
.env.example \
scripts/pre_demo_safety_check.sh

git commit -m "PHASE12-001: add live demo readiness workflow"

echo
echo "Phase 12 workflow prepared and committed."
echo
echo "Now start Claude and use the global continuation prompt."
