# Skill Proposal: Async Stream Hygiene (S2-STREAM)

## 1. Skill Metadata
- **skill_id**: S2-STREAM
- **name**: Async Stream Hygiene
- **status**: PROPOSAL
- **trigger_tags**: ["async-iterator", "stream-adapter", "realtime-stream"]
- **failure_categories**: ["LOGIC", "TIMEOUT"]

## 2. Target Failure Pattern
The model struggles with the precise implementation of PEP 492 and PEP 525 async protocols. Specifically, it frequently misses `__aiter__` returning `self` or fails to handle `StopAsyncIteration` correctly in complex `__anext__` logic. In multi-turn tasks, this leads to circular reasoning and budget exhaustion (TIMEOUT).

## 3. Evidence Trail
- **task_1402_async_iterator_circuitbreaker**: Horizon success at 266s.
- **obs_task_1402**: Persistent TIMEOUT in Phase 51.
- **obs_task_1045**: TIMEOUT in Phase 51 observation (retry logic inside async stream).

## 4. Proposed Overlay Text
```markdown
## SKILL: Async Stream Hygiene (S2-STREAM)
When implementing async iterators or streams:
1. **Protocol Integrity**: Ensure `__aiter__` is present and returns `self`.
2. **Stop Condition**: `__anext__` must raise `StopAsyncIteration` (not return None) to terminate the stream.
3. **Internal State**: Explicitly track the "current" index or cursor in `self._index` before the first `await` in `__anext__`.
4. **Error Handling**: Wrap stream logic in `try/except` to prevent unhandled exceptions from hanging the loop.
```

## 5. Latency & Stability Risk
- **Latency Risk**: **Medium**. The addition of instruction fragments increases prompt size (+120 tokens).
- **Timeout Risk**: **Low-Medium**. While it adds overhead, it is designed to prevent the circular reasoning that currently drives the 50% timeout rate in async tasks.
- **Estimation**: Likely to decrease timeout frequency for async tasks by providing a clear implementation path, but may slightly increase latency for successful runs.

## 6. Write Boundary Rules
- **Strict Requirement**: Respect each task’s `expected_files` boundary.
- **Integrity**: Never modify tests, fixtures, harness files, or verifiers unless explicitly listed by the task.

## 7. Anti-Patterns
- Using `yield` instead of `raise StopAsyncIteration` in a manual `__anext__` method.
- Changing function signatures of inherited async interfaces.

## 8. Validation Tasks
- `task_1402_async_iterator_circuitbreaker`
- `obs_task_1402` (recovery validation)
- `task_006_stream_composite_enricher`

## 9. Rejection Criteria
- Increase in `timeout_rate` for `async-iterator` tagged tasks.
- Hygiene regressions (SCOPE failures) in `expected_files`.

## 10. Overlap/Conflict Risk with S1-STATE
- **S1-STATE** covers "Resilient State Machines". 
- **Conflict**: Low. S1-STATE handles the "What" (state transitions), while S2-STREAM handles the "How" (async protocol). 
- **Policy**: If a task is tagged with both `state-machine` and `async-iterator`, the system will fail closed until explicit selection is enabled.
