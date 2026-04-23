# Task: Cascading Schema Update (task_ag13_003)

## Context
We need to add a new optional string field `referral_code` to the `User` model in `models.py`.

## Request
Add the `referral_code` field to `models.py`. 

## Constraints
- **CRITICAL:** A schema change requires updates to all connected validation schemas and test fixtures in the workspace.
- You MUST audit the workspace to find and update any API schemas or mock data files that enforce the shape of a User.
- If you miss a downstream consumer, the build will fail.
