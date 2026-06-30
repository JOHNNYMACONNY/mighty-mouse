# MM-004 Blind Review

Candidate A was harness and Candidate B was control. The reviewer did not know
the mapping while reviewing.

| Dimension | Candidate A | Candidate B |
|---|---:|---:|
| Correctness | 4.5 | 3.8 |
| Frozen scope | 5.0 | 5.0 |
| Maintainability | 4.2 | 4.3 |
| Simplicity | 4.1 | 4.2 |
| Regression coverage | 4.5 | 3.8 |
| Overall | 4.4 | 4.0 |

Candidate A preserved and exported the existing `detect_projects` API, validated
script values as non-empty strings, and had realistic invalid-script and
PATH-based missing-npm tests. Candidate B provided a richer per-ecosystem status
schema and cleaner direct failure objects, but coerced `test` values with `str`,
allowing arrays, objects, numbers, or `None` to be treated as runnable scripts
instead of actionable metadata errors. It also changed the `detect_checks`
return contract and removed `detect_projects` from exports.

Selection: **Candidate A (harness)**. Both round to quality 4 on the frozen
integer rubric; selection follows the higher correctness and compatibility
review.

Local raw review session SHA-256:
`c7da90197bc852c13345676e9d44cf95e55715b282a157843f4a951d28509a75`.
