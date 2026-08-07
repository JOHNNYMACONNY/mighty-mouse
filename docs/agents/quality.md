# Quality Gates

## Changed-line lint

Development installs include Flake8. Run changed-line lint from repository
root with a base revision:

```bash
.venv/bin/python scripts/check_changed_flake8.py --base HEAD^
```

`scripts/check_changed_flake8.py` inspects only added or modified Python lines.
Existing violations on untouched lines remain visible in full scans but do not
hide new defects or block unrelated work.

CI uses pull-request base commits and push predecessors as base revisions.
Unexpected Flake8 output, Git diff failures, and violations on changed lines
fail closed.

## Existing baseline

On 2026-08-07, default Flake8 reported 3,741 findings across `src`, `eval`,
and `mcp/src`. Baseline remains documented, not relabeled as clean. Future
cleanup passes reduce baseline by module while changed-line lint stays strict.

## Other gates

- Run `PYTHONPATH=eval:src:mcp/src .venv/bin/pytest eval/` for full tests.
- Compile modified Python files with `.venv/bin/python -m py_compile`.
- Build packages into isolated temporary output.
- Run clean wheel and MCP stdio smoke tests before release qualification.
- Do not claim typecheck or automated E2E coverage when tools remain unavailable.
