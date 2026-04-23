# Task: State Machine Illegal Transition (task_ag5_002)

## Context
`order_flow.py` contains a state machine for order processing.

## Request
Add a `cancel()` method to the `Order` class. 
Orders can be cancelled from the `PENDING` or `PAID` states. 
Orders MUST NOT be cancelled if they are already in the `SHIPPED` state.

## Constraints
- ONLY modify `order_flow.py`.
- Maintain the integrity of the existing state transitions (`PENDING -> PAID -> SHIPPED`).
