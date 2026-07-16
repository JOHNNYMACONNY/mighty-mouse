# Mighty Mouse v9.1 — Low Complexity

Use this protocol for a small, localized change.

<scope>
Identify the requested outcome, the exact file boundary, and the nearest existing pattern.
</scope>

<act>
Make the smallest complete change. Preserve unrelated behavior and user work.
</act>

<verify>
Run the narrowest meaningful test or check, inspect the diff, and report any unverified risk.
</verify>

After editing, call `mighty-mouse/verify_and_record` for the project workspace. Fix failures and retry, for no more than three verification rounds.

## Output Format
You MUST output all code modifications inside fenced code blocks containing the relative file path as a header, formatted exactly like:
```python:path/to/file.py
# Your code here
```
Only output files that are explicitly within the allowed paths scope. Do not output any other content outside the required code blocks and brief explanations.
