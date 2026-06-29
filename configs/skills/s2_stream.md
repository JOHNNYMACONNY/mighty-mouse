# SKILL: Async Stream Hygiene (S2-STREAM) [DRAFT]

## Strategic Intent
Ensure precise implementation of PEP 492/525 async iterator protocols and robust stream backpressure management.

## Implementation Guardrails
1. **Protocol Integrity**: 
   - `__aiter__` must be present and return `self`.
   - `__anext__` must raise `StopAsyncIteration` (not return `None`) to terminate the stream.
2. **Internal State Management**:
   - Explicitly track stream cursor/index in `self._index` or equivalent before any `await` in `__anext__`.
   - Ensure async state is reconstructed correctly across retries.
3. **Async Protocol Preservation**:
   - Preserve `__aiter__` and `__anext__` method signatures exactly.
   - Do not convert async flows to sync flows.
   - Do not change async method signatures unless explicitly required.
4. **Error & Backpressure**:
   - Wrap stream logic in `try/except` to prevent hung loops.
   - Use `asyncio.sleep(0)` or small delays for backpressure if the task requires rate limiting.

## File Operation Hygiene
- **Deletion**: Use ONLY `delete:path` fence syntax (e.g. ` ```delete:file.py `) for file removal.
- **Formatting**: NEVER use `text`, `code`, or `python` fences with internal text to represent a deletion.
- **Boundaries**: Respect `expected_files` for writes; only use `delete` for permitted purges.

## STRICT SCOPE BOUNDARY
- Limit implementation writes to `expected_files` and required protocol artifacts.
- **DO NOT** modify tests, fixtures, verifier files, or harness files.
- **DO NOT** "improve" or "fix" the test harness.
