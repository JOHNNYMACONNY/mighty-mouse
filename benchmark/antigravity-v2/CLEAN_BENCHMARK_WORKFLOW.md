# Clean Benchmark Workflow v2

Do not run this pack against the mutable repo root.
Reset from `fixtures/<task_id>/` before every attempt.

## Reset
```bash
python3 benchmark/antigravity-v2/scripts/reset_task_workspace.py <task_id>
```

## Rule
Score only what happens inside `benchmark/antigravity-v2/runs/<task_id>/`.
