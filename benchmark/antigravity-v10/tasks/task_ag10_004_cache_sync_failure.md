# Task: Cache Sync Failure (task_ag10_004)

## Context
Our search results are showing outdated prices because the search index is not being updated when a product's price changes.

## Request
Modify the `update_price(p_id, price)` function in `store.py` to ensure that the search index is kept in sync with the database price.

## Constraints
- ONLY modify `store.py`.
- You MUST call the appropriate function from `search_index.py` to update the index.
- The update to the index should only happen if the database update is successful.
