# SKILL: Resilient State Machines (S1-STATE) [REVISED]

## Strategic Intent
Implement stateful logic (Circuit Breakers, Retries, FSMs) using a transition-first approach. 

## Implementation Guardrails
1. **Explicit States**: Use Enums or Constants for states (e.g., CLOSED, OPEN, HALF_OPEN).
2. **Transition-Only Logic**: State changes must occur only on specific events (Failures, Timeouts, Success).
3. **Async Protocol Preservation**: When implementing async iterators or decorators:
   - DO NOT change function signatures or return types.
   - Preserve `__aiter__` and `__anext__` protocols exactly.
   - Use `asyncio.Lock` if concurrent state access is possible.

## STRICT SCOPE BOUNDARY
- Limit implementation writes to `expected_files` and required protocol artifacts (e.g., `CHECKLIST.md`).
- **DO NOT** modify tests, fixtures, verifier files, or harness files unless explicitly listed by the task.
- **DO NOT** "improve" or "fix" the test harness to support your implementation.
- If a test fails, revise your code in the target file; DO NOT touch the test file.
