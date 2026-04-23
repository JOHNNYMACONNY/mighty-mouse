# Antigravity Operator Runbook

Use this runbook to execute the Mighty Mouse benchmark loop with a solver subagent and a separate grader subagent.

## Goal
Run one variant across the stable 9-task control pack with:
- clean per-task workspaces
- a solver pass
- a separate read-only grader pass
- consistent score-sheet updates

## Files to keep open
- `benchmark/antigravity-v1/CLEAN_BENCHMARK_WORKFLOW.md`
- `benchmark/antigravity-v1/SUBAGENT_SOLVER_PROMPT.md`
- `benchmark/antigravity-v1/SUBAGENT_GRADER_PROMPT.md`
- `benchmark/antigravity-v1/SUBAGENT_ORCHESTRATOR_CHECKLIST.md`
- the target result YAML for the variant you are testing

## Recommended current setup
- Solver variant: **B4**
- Grader: separate read-only grading pass
- Benchmark pack: current 9-task Antigravity control pack

## Per-task flow
### 1. Reset the clean workspace
```bash
python3 benchmark/antigravity-v1/scripts/reset_task_workspace.py <task_id>
```

This creates:
```bash
benchmark/antigravity-v1/runs/<task_id>/
```

### 2. Run solver pass
In a fresh Antigravity chat or clean solver turn:
- paste the solver prompt from `SUBAGENT_SOLVER_PROMPT.md`
- paste the task prompt
- include the workspace path

Solver must:
- work only inside the run workspace
- solve the task
- report changed files, verification, and whether new files/imports were added

### 3. Capture solver artifacts
Collect:
- original task prompt
- workspace path
- solver final response text
- changed files / diff summary

### 4. Run grader pass
In a separate fresh grading turn:
- paste the grader prompt from `SUBAGENT_GRADER_PROMPT.md`
- provide the task prompt
- provide workspace path
- provide solver response
- provide changed files / diff summary

Grader returns only:
- success
- first_pass
- scope_violation
- false_success
- verification_compliance
- notes

### 5. Record the score
Write the grader output into the variant result YAML.

### 6. Repeat
Repeat steps 1-5 for the next task.

## Per-variant flow
After all 9 tasks:
1. aggregate summary metrics
2. write summary into result YAML
3. compare against baseline and prior variants
4. decide whether to:
   - reject
   - keep testing
   - mutate again
   - expand benchmark pack

## Promotion rule
Do not promote automatically.
Promotion should happen only after reviewing:
- pass rate
- scope violation rate
- false-success rate
- verification compliance
- failure mode concentration

## Current benchmark strategy
- keep the current 9-task pack as the control pack
- use it to compare prompt variants apples-to-apples
- only expand difficulty after a variant clearly wins the control pack

## Current recommendation
- B4 is the best current solver candidate
- next big move is either:
  - use B4 in the solver/grader loop, or
  - expand to a harder second-wave pack after validating loop stability

## Common failure checks
Watch for:
- solver grading itself
- grader proposing code changes
- wrong workspace path
- leftover temp files
- claims of cleanup that did not happen
- claims of verification on code that is not runnable as written
