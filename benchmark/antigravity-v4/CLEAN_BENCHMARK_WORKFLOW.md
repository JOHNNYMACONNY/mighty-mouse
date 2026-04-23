# Clean Benchmark Workflow v3

Do not run this pack against the mutable repo root.
Reset from `fixtures/<task_id>/` before every attempt.

## Reset
```bash
python3 benchmark/antigravity-v3/scripts/reset_task_workspace.py <task_id>
```

## Rule
Score only what happens inside `benchmark/antigravity-v3/runs/<task_id>/`.

This pack follows the standard gated workflow:
1. **PLAN**: Define the messy context and identify the surgical fix.
2. **ACT**: Execute the fix without being distracted by technical debt.
3. **VERIFY**: Audit for side effects and manage complex state cleanup.
4. **RESULT**: Honest reporting of changes and verification limits.
