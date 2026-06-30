# MM-001 — Public verify CLI

Both conditions started from commit `fb26ccd`, used Codex CLI 0.120.0 with
`gpt-5.5` at medium reasoning, used dependency-identical Python 3.13.11
environments, and received the same frozen task and acceptance gates. The
harness condition additionally activated the Mighty Mouse medium protocol.

Both conditions passed evaluator-controlled tests and clean-wheel CLI smoke
checks on the first external acceptance run. Neither changed a path outside the
frozen scope. The harness result took 200.073 seconds versus 138.985 seconds for
control and won the blind quality review 24/25 versus 23/25.

Native wheel builds on the external project volume encountered pre-existing
macOS AppleDouble (`._*`) metadata in both conditions. The evaluator applied the
same metadata-clean staging procedure to both; no product code was changed to
work around that environment issue.

Raw agent and reviewer sessions are retained locally because they include local
machine paths and session instructions. Their SHA-256 hashes are published in
the condition result and review files. The source-only implementation patches
are published here for audit.
