# Example: Basic Refactor with Mighty Mouse

## Task
Rename `calculate_price` to `get_discounted_total` in `pricing.py` and update all callers.

## Mighty Mouse Trace

<context_audit>
1. Workspace Search: Found `pricing.py` and `checkout_service.py` (the only consumer).
2. Impact Mapping: `checkout_service.py` calls `calculate_price` on line 42.
3. Dependency Constraints: No hidden side effects; pure function rename.
4. Constraint Audit: Must maintain functional parity.
5. Honesty Check: Feasible.
</context_audit>

<scope_definition>
/src/pricing.py
/src/services/checkout_service.py
</scope_definition>

<state_machine_analysis>
N/A
</state_machine_analysis>

<plan>
1. Rename function in `pricing.py`.
2. Update import and call site in `checkout_service.py`.
</plan>

<act>
[File edits performed...]
</act>

<verify>
1. Self-Reflection: Rename completed; all call sites updated.
2. State Verification: Verified `checkout_service.py` can still calculate totals correctly.
3. Evidence: Ran `pytest tests/test_pricing.py` - PASSED.
</verify>
