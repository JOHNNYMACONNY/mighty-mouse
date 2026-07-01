# PORT-001 Blind Review

Candidate A was control and Candidate B was harness. The reviewer received only
the four allowed implementation files and did not know condition identity.

| Dimension | Candidate A | Candidate B |
|---|---:|---:|
| Correctness | 4.3 | 4.7 |
| Frozen scope | 5.0 | 5.0 |
| Maintainability | 4.6 | 4.7 |
| Simplicity | 4.9 | 4.7 |
| Regression coverage | 4.0 | 4.3 |
| Documentation/audit | 4.7 | 4.9 |
| Overall | 4.5 | 4.7 |

Both candidates used safe argument-vector Git calls, NUL-delimited path parsing,
correct generated-path rules, and honest inventory documentation. Candidate B
also verified that every tracked `output/` evidence path still existed in the
worktree. Candidate A only checked the index and could miss an unstaged evidence
deletion. Neither enforces an exact expected count of 20, so both retain a
smaller preservation false-negative.

Selection: **Candidate B (harness)**.

Local raw review session SHA-256:
`7437c39cd23c4806446416b68fd3ca35b53f3297cfa9ce384d950807819fcc86`.
