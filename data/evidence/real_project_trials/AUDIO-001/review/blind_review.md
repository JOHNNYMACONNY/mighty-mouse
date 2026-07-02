# Blind re-review

Candidate A was harness; candidate B was control. The review supersedes the
provisional review before repair round 1.

Selected: **A**

| Criterion | A | B |
|---|---:|---:|
| Correctness | 4.7 | 4.5 |
| Frozen scope | 5.0 | 5.0 |
| Maintainability | 4.6 | 4.5 |
| Simplicity | 4.4 | 4.5 |
| Regression coverage | 4.7 | 4.5 |
| Overall | 4.7 | 4.5 |

Both repaired their material defects. A now invalidates and reports every
duplicate member, exits nonzero after reporting invalid dry runs, requires an
affirmative SoundCloud publish destination, rejects empty history identities,
excludes in-tree history, and uses locale-independent ordering. Its multipart
publisher includes normalized artist and title.

B has stronger direct multipart request-shape coverage, but its history match
does not normalize surrounding whitespace and its live title omits normalized
artist. Neither contacted a remote service.

Local raw review session SHA-256:
`23f1c54ceea173cab90d28db9e16bfe360bafe9f9fcac16e255a63822ede333e`.
