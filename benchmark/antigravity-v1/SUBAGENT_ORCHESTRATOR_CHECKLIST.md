# Antigravity Subagent Orchestrator Checklist

Use this checklist when running the solver + grader loop.

## Per task
1. Reset clean workspace
   - `python3 benchmark/antigravity-v1/scripts/reset_task_workspace.py <task_id>`
2. Capture workspace path
   - `benchmark/antigravity-v1/runs/<task_id>/`
3. Send the task prompt + workspace path to the solver subagent
4. Collect solver output
   - final response text
   - changed files / diff summary
   - any verification claims
5. Send the original task prompt + solver output + workspace path to the grader subagent
6. Record grader output into the right result YAML
7. Repeat for next task

## Per variant
1. Run all 9 tasks
2. Aggregate:
   - pass_rate
   - first_pass_rate
   - scope_violation_rate
   - false_success_rate
   - verification_compliance_rate
3. Write summary + decision into the variant result file
4. Do not auto-promote the variant without review

## Safety rules
- Solver and grader must be separate turns or separate subagents.
- Grader must be read-only.
- Promotion decisions should remain outside the solver pass.
- Keep the current 9-task pack as the stable control pack.

## Recommended role split
- Solver: B4 or later winning candidate
- Grader: stricter read-only grading prompt
- Orchestrator: reset, dispatch, collect, write scores, aggregate metrics

## Good stopping points
Stop and review if:
- the solver starts grading itself
- the grader starts proposing code changes
- the workspace path is ignored
- repeated scope drift appears across tasks
- the variant gets better on pass rate but worse on honesty
