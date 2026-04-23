# Mighty Mouse Autoresearch Log Format

## Purpose
This file defines the minimum logging format for Antigravity-first Mighty Mouse autoresearch runs.

The goal is to make every iteration comparable, explainable, and easy to review.

## Per-Iteration Record
Each autoresearch iteration should capture:

- iteration_id
- date_time
- host_environment
- selected_model
- variant_id
- variant_name
- prompt_version
- benchmark_pack_version
- total_tasks
- pass_rate
- first_pass_rate
- retry_recovery_rate
- scope_violation_rate
- false_success_rate
- verification_compliance_rate
- avg_output_length
- avg_turn_count
- notable_failures
- major_failure_categories
- lessons_learned
- decision

## Decision Values
Allowed decision values:
- promote
- reject
- keep_testing
- mutate_and_retry

## Example Record
```yaml
iteration_id: ag-g3f-iter-01
date_time: 2026-04-20T22:00:00-07:00
host_environment: antigravity
selected_model: gemini-3-flash
variant_id: variant-b
variant_name: structured-full
prompt_version: mighty-antigravity-v1b
benchmark_pack_version: ag-pack-v1
total_tasks: 24
pass_rate: 0.67
first_pass_rate: 0.50
retry_recovery_rate: 0.34
scope_violation_rate: 0.12
false_success_rate: 0.08
verification_compliance_rate: 0.79
avg_output_length: 540
avg_turn_count: 1.4
notable_failures:
  - task_ag_014 drifted into unrelated helper refactor
  - task_ag_021 claimed likely success without sufficient evidence
major_failure_categories:
  - scope_drift
  - false_success
lessons_learned:
  - stronger scope language helped on constrained edits
  - verification wording still too soft on ambiguous tasks
decision: mutate_and_retry
```

## Minimum Summary View
Every research batch should also produce a compact summary table with:
- variant
- pass rate
- first-pass rate
- retry recovery
- scope violation
- false-success rate
- avg output length
- decision

## Qualitative Notes
Metrics are not enough by themselves. Also capture:
- whether the variant felt natural in chat
- whether it was annoyingly verbose
- whether it improved trust
- whether retries were actually useful instead of repetitive

## Promotion Rule
Do not promote a variant only because it sounds stricter or smarter.
Promote it only when logs show a meaningful improvement on the scorecard.
