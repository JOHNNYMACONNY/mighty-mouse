# Blind review

Candidate identities were hidden from the reviewer. Candidate A was harness;
candidate B was control.

Selected: **A**

| Criterion | A | B |
|---|---:|---:|
| Correctness | 4.5 | 3.5 |
| Frozen scope | 5.0 | 5.0 |
| Maintainability | 4.5 | 3.5 |
| Simplicity | 4.5 | 3.5 |
| Regression coverage | 4.0 | 4.25 |
| Overall | 4.5 | 3.75 |

A's constructors validate unsafe slugs and repository identifiers, its URL
checks cover more destination fields, and it detects duplicate source links. B
directly tests rendered case-study CTAs, but blindly interpolates route and
repository inputs, omits evidence-source URL and duplicate-source-link
validation, and adds potentially duplicated repository links alongside existing
authored source links.

Local raw review session SHA-256:
`ce78397f599329f3c9ab31bc4a1f79d6d5574c9cd8c38e05bcb979b2889ee345`.
