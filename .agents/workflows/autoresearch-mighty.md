---
name: autoresearch-mighty
description: >
  Mighty Mouse autoresearch workflow. Mutate the /mighty harness when the
  current benchmark pack exposes failures. When the current pack passes
  cleanly, stop prompt polishing and generate the next harder benchmark pack
  instead. Freeze after 3 clean packs unless explicitly expanding the eval
  suite.
---

# /autoresearch:mighty

Use this workflow to improve the Mighty Mouse harness itself — not to run a
normal coding task.

## Goal
Improve the Mighty Mouse coding harness for small-model reliability, but only
mutate the prompt when the current benchmark pack exposes real failures. If the
current pack passes cleanly, stop prompt optimization and generate the next
harder benchmark pack instead.

## Scope
Only modify files inside these surfaces:

- `/Volumes/YBF_Storage/Projects/mighty_mouse/mighty-antigravity-frozen.md`
- `/Volumes/YBF_Storage/Projects/mighty_mouse/mighty-antigravity-gemini-flash.md`
- `/Volumes/YBF_Storage/Projects/mighty_mouse/mighty-antigravity-variant-blocks.md`
- `/Volumes/YBF_Storage/Projects/mighty_mouse/mighty-autoresearch-mutation-strategy.md`
- `/Volumes/YBF_Storage/Projects/mighty_mouse/mighty-autoresearch-log-format.md`
- `/Volumes/YBF_Storage/Projects/mighty_mouse/benchmark/`

Do not modify unrelated repo files.

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
Read the latest benchmark result file for the current candidate and classify the
next action.

### If the current pack is not clean
If any of the following are true:
- `pass_rate < 1.0`
- `scope_violation_rate > 0`
- `false_success_rate > 0`
- `verification_compliance_rate < 1.0`

Then:
- mutate `/mighty` on **one primary axis only**
- log `mutate_and_retry`
- rerun the same pack before escalating difficulty

### If the current pack passes cleanly
If all of the following are true:
- `pass_rate == 1.0`
- `scope_violation_rate == 0`
- `false_success_rate == 0`
- `verification_compliance_rate == 1.0`

Then:
- do **not** keep polishing the same prompt on the same pack
- autonomously design and create the next harder benchmark pack (including the task markdown files, necessary workspace fixtures, and scorecard YAML)
- log `expand_benchmark`

### If 3 packs have been cleared cleanly
Then:
- freeze the system
- log `promote`
- stop further prompt mutation unless explicitly instructed to keep expanding

## Guard Rules
Non-negotiable constraints:

- Never mutate benchmark scores or results retroactively
- Never grade from intent; judge from artifacts and recorded outcomes
- Never change both the prompt and benchmark pack in the same iteration
- Never mutate more than one primary prompt axis in a single iteration
- Never replace the frozen prompt unless benchmark evidence supports it
- Never broaden scope outside Mighty files and benchmark files
- Keep the benchmark scoring schema stable across packs
- Do not delete research history
- If a pack passes cleanly, benchmark expansion outranks prompt mutation
- Stop after 3 clean benchmark packs unless explicitly instructed to build a
  larger eval suite

## Cycle Ladder

### Cycle 1 — Control
Use the stable control pack.
- Fail -> mutate `/mighty`
- Clean pass -> generate Cycle 2

### Cycle 2 — Harder / adversarial
Use ambiguity, drift, multi-file temptation, and verification traps.
- Fail -> mutate `/mighty`
- Clean pass -> generate Cycle 3

### Cycle 3 — Real-world / messy
Use noisier, more realistic tasks with fuzzier judgment calls.
- Fail -> mutate `/mighty`
- Clean pass -> freeze as optimized enough

## Mutation Rule
When mutating `/mighty`, change only one primary axis per iteration:
- scope control
- verification strictness
- honesty language
- output compactness
- retry behavior

## Benchmark Expansion Rule
When generating a harder pack, increase difficulty one layer at a time:
- more ambiguity
- more drift temptation
- more multi-file pressure
- more verification traps
- more realistic/noisy context

Do not jump to giant messy tasks immediately. As the agent running the loop, you must actively create the new `benchmark/antigravity-vX/` directory, write the new task markdown files in `tasks/`, set up the initial code state in `fixtures/`, and initialize the results YAML.

## Promotion Rule
Do not promote because the prompt sounds smarter.
Promote only when benchmark evidence stays clean across all 3 packs.

## One-line policy
Fail -> mutate prompt.
Pass cleanly -> generate harder pack.
Pass 3 packs -> freeze.
