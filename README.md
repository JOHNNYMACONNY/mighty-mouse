# Mighty Mouse

Mighty Mouse is a provider-agnostic coding protocol and verification harness for AI agents. Its primary research goal is to make small, locally operated models more viable for coding and agentic work through explicit protocols, project-native verification, and bounded recovery. It can be imported as a Python library, exposed to any MCP-compatible client, or used through platform rules for Antigravity, Claude Code, Cursor, Codex, Hermes, and Windsurf.

The harness does not replace an agent's model provider. It supplies:

- versioned low, medium, and high-complexity coding protocols;
- project-native verification for tests, lint, builds, and Git scope;
- structured pass/fail results with retry suggestions;
- a local MCP server with `protocol` and `verify` tools;
- the original Ollama benchmark CLI and frozen evaluation evidence.

## Evidence and limitations

The historical paired validation contains 15 original-protocol runs and 15 Lean protocol runs. Both recorded 15/15 passes; Lean reduced average latency by 29.5% in that recorded environment.

A new bare control sent the same 15 frozen tasks to `gemma4:e4b` with one raw request per task, no Mighty Mouse prompt, and no verification retry loop. It also passed 15/15. Therefore:

- the frozen synthetic corpus supports the recorded Lean latency result;
- it does **not** demonstrate a success-rate advantage over a raw model call;
- its permissive tests have a ceiling effect and should not be generalized to real projects.

See [`data/evidence/results/baseline_comparison.md`](data/evidence/results/baseline_comparison.md) and the raw [`bare_baseline_results.json`](data/evidence/results/bare_baseline_results.json).

The prospective real-project study is complete at 10 paired tasks. Both conditions passed 6/10 tasks on the first attempt, with no scope violations. Mighty Mouse used 4 retry rounds versus 6 for the control and received a higher mean blind-review quality score (4.60 versus 4.30), but it was slower by both mean and median duration. **No generalized improvement was demonstrated.** The result is mixed: fewer retries and higher review quality, without better first-pass reliability or speed. See the [`real-project study report`](data/evidence/real_project_report.md) and its paired raw evidence.

That real-project study used GPT-5.5 through Codex CLI, so it does not test the primary small-local-model thesis. A prospective three-condition study—raw Gemma, Gemma with Mighty Mouse, and a larger-model reference—is specified in [`docs/local-model-capability-study.md`](docs/local-model-capability-study.md). Until that study is complete, Mighty Mouse does not claim that it closes the capability gap between small and large models.

## Install

```bash
git clone https://github.com/JOHNNYMACONNY/mighty-mouse.git
cd mighty-mouse
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

The core library and MCP transport support CPython 3.10, 3.11, 3.12, and 3.13.

## Verify any project

From the command line, verify a workspace with auto-detected project checks:

```bash
mighty-mouse verify /path/to/project
```

For automation, add `--json`. Standard output contains exactly one JSON document
for pass (`0`), check failure (`1`), and unusable workspace (`2`) outcomes:

```bash
mighty-mouse verify /path/to/project --json
```

The version 1 verify shape is:

```json
{
  "schema_version": 1,
  "interface": "verify",
  "passed": true,
  "checks": [{"name": "tests", "passed": true, "output": "", "duration_sec": 0.25}],
  "summary": "Passed 1/1 verification checks.",
  "suggestions": [],
  "detected_projects": ["python", "node"],
  "warnings": []
}
```

Commands, changed-file scope, and the per-command timeout can be specified explicitly:

```bash
mighty-mouse verify . \
  --test-command "pytest -q" \
  --lint-command "ruff check ." \
  --build-command "python -m build" \
  --allowed-path src/ \
  --allowed-path tests/ \
  --timeout-sec 120
```

The command exits `0` when all applicable checks pass, `1` when verification
runs and a check fails, and `2` for invalid input or an unusable workspace.

```python
from mighty_mouse.verifier import verify

result = verify(
    workspace="/path/to/project",
    allowed_paths=["src/feature.py", "tests/"],
)

print(result.passed)
print(result.summary)
for check in result.checks:
    print(check.name, check.passed, check.duration_sec)
