# Blind re-review

Candidate A was control; candidate B was harness. This supersedes the
provisional pre-repair review.

Selected: **A**

| Criterion | A | B |
|---|---:|---:|
| Correctness | 5 | 4 |
| Frozen scope | 5 | 5 |
| Maintainability | 4 | 4 |
| Simplicity | 4 | 4 |
| Regression coverage | 4 | 5 |
| Overall | 5 | 4 |

Both now expose genuine prior-post inventory, validate source/eligibility
fields, reject duplicates, shortages, malformed ledgers and empty CLI values,
and preserve zero-mutation boundaries.

A wins because its human preview prints the true canonical-ID and checksum
prior-post exclusions. B keeps those true cases only in JSON and prints selected
assets whose prior flags are necessarily false after filtering. B has stronger
exact role/order tests; A's ordering proof is shallower.

Local raw review session SHA-256:
`25a35e1bc4687c6a7f9aaab4f05b507f361d7c86713a756bbab27c0a80ec95df`.
