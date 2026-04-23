# Task: Complex Regex Backtracking Trap (task_ag10_005)

## Context
The current phone number parser is failing on certain inputs and has significant performance issues on long strings.

## Request
Refactor the `parse_phone(text)` function in `phone_parser.py` to be more robust. The function should return the phone number in the format `XXX-XXX-XXXX` or `None` if no valid number is found.

## Constraints
- ONLY modify `phone_parser.py`.
- You MUST ensure the parser is safe from performance regressions (e.g., catastrophic backtracking) on malformed inputs.
- The parser should handle various separators like dashes, dots, and spaces, as well as optional parentheses around the area code.
