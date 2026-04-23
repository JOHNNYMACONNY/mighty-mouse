# Mighty Mouse Antigravity Benchmark Pack

## Purpose
This benchmark pack is the first focused evaluation set for Mighty Mouse inside Antigravity using Gemini 3 Flash.

The pack is intentionally small and high-signal. It is meant to guide early autoresearch iterations without drowning the loop in noise.

## Recommended Size
Start with 24 tasks total:
- 6 simple tasks
- 8 medium tasks
- 5 drift-trap tasks
- 5 honesty-trap tasks

## Buckets

### Bucket A: Simple
Purpose:
- establish baseline competence
- measure first-pass improvement on common low-complexity tasks

Task types:
- one-file bug fix
- small function implementation
- validation edge case
- small refactor with clear expected behavior

Metrics emphasized:
- success rate
- first-pass success
- output brevity

### Bucket B: Medium
Purpose:
- test structured reasoning without overwhelming the model
- measure whether Mighty Mouse improves multi-step reliability

Task types:
- two-file repair
- constrained bug fix
- preserve-existing-behavior edits
- add validation without breaking interfaces
- small multi-step debugging task

Metrics emphasized:
- success rate
- retry recovery
- verification compliance
- scope discipline

### Bucket C: Drift Traps
Purpose:
- test whether the harness reduces unnecessary edits and wandering

Task types:
- prompt includes unrelated nearby files
- task has explicit do-not-touch instructions
- extra context tempts over-refactor
- only one function needs fixing but multiple seem relevant
- misleading phrasing that invites overscoped solutions

Metrics emphasized:
- scope violation rate
- file touch precision
- adherence to constraints

### Bucket D: Honesty Traps
Purpose:
- test whether the harness reduces fake confidence and fabricated verification

Task types:
- missing tests
- incomplete environment context
- ambiguous requirements
- impossible-to-confirm success conditions
- tasks where a bluff is easy but verification is hard

Metrics emphasized:
- false-success rate
- verification compliance
- blocker honesty

## Initial Benchmark Design Principles
- Prefer realistic coding tasks over puzzle tasks
- Keep each task small enough for repeated testing
- Include explicit expected constraints
- Make pass/fail criteria clear
- Record not just success or failure, but failure category

## Per-Task Template
Each task should define:
- task_id
- title
- bucket
- prompt
- constraints
- expected_files_or_scope
- verification_method
- pass_criteria
- common_failure_modes

## Baseline Rule
Before comparing Mighty Mouse variants, capture baseline performance for:
- Gemini 3 Flash in Antigravity without Mighty Mouse

## Promotion Rule
A variant is only better if it improves the benchmark pack on primary metrics without introducing too much verbosity or friction.

## Expansion Rule
Do not scale the benchmark pack until the initial 24-task set is producing stable signal.
First get clarity, then add volume.
