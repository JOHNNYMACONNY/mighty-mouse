# Quick Test Checklist: Antigravity + Gemini 3 Flash

## Before You Start
- Open Antigravity
- Select **Gemini 3 Flash**
- Open `runner-sheet.md`
- Open the matching results file:
  - baseline-gemini-3-flash.yaml
  - variant-a-compact-core.yaml
  - variant-b-structured-full.yaml
  - variant-c-scope-first.yaml

## Baseline Run
For each task:
- paste the task prompt
- do **not** use `/mighty`
- record:
  - success/fail
  - first-pass yes/no
  - scope violation yes/no
  - false-success yes/no
  - verification compliance yes/no
  - quick notes

## Variant Run
For each task:
- activate the chosen Mighty Mouse variant
- paste the task prompt
- record:
  - success/fail
  - first-pass yes/no
  - scope violation yes/no
  - false-success yes/no
  - verification compliance yes/no
  - quick notes

## Fast Scoring Rules
### success
- yes if the task was actually solved
- no if solution is wrong, incomplete, or drifts too hard

### first-pass
- yes if solved without needing repair/retry
- no otherwise

### scope_violation
- yes if it touched unrelated files/logic or broadened scope unnecessarily
- no if it stayed tight

### false_success
- yes if it claimed success or testing without enough evidence
- no if it stayed honest

### verification_compliance
- yes if it meaningfully verified or honestly explained verification limits
- no if it hand-waved verification

## Suggested Run Order
1. Baseline
2. Variant A
3. Variant B
4. Variant C

## After Each Run
Fill in summary fields:
- pass_rate
- first_pass_rate
- scope_violation_rate
- false_success_rate
- verification_compliance_rate
- avg_output_length
- decision

## Keep In Mind
- Don’t overthink the scoring
- Be consistent across variants
- If a task feels ambiguous, note it in `notes`
- If Gemini 3 Flash behavior feels materially different on a later day, refresh baseline
