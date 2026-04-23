# Phase 13: IDE-Native Autoresearch Loop

## Objective
Adapt the `/autoresearch` workflow to operate entirely within the IDE, mutating a portable prompt block (`mighty-antigravity-frozen.md`) and testing it using the built-in subagent capabilities instead of relying on external Python orchestrators (`mighty_mouse_agent.py`).

## Requirements
1. **Target**: Mutate `mighty-antigravity-frozen.md` (or a copy, `mighty-antigravity-native.md`).
2. **Evaluation Mechanism**: The loop must evaluate the new prompt by spinning up a native subagent or using the IDE's built-in slash commands, feeding it the task and the prompt.
3. **Mutation Focus**: Inject advanced reasoning strategies (e.g., scratchpads, explicit self-reflection steps) into the prompt.
4. **No External API Scripts**: Do not use `recursive_solver.py` or `gemini_client.py`.

## Implementation Steps
1. Create a new prompt variant `mighty-antigravity-native.md` based on the frozen prompt.
2. Create a new autoresearch workflow `.agents/workflows/autoresearch-native.md`.
3. In `autoresearch-native.md`, define the `Verify Logic` to:
   - Read a benchmark task.
   - Invoke an internal subagent (or equivalent IDE execution mechanism) loaded with the `mighty-antigravity-native.md` prompt.
   - Run the task's test script via the standard terminal.
   - Log the result and decide the next mutation.
4. Implement a small test script `eval/run_native_benchmark.sh` or rely on the GSD workflow to execute it.

## Verification
- Run the new `/autoresearch:native` workflow manually for 1 iteration.
- Ensure the prompt is mutated and evaluated using the native IDE tools (terminal/subagent).
