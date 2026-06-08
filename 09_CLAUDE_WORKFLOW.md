# 09_CLAUDE_WORKFLOW.md

## Purpose

This file defines how Claude Code must work on this project.

Claude must follow project files, not random direction changes.

## Source of Truth

Claude must read:

1. CLAUDE.md,
2. CURRENT_STATE.md,
3. 12_HANDOFF.md,
4. 10_TASK_QUEUE.md,
5. the relevant policy files for the current task.

## Work Rule

Claude must work only on the current task from TASK_QUEUE unless explicitly instructed otherwise.

## Task Format

Every task must have:

- Task ID,
- Goal,
- Allowed files,
- Forbidden files,
- Expected output,
- Tests to run,
- Evidence required,
- Stop condition.

## No Broad Audit Rule

Claude must not perform broad audits unless the current task requires it.

Claude must inspect only files relevant to the task.

## No Architecture Drift Rule

Claude must not change architecture without:

1. explaining why,
2. identifying affected files,
3. updating ARCHITECTURE.md,
4. updating DECISION_LOG.md,
5. receiving explicit approval if change affects risk or execution.

## Token Efficiency Rule

At the end of each task, Claude must report only:

- completed files,
- tests run,
- result,
- unresolved issues,
- next task.

## Session Limit Rule

If Claude approaches token/session limit, it must update 12_HANDOFF.md with:

- current task,
- completed work,
- changed files,
- failed tests,
- next exact command,
- known risks,
- do-not-touch items.

The next Claude session must resume from HANDOFF.md.

## Commit Rule

Claude should commit only after:

- task is complete,
- tests pass,
- handoff/state is updated,
- no unrelated files are included.

Commit message format:

Task-ID: concise description

## Forbidden Claude Behavior

Claude must not:

- change goals,
- expand scope unnecessarily,
- rewrite stable modules without reason,
- bypass tests,
- bypass risk,
- invent broker facts,
- hallucinate data availability,
- mark incomplete work as done,
- modify real-money settings without explicit approval.

## Final Rule

Claude is an implementation agent, not the final authority.
