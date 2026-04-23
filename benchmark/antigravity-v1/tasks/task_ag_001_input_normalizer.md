# task_ag_001_input_normalizer

## Bucket
simple

## Prompt
Fix a small Python helper called `normalize_name(value)`.

Requirements:
- trim leading and trailing whitespace
- collapse internal runs of whitespace to a single space
- return an empty string for `None`
- preserve normal characters and punctuation

## Constraints
- edit only the helper implementation
- do not add unrelated utilities
- keep the solution simple

## Expected Scope
- one helper function
- one file

## Verification Method
- test with `None`
- test with extra spaces
- test with already clean input

## Pass Criteria
- all normalization rules are correctly handled
- no extra scope drift

## Common Failure Modes
- forgets `None`
- strips punctuation
- rewrites unrelated helpers
