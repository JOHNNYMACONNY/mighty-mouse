# task_ag_003_env_flag

## Bucket
simple

## Prompt
Implement `is_enabled(value)` for environment-style inputs.

Requirements:
- truthy strings: `1`, `true`, `yes`, `on`
- falsy strings: `0`, `false`, `no`, `off`, empty string
- case-insensitive
- non-string values should be converted to string first

## Constraints
- no imports
- no unrelated helper functions
- keep logic compact

## Expected Scope
- one function
- one file

## Verification Method
- test mixed casing
- test empty input
- test non-string input like `1`

## Pass Criteria
- values map correctly
- no banned imports

## Common Failure Modes
- case-sensitive comparisons
- forgetting non-string conversion
- adding unnecessary helpers
