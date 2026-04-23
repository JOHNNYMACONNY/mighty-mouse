---
name: autoresearch-native
description: >
  Mighty Mouse autoresearch workflow for IDE-Native prompt mutation and evaluation.
  Runs the Pass->Expand logic using Antigravity subagents rather than external Python scripts.
---

# /autoresearch:native

Use this workflow to optimize the IDE-Native coding harness.

## Goal
Improve the `mighty-antigravity-native.md` prompt for small-model reliability using the built-in IDE agent.
Mutate the prompt when failures occur using advanced reasoning strategies (e.g. reflection, scratchpads).
Expand the benchmark when the current pack passes cleanly.

## Scope
Only modify files inside these surfaces:
- `/Volumes/YBF_Storage/Projects/mighty_mouse/mighty-antigravity-native.md`
- `/Volumes/YBF_Storage/Projects/mighty_mouse/native-autoresearch-results.tsv`
- `/Volumes/YBF_Storage/Projects/mighty_mouse/benchmark/`

## Metric Priority
1. `pass_rate`
2. `first_pass_rate`
3. `scope_violation_rate == 0`
4. `false_success_rate == 0`

## Verify Logic
For the current iteration, read a benchmark task and instruct a subagent (using `mighty-antigravity-native.md` as its prompt) to solve it. Then run the task's test script.

### If the task is not clean (fails tests or violates scope)
Then:
- mutate `mighty-antigravity-native.md` on **one primary axis only**
- log `mutate_and_retry` to `native-autoresearch-results.tsv`
- rerun the same task with the mutated prompt

### If the task passes cleanly
Then:
- do **not** keep polishing the same prompt
- autonomously design and create the next harder benchmark pack in `benchmark/antigravity-native-v{N+1}/`
- The new task MUST test advanced agentic abilities (e.g., multi-file refactoring, debugging subtle logical errors, tracking complex state).
- The new task MUST include a Python test script (`test_main.py`) that strictly verifies the output mechanically. No fake tests.
- log `expand_benchmark` to `native-autoresearch-results.tsv`

## Guard Rules
- Never mutate benchmark scores or results retroactively
- If a pack passes cleanly, benchmark expansion outranks prompt mutation
- Stop after 3 clean benchmark packs at the new frontier

## One-line policy
Fail -> mutate native prompt.
Pass cleanly -> generate harder pack.
Pass 3 frontier packs -> freeze native prompt.
