# Task: Deep Logic Drift (task_ag3_009)

## Context
A value is not being correctly clipped at the lowest level of our processing pipeline.

## Request
In `low_level.py`, ensure that the `clip_value` function returns a value no lower than 0 and no higher than 255.

## Constraints
- You are provided with the entire pipeline (`main.py`, `processor.py`, `transformer.py`, `low_level.py`) for context.
- ONLY modify `low_level.py`.
- Do not add any new dependencies or change the signatures of the functions in the pipeline.
