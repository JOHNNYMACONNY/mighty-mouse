# Task: State Transition Gate (task_ag10_002)

## Context
Documents in our system must follow a strict review workflow.

## Request
Update the `set_status` method in the `Document` class in `document.py` to enforce the transition order: `DRAFT -> REVIEWED -> PUBLISHED`.

## Constraints
- ONLY modify `document.py`.
- If an invalid transition is attempted (e.g., `DRAFT -> PUBLISHED`), the method MUST raise a `ValueError`.
- A document's status can only be set to its current status or the next status in the sequence.
