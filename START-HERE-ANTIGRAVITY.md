# START HERE: Mighty Mouse in Antigravity

## What This Is
This folder contains the first real research package for Mighty Mouse as an Antigravity-first slash-command harness, starting with **Gemini 3 Flash**.

The goal is to answer:
- does `/mighty` improve Gemini 3 Flash in Antigravity?
- which prompt variant works best?
- how should `/autoresearch` mutate the harness over time?

Current answer:
- **B4 / structured-simple-first** is the winning first productized candidate
- default real-use reference: `mighty-antigravity-frozen.md`

## First-Time Run Order
Follow this order:

### 1. Read the core docs
- `mighty-core.md`
- `mighty-antigravity-frozen.md`
- `mighty-antigravity-gemini-flash.md`
- `mighty-scorecard.md`

### 2. Read the Antigravity research docs
- `.gsd/AUTORESEARCH-SPEC-ANTIGRAVITY.md`
- `mighty-antigravity-variant-blocks.md`
- `mighty-autoresearch-mutation-strategy.md`

### 3. Open the benchmark pack
- `benchmark/antigravity-v1/runner-sheet.md`
- `benchmark/antigravity-v1/quick-test-checklist.md`
- `benchmark/antigravity-v1/CLEAN_BENCHMARK_WORKFLOW.md`
- `benchmark/antigravity-v1/SELF_GRADING_LOOP.md`
- `benchmark/antigravity-v1/OPERATOR_RUNBOOK.md`
- `benchmark/antigravity-v1/SUBAGENT_SOLVER_PROMPT.md`
- `benchmark/antigravity-v1/SUBAGENT_GRADER_PROMPT.md`
- `benchmark/antigravity-v1/SUBAGENT_ORCHESTRATOR_CHECKLIST.md`
- `benchmark/antigravity-v1/b2-grading-notes.md` (when scoring Variant B2)

### 4. Start with baseline
Use:
- `baseline-run-antigravity.md`
- `benchmark/antigravity-v1/results/baseline-gemini-3-flash.yaml`

### 5. Run first-wave variants
Use these result files:
- `benchmark/antigravity-v1/results/variant-a-compact-core.yaml`
- `benchmark/antigravity-v1/results/variant-b-structured-full.yaml`
- `benchmark/antigravity-v1/results/variant-c-scope-first.yaml`

### 6. If Variant B looks promising but drifts
Use:
- `benchmark/antigravity-v1/results/variant-b2-structured-tight-scope.yaml`
- `benchmark/antigravity-v1/results/variant-b3-structured-no-artifacts.yaml`

Current recommendation:
- use **B4 / structured-simple-first** as the first real `/mighty` default
- keep the older variants as research history and fallback material
- use benchmark packs plus `/autoresearch` only when you want to challenge or replace the frozen candidate

## Recommended Testing Order
Historical order:
1. **Baseline**, Gemini 3 Flash with no Mighty Mouse
2. **Variant A**, Compact Core
3. **Variant B**, Structured Full
4. **Variant C**, Scope-First
5. **Variant B2**, Structured Full Tight Scope
6. **Variant B3**, Structured Full No-Artifacts
7. **Variant B4**, Structured Full Simple-First

Current practical order:
1. use `mighty-antigravity-frozen.md` for real tasks
2. benchmark it again only when you have a new challenge pack or a mutation candidate worth testing

## What To Compare
After each run, compare:
- pass rate
- first-pass success
- scope violation rate
- false-success rate
- verification compliance
- output length / friction

## If You’re Running `/autoresearch`
Use this loop:
1. run benchmark pack
2. review score sheet
3. identify biggest failure mode
4. mutate one primary axis only
5. re-run
6. promote only if scorecard improves meaningfully

Use:
- `mighty-autoresearch-log-format.md`
- `mighty-autoresearch-mutation-strategy.md`

## Current Truth
Right now, the project is centered on:
- **Antigravity**
- **user-selected Gemini 3 Flash in chat**
- **portable `/mighty` harness design**
- **field-mode research before broad packaging**
- **clean per-task fixture resets before every benchmark attempt**

## Long-Term Goal
Once Mighty Mouse is clearly useful here, package it so it can be installed easily as a slash command / skill in other environments too.

## Current freeze point
The current freeze point is the B4-derived productized block in `mighty-antigravity-frozen.md`.

## If You Forget Everything Else
Open these 3 files:
- `benchmark/antigravity-v1/runner-sheet.md`
- `benchmark/antigravity-v1/quick-test-checklist.md`
- `benchmark/antigravity-v1/results/baseline-gemini-3-flash.yaml`

That is enough to start testing again fast.
