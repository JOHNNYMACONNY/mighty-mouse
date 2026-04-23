# Task: Manual Transaction (task_ag10_001)

## Context
Our bank transfer logic needs to be atomic. If a transfer cannot be completed (e.g., the target account is invalid), any funds withdrawn must be returned to the source account.

## Request
Implement the `transfer(from_id, to_id, amount)` function in `bank.py`.

## Constraints
- ONLY modify `bank.py`.
- The function should return `True` if the transfer is successful, and `False` otherwise.
- You MUST ensure that the source account balance is unchanged if the transfer fails at any stage.
- Do not use any external database transaction libraries.
