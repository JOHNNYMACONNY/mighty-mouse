# task_ag_004_two_file_validation

## Bucket
medium

## Prompt
A small Python app validates a signup payload across two files.

Required fix:
- ensure empty email values are rejected
- ensure whitespace-only names are rejected
- preserve existing behavior for valid payloads

## Constraints
- keep the public function names unchanged
- do not refactor unrelated code
- keep changes limited to validation flow

## Expected Scope
- two files max
- validation logic only

## Verification Method
- test valid payload
- test empty email
- test whitespace-only name

## Pass Criteria
- invalid payloads fail correctly
- valid payload still passes
- no unrelated edits

## Common Failure Modes
- changes interface names
- only fixes one invalid case
- rewrites broader module structure
