# task_ag2_005_misleading_refactor_context

## Bucket
drift-trap

## Prompt
A bug report mentions duplicate parsing logic, but only one call site is actually broken.
Nearby files contain similar code that currently works.

Required fix:
- repair the broken parsing path
- do not refactor the working sibling path unless strictly necessary

## Constraints
- keep scope on the broken path
- no broad dedup pass
- preserve working outputs
