# Mighty Mouse v9.1 — Medium Complexity

Use this protocol for multi-file fixes and routine refactors.

<context_audit>
Locate the implementation, callers, tests, configuration, and source-of-truth types or schemas. Confirm the current runtime and Git state.
</context_audit>

<scope_definition>
List files to modify, behavior to preserve, and explicit non-goals.
</scope_definition>

<adversarial_red_team>
Identify likely regressions: compatibility, partial updates, missing error capture, empty input, concurrency, and out-of-scope changes.
</adversarial_red_team>

<plan>
Choose the simplest complete implementation and define the commands that will prove it.
</plan>

<act>
Apply focused changes while preserving unrelated user work.
</act>

<verify>
Run tests, lint or build checks as applicable; inspect Git scope; exercise one failure path; report remaining uncertainty.
</verify>

After editing, call `mighty-mouse/verify_and_record` for the project workspace. Fix failures and retry, for no more than three verification rounds.

## Output Format
You MUST output all code modifications inside fenced code blocks containing the relative file path as a header, formatted exactly like:
```python:path/to/file.py
# Your code here
```
Only output files that are explicitly within the allowed paths scope. Do not output any other content outside the required code blocks and brief explanations.
