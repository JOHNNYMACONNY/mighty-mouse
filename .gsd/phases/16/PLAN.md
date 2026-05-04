# Plan: Phase 16 - Flashpoint Reliability Stress Test

## Step 1: Benchmark Restoration
- Investigate why `benchmark/antigravity-v14/fixtures` and `benchmark/antigravity-v15/tasks` are empty.
- Restore the missing files from previous logs, git history, or by regenerating them based on the task descriptions if necessary.
- Reset all fixtures in V13, V14, V15 to their initial "broken" state (e.g., circular dependencies in V14, rounding errors in V13).

## Step 2: Sequential Stress Test
- **V13 Run**: Execute the `/autoresearch:flashpoint` logic for Pack V13.
- **V14 Run**: Execute the `/autoresearch:flashpoint` logic for Pack V14.
- **V15 Run**: Execute the `/autoresearch:flashpoint` logic for Pack V15.

## Step 3: Verification & Audit
- Check `flashpoint-autoresearch-results.tsv` for new entries.
- Ensure all tasks passed with `pass_rate == 1.0` and no `scope_violation`.
- Produce a summary of the stress test results.

## Verification
- `flashpoint-autoresearch-results.tsv` contains successful runs for V13, V14, and V15.
- Milestone 7 objectives are met.