```

Without explicit commands, Mighty Mouse detects every applicable root ecosystem rather than choosing one. Python-only projects run pytest when tests are present and otherwise run a syntax check with a structured partial-coverage warning. Node-only projects select a usable test, lint, or build script. Mixed Python/Node projects run one applicable check family for each ecosystem, and a failure in either family fails the combined result.

Malformed Node metadata, missing Node scripts, and missing executables produce explicit non-passing checks plus actionable entries in `warnings`; they never result in a successful empty verification. `detected_projects` records the ecosystems considered by auto-detection. Explicit command overrides bypass auto-detection, so their results leave `detected_projects` empty rather than claiming detection ran. Human output labels detection warnings, while `--json` emits them only as JSON fields.

Rust and Go root markers continue to select their native test commands. You can override detection:

```python
result = verify(
    workspace="/path/to/project",
    test_command="pytest -q",
    lint_command="ruff check .",
    build_command="python -m build",
    timeout_sec=120,
)
```

Commands are executed without a shell, but they still run with the verifier process's local permissions. Use explicit commands only in trusted workspaces.

## Select a protocol

Show the medium-complexity protocol for a task (the default):

```bash
mighty-mouse protocol "Add JSON output to the CLI"
mighty-mouse protocol "Fix a typo" --complexity low
mighty-mouse protocol "Change authentication" --complexity high --json
```

Human output includes the selected protocol and its verification reminder. With
`--json`, the version 1 protocol shape is:

```json
{
  "schema_version": 1,
  "interface": "protocol",
  "task_description": "Fix a typo",
  "complexity": "low",
  "protocol_prompt": "# Mighty Mouse v9.1 — Low Complexity\n...",
  "verification_reminder": "After editing, run Mighty Mouse verification, fix failures, and retry for no more than three rounds."
}
```

## MCP server

Install the separate transport package into the same environment:

```bash
.venv/bin/pip install -e ./mcp
.venv/bin/python -m mighty_mouse_mcp.server
```

The `mighty-mouse` server exposes:

- `protocol(task_description, complexity)`: returns the pinned v9.1 low, medium, or high protocol.
- `verify(workspace, ...)`: returns structured tests, lint, build, and scope results.

Generic stdio configuration:

```json
{
  "mcpServers": {
    "mighty-mouse": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "mighty_mouse_mcp.server"]
    }
  }
}
```

Platform-specific rule files and current configuration shapes are documented in [`skills/README.md`](skills/README.md).

## Original benchmark CLI

```bash
mighty-mouse doctor
mighty-mouse doctor --live
mighty-mouse demo
mighty-mouse demo --live --model gemma4:e4b
mighty-mouse benchmark
mighty-mouse benchmark --tasks-dir ./my-tasks
```

The simulated demo replays recorded fixtures and does not execute a model. Live commands isolate logs and temporary workspaces under a reported output directory.

## Reproduce the bare control

With Ollama running and `gemma4:e4b` installed:

```bash
PYTHONPATH=src python eval/run_bare_baseline.py --force
```

The runner requires exactly 15 frozen tasks, makes one generation request per task, retains every raw response, records model provenance and hashes, and never applies a Mighty Mouse protocol or retry loop.

## Architecture

- `src/mighty_mouse/verifier/`: generic project verification public API.
- `src/mighty_mouse/protocols/`: versioned complexity-scaled protocols.
- `mcp/`: separately installable MCP transport.
- `skills/`: platform rules and MCP configuration examples.
- `src/mighty_mouse/orchestrator/`: original local-model agent loop.
- `src/mighty_mouse/services/`: synthetic benchmark and legacy verification services.
- `data/evidence/`: frozen historical, bare-control, and real-project study artifacts.
- `eval/`: evidence runners and automated tests.

## Development

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
python -m build
```

The MCP package is built separately from `mcp/`. Release verification installs both wheels into a clean environment and exercises an actual stdio MCP session.

GitHub Actions runs the complete test suite on every supported Python version
for pull requests and pushes to `main`, with both the core and MCP packages
installed. A separate Python 3.13 packaging job builds both wheels, installs
only those wheels into a clean environment, and checks the version import, MCP
server import, CLI help, protocol JSON, and passing verify JSON from outside the
source checkout.

## License

MIT. See [`LICENSE`](LICENSE).
