# Task: Schema Evolution (task_ag9_002)

## Context
We are upgrading our project member storage format to support role-based access control.

## Request
Implement the `migrate_data(old_data)` function in `db_manager.py`. 
The function should take the `old_data` dictionary and return a `new_data` dictionary where the `projects` format is migrated.

- Old format: `{"projects": {"PROJECT_ID": ["USER_ID_1", "USER_ID_2"]}}`
- New format: `{"projects": {"PROJECT_ID": {"USER_ID_1": {"role": "member"}, "USER_ID_2": {"role": "member"}}}}`

## Constraints
- ONLY modify `db_manager.py`.
- Ensure all existing members are migrated with the default role of `"member"`.
- Preserve the rest of the dictionary structure.
