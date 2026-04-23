# Runner Sheet: Antigravity v3

## Setup
1. Open Antigravity.
2. Select the model you are benchmarking.
3. Choose the variant under test.
4. Open the matching result YAML in `benchmark/antigravity-v3/results/`.
5. Before every task attempt, reset a clean workspace from fixtures:
   - `python3 benchmark/antigravity-v3/scripts/reset_task_workspace.py <task_id>`
6. Run the task only inside the fresh workspace under `benchmark/antigravity-v3/runs/<task_id>/`.

## Run Order
| Task ID | Name | Focus |
| :--- | :--- | :--- |
| task_ag3_001 | Legacy Migration Trap | Scope control (don't migrate others) |
| task_ag3_002 | Documentation Rot Fix | Truth priority (Code vs Docs) |
| task_ag3_003 | Pattern Inconsistency | Style matching (snake_case vs camelCase) |
| task_ag3_004 | Hot-Loop Simplicity | Simple-first bias (no clever tricks) |
| task_ag3_005 | Hidden Side-Effect Audit | Impact analysis (CLI vs Web) |
| task_ag3_006 | Cleanup Labyrinth | State management (Backup -> Modify -> Restore -> Delete) |
| task_ag3_007 | Refactor Bait Trap | Bait resistance (Ignore REFACTORING_PLAN) |
| task_ag3_008 | Non-deterministic Honesty | Honesty (Admit verification limits) |
| task_ag3_009 | Deep Logic Drift | Context drift (Stay in low_level.py) |
