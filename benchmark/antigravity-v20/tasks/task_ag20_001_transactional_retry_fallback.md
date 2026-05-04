# Task: Transactional Retry with Fallback (task_ag20_001)

## Context
Our upstream data provider is experiencing severe instability (50% failure rate).

## Request
Implement `fetch_with_resilience()` in `fetcher.py`.
1. **Retry Logic**: Attempt to call `infrastructure.remote_service.get_data()` up to 3 times.
2. **Backoff**: Between attempts, print `RETRYING_IN_{N}S` where N is the attempt number (1, 2, 3).
3. **Fallback**: If all 3 attempts fail, call `cache.local_store.get_cached_value()`.
4. **Final Default**: If the cache returns `None`, return the string `"EMERGENCY_DEFAULT"`.

## Constraints
- ONLY modify `fetcher.py`.
- You MUST audit `infrastructure/remote_service.py` and `cache/local_store.py` to understand their APIs.
- **CRITICAL:** Do not use `time.sleep()` (keep the tests fast); just print the backoff message.

## Verification
Run `python3 test_resilience.py`. This script uses a mock that fails exactly 3 times and then checks if the fallback logic was triggered correctly.
