# Baseline Run Procedure: Antigravity + Gemini 3 Flash

## Purpose
This procedure defines how to capture the baseline behavior of Gemini 3 Flash in Antigravity before applying Mighty Mouse.

Baseline means:
- same host environment
- same selected model
- same benchmark tasks
- no Mighty Mouse slash-command or harness active

## Setup
1. Open Antigravity.
2. Select Gemini 3 Flash for the chat.
3. Ensure no Mighty Mouse prompt or wrapper is active.
4. Use the Antigravity benchmark pack v1 tasks.

## Run Procedure
For each task:
1. Paste the task prompt into Antigravity naturally.
2. Do not prepend `/mighty`.
3. Let Gemini 3 Flash respond normally.
4. Record:
   - whether it solved the task
   - whether it solved it on first pass
   - whether it drifted scope
   - whether it made unsupported success claims
   - how it handled verification
   - response length / friction notes

## Minimum Per-Task Capture
Record at least:
- task_id
- success or fail
- first-pass yes/no
- scope violation yes/no
- false-success yes/no
- verification compliance yes/no
- short notes

## Batch Summary
After all tasks are complete, calculate:
- pass rate
- first-pass pass rate
- scope violation rate
- false-success rate
- verification compliance rate
- average output length

## Comparison Rule
Every Mighty Mouse variant must be compared against this baseline first.
If a variant does not clearly improve on baseline in meaningful ways, do not promote it.

## Notes
- If Antigravity behavior changes materially, refresh the baseline.
- If Gemini 3 Flash changes significantly, capture a fresh baseline before claiming progress.
- Baseline is the reference point for field usefulness, not a one-time forever truth.
