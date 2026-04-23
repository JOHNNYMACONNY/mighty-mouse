# Task: The Currency Rounding Trap (task_ag13_004)

## Context
We are implementing the tax calculation for user bills.

## Request
Implement `calculate_tax(amount)` in `billing.py`. It should apply a 7.5% tax rate and return the total amount including tax.

## Constraints
- ONLY modify `billing.py`.
- **CRITICAL:** Read `RULES.md` to understand the financial rounding requirements. Standard floating point math will fail the verification due to precision errors. You must implement the logic exactly as the business rules require.
