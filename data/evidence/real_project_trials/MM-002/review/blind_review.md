# MM-002 Blind Review

Candidate A was the harness condition and Candidate B was control. The mapping
was withheld from the reviewer until the review was complete.

| Dimension | Candidate A | Candidate B |
|---|---:|---:|
| Correctness | 5.0 | 4.5 |
| Frozen scope adherence | 5.0 | 5.0 |
| Maintainability | 5.0 | 4.5 |
| Simplicity | 4.5 | 5.0 |
| Regression coverage | 5.0 | 4.0 |
| Overall | 5.0 | 4.5 |

Candidate A had stronger exact-contract tests, reusable document builders, and
explicit proof that human protocol output was not JSON. Candidate B was slightly
simpler but stripped leading/trailing whitespace from `task_description`, which
violated the requirement to retain the supplied value exactly. Its protocol and
invalid-workspace schema assertions were also weaker.

Selection: **Candidate A (harness)**.

Local raw review session SHA-256:
`346db3ed77f248ea06145bb9f8052de58c4fa2bf75ede1e6ba662481f2d0a6bb`.
