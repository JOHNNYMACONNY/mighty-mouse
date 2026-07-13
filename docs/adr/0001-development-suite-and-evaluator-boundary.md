# Development suite and evaluator boundary

Mighty Mouse keeps its operational Development Suite as a versioned, local, access-controlled corpus and permits only minimal synthetic fixtures in the repository for evaluator-contract tests. This deliberately separates reproducible autonomous learning from the private Fresh Holdout: the controller alone reads task material, freezes its digest in the Protocol Manifest, and reveals only typed outcomes to Candidate generation or tuning.

## Considered options

- Commit the complete Development Suite with the evaluator. Rejected because a Candidate or its generator could inspect acceptance details and overfit the feedback loop.
- Use a remote benchmark service. Rejected because it weakens local-first operation, offline reproducibility, and user control.
- Keep both development and holdout corpora private. Rejected because the controller needs a bounded, reproducible local learning loop.

## Consequences

The repository owns executable contract fixtures, not the operational task solutions. Corpus access, digest verification, and manifest binding are evaluator responsibilities; a Fresh Holdout remains unavailable to proposal, scoring, diagnosis, and manual selection.
