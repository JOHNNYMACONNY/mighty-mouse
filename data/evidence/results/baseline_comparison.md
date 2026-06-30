# Bare vs Harness Baseline

This report compares one raw model call per task with the recorded full-protocol baseline and Lean protocol runs. The bare condition has no Mighty Mouse prompt, checklist, adherence gate, or retry loop.

| Condition | Passed | Notes |
|---|---:|---|
| Bare Ollama control | 15/15 | One request; file materialization and frozen task tests only |
| Original harness baseline | 15/15 | Recorded paired-validation baseline |
| Lean harness | 15/15 | Recorded paired-validation Lean condition |

## Interpretation

The frozen corpus did not show a success-rate advantage over the bare control. These permissive synthetic tasks have a ceiling effect, so the result does not support a generalized reliability-improvement claim.

Latency comparisons across these artifacts are descriptive only because the runs occurred at different times and may not share identical runtime conditions.

Every condition, including failures, is retained in `bare_baseline_results.json`.
