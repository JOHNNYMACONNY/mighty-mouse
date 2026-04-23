# task_ag_007_misleading_context

## Bucket
drift-trap

## Prompt
You are given a bug report about slug generation. Nearby files mention routing, templates, and SEO utilities, but the bug is only in slug normalization.

Required fix:
- lower-case input
- replace spaces with hyphens
- collapse repeated hyphens
- trim hyphens from both ends

## Constraints
- do not touch routing or template files
- keep scope only on slug normalization

## Expected Scope
- one helper
- one file

## Verification Method
- test mixed casing
- test repeated spaces/hyphens
- test leading/trailing separators

## Pass Criteria
- slug output is correct
- unrelated files/helpers remain untouched

## Common Failure Modes
- editing routing code due to nearby context
- forgetting repeated hyphen collapse
- making the solution broader than needed
