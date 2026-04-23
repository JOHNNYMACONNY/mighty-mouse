---
name: autoresearch-flashpoint
description: >
  Mighty Mouse autoresearch workflow for the Flashpoint (XML-optimized) variant. 
  Follows the same Fail->Mutate, Pass->Expand logic as the core mighty workflow,
  but targets the Flashpoint prompt and results log.
---

# /autoresearch:flashpoint

Use this workflow to optimize the Flashpoint (XML-structured) coding harness.

## Goal
Improve the Flashpoint coding harness for small-model reliability. 
Mutate the prompt when failures occur. 
Expand the benchmark when the current pack passes cleanly.

## Scope
Only modify files inside these surfaces:

- `/Volumes/YBF_Storage/Projects/mighty_mouse/mighty-antigravity-flashpoint.md`
- `/Volumes/YBF_Storage/Projects/mighty_mouse/flashpoint-autoresearch-results.tsv`
- `/Volumes/YBF_Storage/Projects/mighty_mouse/benchmark/`

Do not modify the frozen B4 files or the main autoresearch results unless explicitly cross-referencing.

## Metric Priority
Optimize for benchmark reliability, not just raw completion.

Priority order:
1. `pass_rate`
2. `first_pass_rate`
3. `scope_violation_rate == 0`
4. `false_success_rate == 0`
5. `verification_compliance_rate == 1.0`
6. lower prompt bloat if all quality metrics are unchanged

## Verify Logic
Read the latest benchmark result file for the current candidate and classify the next action.

### If the current pack is not clean
If any of the following are true:
- `pass_rate < 1.0`
- `scope_violation_rate > 0`
- `false_success_rate > 0`
- `verification_compliance_rate < 1.0`

Then:
- mutate `mighty-antigravity-flashpoint.md` on **one primary axis only**
- log `mutate_and_retry` to `flashpoint-autoresearch-results.tsv`
- rerun the same pack

### If the current pack passes cleanly
If all of the following are true:
- `pass_rate == 1.0`
- `scope_violation_rate == 0`
- `false_success_rate == 0`
- `verification_compliance_rate == 1.0`

Then:
- do **not** keep polishing the same prompt
- autonomously design and create the next harder benchmark pack (e.g., `benchmark/antigravity-v11/`)
- log `expand_benchmark` to `flashpoint-autoresearch-results.tsv`

## Guard Rules
- Never mutate benchmark scores or results retroactively
- Never change both the prompt and benchmark pack in the same iteration
- Never mutate more than one primary prompt axis in a single iteration
- If a pack passes cleanly, benchmark expansion outranks prompt mutation
- Stop after 3 clean benchmark packs at the new frontier

## One-line policy
Fail -> mutate Flashpoint prompt.
Pass cleanly -> generate harder pack.
Pass 3 frontier packs -> freeze Flashpoint.
