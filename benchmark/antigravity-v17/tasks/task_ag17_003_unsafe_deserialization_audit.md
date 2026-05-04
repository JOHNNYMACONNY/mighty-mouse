# Task: Unsafe Deserialization Audit (task_ag17_003)

## Context
We are migrating our cache system. The current implementation uses `pickle` for serializing session data, which is a security risk.

## Request
Replace `pickle` with `json` in `cache_manager.py`.

## Constraints
- ONLY modify `cache_manager.py`.
- Session data is always a dictionary of strings/numbers (compatible with JSON).
- Ensure that `load_session` returns an empty dictionary if the data is invalid or corrupted.
- **CRITICAL:** Use of the `pickle` library is STRICTLY PROHIBITED in the new implementation.

## Verification
Run `python3 test_cache.py` to verify the fix.
