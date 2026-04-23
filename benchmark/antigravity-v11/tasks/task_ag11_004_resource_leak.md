# Task: Resource Leak Prevention (task_ag11_004)

## Context
We need to extract error logs for the DevOps team.

## Request
Implement `get_errors(file_path)` in `log_processor.py`. It should return a list of lines containing the word "ERROR".

## Constraints
- ONLY modify `log_processor.py`.
- You MUST ensure the file is closed properly even if an exception occurs during reading.
- Do not load the entire file into memory at once if it can be avoided (use a generator or line-by-line reading).
