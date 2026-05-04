# Context: Phase 17 - Full Regression Coverage & Milestone Archiving

## Objective
Restore all missing benchmark fixtures for V14 and V15 and run a final, 100% autonomous regression pass for Milestone 7.

## Scope
- Benchmarks: `antigravity-v14`, `antigravity-v15`.
- Tasks:
  - V14: 003 (Rollback), 005 (Secure Lint).
  - V15: 001-005 (New adversarial tasks).

## Requirements
- All tasks must have valid, failing initial fixtures.
- All tasks must have a `test_runner.py` or equivalent for mechanical verification.
- The Flashpoint harness must clear the entire 15-task suite in one go.

## Decisions
- We will recreate V15 from scratch as an "Adversarial Frontier" pack.
- We will use the existing `autoresearch-flashpoint.md` logic to run the batch.
