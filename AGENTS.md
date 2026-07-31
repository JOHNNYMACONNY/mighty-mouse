## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for `JOHNNYMACONNY/mighty-mouse`; external pull requests are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

The repo uses the standard `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix` workflow labels. See `docs/agents/triage-labels.md`.

### Domain docs

The repo uses a single-context domain documentation layout. See `docs/agents/domain.md`.

### Single-instance process enforcement

Before starting or restarting `eval/perpetual_loop.py` or any evaluation runner background process:
1. Inspect running processes for active `perpetual_loop.py` or `solve_benchmark.py` instances.
2. Terminate any stale or duplicate background loop processes.
3. Enforce that **strictly ONLY ONE single active instance** of the Mighty Mouse evaluation runner is executing at any time to prevent state file race conditions.

