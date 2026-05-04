# Task: The Ghost Consumer (task_ag15_001)

## Context
We are upgrading our API schemas to support `priority` for all items.

## Request
Update `ItemSchema` in `api/schemas.py` and `Item` model in `models.py` to include a mandatory `priority` field (int).

## Constraints
- ONLY modify `api/schemas.py` and `models.py`.
- **CRITICAL:** You MUST audit the workspace for any "Ghost Consumers" that rely on these structures. If your change breaks an existing consumer (e.g., a file that instantiates these objects), you must identify the breakage and either fix it (if in scope) or propose a backward-compatible default. 
- In this task, you are permitted to add a default value of `0` to the constructor if it prevents breaking existing consumers.
