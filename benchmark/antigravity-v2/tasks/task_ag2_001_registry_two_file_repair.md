# task_ag2_001_registry_two_file_repair

## Bucket
medium

## Prompt
A small Python app registers users across two files.

Required fix:
- reject blank usernames after trimming whitespace
- reject emails that are blank after trimming whitespace
- preserve existing behavior for valid payloads

## Constraints
- keep public function names unchanged
- keep changes limited to validation / registration flow
- do not refactor storage logic

## Expected Scope
- two files max
- validation and call flow only

## Pass Criteria
- blank username fails
- blank email fails
- valid registration still succeeds
