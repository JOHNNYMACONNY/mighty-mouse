# Task: Metaclass Validation (task_ag24_002)

## Context
We need to ensure that all plugin developers implement a specific interface, but we want to catch errors at definition time rather than runtime.

## Request
Implement `ValidatorMeta` in `models.py`.
1. It must be a metaclass (inheriting from `type`).
2. When a new class is created using this metaclass, it must check if the class defines a method named `validate`.
3. If `validate` is missing, it must raise a `TypeError` with the message `"Missing validate method in {class_name}"`.
4. **Note:** The `Base` class itself (which uses the metaclass) should be exempt from this check if it's considered an abstract base. Actually, let's just make it required for ALL classes using it except the one that defines it.

## Constraints
- ONLY modify `models.py`.
- Ensure it works for multi-level inheritance (subclasses of subclasses must also be validated).

## Verification
Run `python3 test_meta.py`.
