# MM-003 Blind Review

Candidate A was control and Candidate B was harness. Identity was revealed only
after the read-only review.

| Dimension | Candidate A | Candidate B |
|---|---:|---:|
| Correctness | 5 | 4 |
| Frozen scope | 5 | 5 |
| Maintainability | 4 | 5 |
| Simplicity | 4 | 5 |
| Regression coverage | 5 | 3 |
| Overall | 5 | 4 |

Candidate A parsed protocol and verification JSON in the packaging job and
asserted their semantics. Candidate B invoked both commands but malformed JSON
or an incorrect `passed` value could still exit successfully. Candidate A's
main weakness was hard-coding version `0.2.0`, which requires maintenance on a
future release. Candidate B used cleaner `$RUNNER_TEMP` paths.

Selection: **Candidate A (control)** because its CI smokes verify behavior rather
than merely command execution.

Local raw review session SHA-256:
`05831ba807301953fc64d68458371a6cbe1d072d7c22322678db54aafa35acdf`.
