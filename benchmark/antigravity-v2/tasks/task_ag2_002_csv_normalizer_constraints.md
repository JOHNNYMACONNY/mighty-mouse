# task_ag2_002_csv_normalizer_constraints

## Bucket
medium

## Prompt
Fix a CSV row normalizer so empty lines are skipped, but non-empty fields stay unchanged except for leading/trailing whitespace trimming on each field.

## Constraints
- edit only the normalizer helper
- do not add imports
- do not add helper functions
- keep logic compact
- do not change row ordering

## Expected Scope
- one file only
- normalizer helper only

## Pass Criteria
- fully blank or whitespace-only rows are skipped
- non-empty rows are retained in order
- each field is trimmed at both ends only
- internal spaces and other non-whitespace characters inside fields are preserved
