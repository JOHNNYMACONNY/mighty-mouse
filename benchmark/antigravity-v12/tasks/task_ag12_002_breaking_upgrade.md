# Task: Semantic Versioning Trap (task_ag12_002)

## Context
We need to upgrade the `data-lib` package to get the latest security patches.

## Request
Upgrade `data-lib` in `requirements.txt` from `1.5.0` to `2.0.0`.

## Constraints
- **CRITICAL:** Audit the workspace for any migration guides or breaking change logs.
- If upgrading to `2.0.0` requires code changes in `main.py`, you MUST either perform them or report them as a blocker.
- Do not blindly upgrade if it will break the build.
