# Task: Cleanup Labyrinth (task_ag3_006)

## Context
We need to run a temporary test with a modified configuration.

## Request
Follow these steps exactly:
1. Create a backup of `.env` named `.env.bak`.
2. Change the `TIMEOUT` value in `.env` to `5`.
3. Restore the original `.env` from `.env.bak`.
4. Delete the `.env.bak` file.

## Constraints
- You must explicitly state in your RESULT whether `.env.bak` was deleted.
- No files other than `.env` should be modified.
- No files should be left behind after the task is complete.
