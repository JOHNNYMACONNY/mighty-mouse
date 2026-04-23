# Antigravity Benchmark Pack v14: Multi-Step Drift

## Goal
Test the agent's ability to handle structural complexity, circular dependencies, and cross-file rule obfuscation. This pack measures whether the context audit is deep enough to find non-obvious constraints.

## Tasks
1. **task_ag14_001_circular_dependency**: Refactor two files to break a circular import by extracting shared logic.
2. **task_ag14_002_hidden_validation**: Add a field that requires registration in a hidden decorator logic.
3. **task_ag14_003_selective_rollback**: Implement manual rollback for a dual-write operation.
4. **task_ag14_004_obfuscated_rule**: Calculate a value based on rules split across 3 different files/formats.
5. **task_ag14_005_adversarial_lint**: Implement a feature using a mandatory internal wrapper instead of a standard library.

## Success Criteria
100% pass rate requires:
- Task 1: No circular imports remain; functional parity preserved.
- Task 2: Field added with correct decorator metadata/type-hinting discovered via audit.
- Task 3: Local DB record is deleted if remote API call fails.
- Task 4: Discount calculation matches the combined value from all 3 rule files.
- Task 5: Use of `secure_http` instead of `requests`.
