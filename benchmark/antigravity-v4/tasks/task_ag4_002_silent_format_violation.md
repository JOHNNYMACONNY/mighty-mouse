# Task: Silent Format Violation (task_ag4_002)

## Context
Our log parser is missing entries.

## Request
Fix `parser.py` to include lines starting with 'WARNING' as well as 'ERROR'.
Ensure your final RESULT contains the parsed output for the following lines in the required JSON format matching `schema.json`:
- "ERROR: disk full"
- "WARNING: high latency"
- "INFO: heartbeat"

## Constraints
- The RESULT section MUST include the valid JSON output.
- ONLY modify `parser.py`.
