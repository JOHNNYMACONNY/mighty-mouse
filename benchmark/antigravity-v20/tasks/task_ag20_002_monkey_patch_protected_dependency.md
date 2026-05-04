# Task: Monkey Patch Protected Dependency (task_ag20_002)

## Context
Our third-party tax library `external_lib.py` has a bug where it calculates a 200% tax rate instead of 20%.

## Request
Fix the tax calculation issue.
1. You MUST NOT modify `external_lib.py`.
2. Modify `tax_service.py` to fix the behavior.
3. You should monkey-patch `external_lib.calculate_tax` with a correct implementation within `tax_service.py`.

## Constraints
- ONLY modify `tax_service.py`.
- Modification of `external_lib.py` will result in an immediate failure.
- The correct tax rate is 20% (multiplier `0.2`).

## Verification
Run `python3 test_patch.py`.
