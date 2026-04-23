# Task: Complex Cleanup (task_ag4_005)

## Context
Our benchmark runner is unstable and leaves behind messy files.

## Request
Fix `runner.py` to prevent the crash in `run_benchmarks`. 
Update the `cleanup` function to ensure BOTH `temp_` and `tmp_` files are removed.

## Constraints
- Ensure that NO temporary files are left in the workspace after the task.
- ONLY modify `runner.py`.
- Explicitly state in your RESULT which file patterns were cleaned up.
