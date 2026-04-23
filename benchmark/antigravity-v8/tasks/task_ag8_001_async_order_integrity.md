# Task: Async Order Integrity (task_ag8_001)

## Context
`api_client.py` fetches items sequentially, which is too slow.

## Request
Parallelize the `fetch_all(ids)` function in `api_client.py`.
It MUST fetch all items in parallel to improve performance, but it MUST return the results in the same relative order as the input `ids` list.

## Constraints
- ONLY modify `api_client.py`.
- Use standard `asyncio` patterns for parallelization.
- Ensure that even if network responses arrive out of order, the final list is correctly ordered.
