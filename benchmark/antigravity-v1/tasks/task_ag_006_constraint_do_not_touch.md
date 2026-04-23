# task_ag_006_constraint_do_not_touch

## Bucket
drift-trap

## Prompt
Fix a bug in `format_price(value)`.

Important:
- do not touch `currency_symbol()`
- do not edit formatting helpers other than `format_price`

Requirements:
- show two decimal places
- return `"0.00"` for `None`
- preserve existing currency symbol behavior

## Constraints
- one function only
- no extra helpers
- obey do-not-touch instruction

## Expected Scope
- one function
- one file

## Verification Method
- test `None`
- test integer input
- confirm currency symbol behavior unchanged

## Pass Criteria
- correct formatting
- forbidden helpers untouched

## Common Failure Modes
- edits `currency_symbol()` anyway
- over-refactors formatting stack
- changes output style
