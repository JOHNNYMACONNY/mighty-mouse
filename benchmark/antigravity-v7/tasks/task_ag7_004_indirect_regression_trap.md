# Task: Indirect Regression Trap (task_ag7_004)

## Context
We need better visibility into our payment processing pipeline.

## Request
Modify the `process(items)` function in `payment.py` to print a message: "Processing N items" at the start of the function, where N is the total number of items in the input collection.

## Constraints
- ONLY modify `payment.py`.
- The `items` input may be an iterator or a generator.
- You MUST ensure that the actual processing loop (the `for item in items` block) still functions correctly and processes all items after your modification.
