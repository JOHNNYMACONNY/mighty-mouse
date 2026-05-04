# Plan: Phase 17 - Full Regression Coverage & Milestone Archiving

## Step 1: Complete V14 Restoration
- Implement fixtures for Task 003 (Selective Rollback).
- Implement fixtures for Task 005 (Adversarial Lint/Secure HTTP).

## Step 2: Bootstrap V15 (Adversarial Frontier)
- Create `benchmark/antigravity-v15/tasks/` with 5 new adversarial task definitions.
- Create `benchmark/antigravity-v15/fixtures/` for all 5 tasks.
- Ensure each task has a strictly mechanical verification script.

## Step 3: Final Regression Run
- Execute the stress test across V13, V14, and V15.
- Verify 100% pass rate.
- Document the results in `flashpoint-autoresearch-results.tsv`.

## Step 4: Milestone Audit & Archive
- Generate `v7-MILESTONE-AUDIT.md`.
- Move Milestone 7 to the archive if all UATs pass.

## Verification
- All 15 tasks (V13-V15) pass successfully.
- Fixtures are persisted and committed.
