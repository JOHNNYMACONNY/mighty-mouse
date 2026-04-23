# Phase 14: Autonomous Benchmark Escalation

## Objective
Implement the "Pass -> Expand" logic for the native autoresearch loop. When the `mighty-antigravity-native.md` prompt correctly solves all tasks in the current benchmark pack, the loop should not stop or endlessly mutate. Instead, it should autonomously generate a harder benchmark pack (Pack N+1) and continue the loop against the new frontier.

## Requirements
1. **Trigger Condition**: Identify when a benchmark pack achieves a 100% pass rate.
2. **Generation Logic**: The workflow must specify how to generate the new pack (e.g., instructing the LLM to write complex agentic tasks like multi-file refactoring, logic state tracking, and integration bugs).
3. **Verification Constraints**: The new tasks must have valid, runnable test scripts. The workflow must explicitly forbid fake tests or un-runnable verification.

## Implementation Steps
1. Modify `.agents/workflows/autoresearch-native.md` to detail the `expand_benchmark` logic.
2. Provide explicit prompt instructions for the benchmark generation step, ensuring the generated tasks are verifiable.
3. Define the structure for how the new pack should be saved (`benchmark/antigravity-native-v{N+1}/tasks` and `fixtures`).

## Verification
- Run a simulated benchmark expansion.
- Ensure a new task is generated with a valid Python test script.
