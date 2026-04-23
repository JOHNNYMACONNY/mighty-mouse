# task_ag_005_preserve_behavior_refactor

## Bucket
medium

## Prompt
A helper is duplicated in two nearby places. Consolidate the duplication without changing behavior.

Requirements:
- preserve output exactly
- reduce duplication in the narrowest safe way
- keep call sites understandable

## Constraints
- do not change external behavior
- do not rename public functions
- avoid broad file movement

## Expected Scope
- one or two files
- minimal refactor

## Verification Method
- compare output before and after for representative inputs
- confirm public names stay intact

## Pass Criteria
- duplication reduced
- outputs unchanged
- refactor remains small

## Common Failure Modes
- changes behavior while refactoring
- renames interfaces unnecessarily
- spreads edits too broadly
