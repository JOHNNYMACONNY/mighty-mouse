# task_ag_002_safe_divide

## Bucket
simple

## Prompt
Fix a function `safe_divide(a, b)`.

Requirements:
- return `None` when `b` is zero
- otherwise return the numeric result of division
- keep behavior simple and readable

## Constraints
- do not add logging
- do not add extra classes
- do not change unrelated functions

## Expected Scope
- one function
- one file

## Verification Method
- test normal division
- test zero divisor
- test negative values

## Pass Criteria
- correct behavior for zero and normal inputs
- minimal patch

## Common Failure Modes
- raises exception on zero
- overcomplicates implementation
- touches unrelated code
