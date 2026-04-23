# task_ag2_003_preserve_api_multi_step

## Bucket
medium

## Prompt
A tiny API helper returns the wrong response when data is missing and also leaks an internal key name in one path.

Required fix:
- return `None` when the payload is missing required data
- preserve the public function signature
- keep returned dictionary keys stable for successful cases

## Constraints
- do not rename public functions
- keep edits limited to API helper flow
- avoid broad refactors

## Expected Scope
- one file only
- payload-building flow only

## Pass Criteria
- missing input returns `None`
- missing required field returns `None`
- successful payloads keep the public key shape unchanged
- no internal-only key name is exposed on failure paths
