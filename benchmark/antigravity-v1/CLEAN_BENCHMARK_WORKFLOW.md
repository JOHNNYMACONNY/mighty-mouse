# Clean Benchmark Workflow

The Antigravity benchmark must not run against the mutable repo root.
Later variants can otherwise inherit earlier fixes and get free passes.

## Rule
Before every task attempt, reset a fresh workspace from `fixtures/<task_id>/`.

## One-line reset
```bash
python benchmark/antigravity-v1/scripts/reset_task_workspace.py task_ag_001_input_normalizer
```

This creates a clean working copy under `benchmark/antigravity-v1/runs/<task_id>/`.

## Antigravity usage
Tell the agent to work only inside the reset workspace path for the current task.
Score only what happens inside that fresh run directory.

## Why this is necessary
- baseline, A, B, and B2 must see the same starting code
- prior fixes in `helpers.py` and `response_parser.py` contaminate later scores
- temporary scratch artifacts should be judged relative to a clean task workspace

## Minimal protocol
1. Reset the task workspace.
2. Point the agent at `benchmark/antigravity-v1/runs/<task_id>/`.
3. Run exactly one variant on that clean copy.
4. Score the result.
5. Reset again before the next variant.
