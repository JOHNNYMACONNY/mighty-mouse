# Mighty Mouse

[![Portfolio Case Study](https://img.shields.io/badge/Portfolio-Live%20Case%20Study-00FF88?style=for-the-badge&logo=vercel&logoColor=black)](https://www.ybfstudio.com/work/mighty-mouse)

> **TL;DR**: **Mighty Mouse** is a test-time compute scaling engine and MCP reliability server designed to make **small local LLMs** (`gemma4:e4b`) code with frontier-model precision and zero scope drift.

---

## ⚡ Headline Results & Impact

| Metric | Before (Raw Model) | **After (Mighty Mouse Engine)** | Impact |
| --- | ---: | ---: | --- |
| **Local Model Accuracy** | `28.0%` | **`74.2%`** | **+165% Net Accuracy Gain** across 31 benchmark tasks |
| **Tier 6 Challenge Pass Rate** | `20.0%` | **`80.0%`** | **4.0x Jump** on multi-step complex reasoning challenges |
| **Blind-Review Code Quality** | `4.30 / 5` | **`4.60 / 5`** | Outscored raw control in double-blind expert review |
| **Scope Drift & Rogue Deletes** | High Drift | **`0 Violations`** | 100% adherence to zero-footprint scope constraints |

*Evidence Note*: The prospective real-project study is complete at 10 paired tasks. Mighty Mouse used 4 retry rounds vs 6 for the control and received 4.60 vs 4.30 mean blind-review quality. No generalized improvement was demonstrated on timing. See the [`real-project study report`](data/evidence/real_project_report.md).

---

## 🎯 The Problem

Small, local open models (like `gemma4:e4b`) offer **total privacy, zero API costs, and low latency**, but raw execution fails ~72% of the time on non-trivial coding tasks. Without rigid guardrails, small models suffer from:
- **Scope Drift & Rogue File Deletes**: Editing or deleting unrelated workspace files.
- **Hallucinated Retries**: Repeating the exact same failing code in loop cycles.
- **Context Overload**: Attempting multi-file refactors without an upfront architectural blueprint.

---

## ⚙️ How It Works (4 Core Scaling Mechanisms)

Mighty Mouse acts as a high-reliability **cognitive exoskeleton** built around 4 test-time compute scaling mechanisms:

1. **Two-Stage Blueprinting (`<plan>` $\rightarrow$ `<act>`)**:  
   Isolates architectural planning (`<plan>`) from surgical execution (`<act>`) to eliminate scope drift before any file is touched.
2. **Multi-Turn Traceback Feedback Loops**:  
   Extracts Pytest error stack traces, lints, and scope check failures, feeding them back into Turn 2 for immediate self-correction.
3. **Dynamic Temperature Annealing ($T=0.0 \rightarrow 0.35 \rightarrow 0.70$)**:  
   Automatically scales sampling temperature on retries to break out of deterministic error loops.
4. **Best-of-$N$ Consensus Ranker**:  
   Evaluates candidate runs and locks in the draft with zero scope violations and the smallest clean diff.

![Gemma Test-Time Scaling Benchmark Chart](docs/assets/gemma_benchmark_chart.jpg)

---

## 🚀 Future Evolution & Roadmap

- [ ] **Multi-Agent Swarm Orchestration**: Splitting execution into specialized Planner, Coder, and Reviewer subagents.
- [ ] **Real-Time IDE & MCP Hooks**: Background self-healing directly inside Antigravity, Cursor, Claude Code, and Windsurf.
- [ ] **Cross-Model Frontier Parity**: Expanding perpetual benchmark evaluation to Llama 3 and Qwen models.

---

## 🔌 Supported Interfaces & Integrations

Mighty Mouse can be used as a **Python Library**, exposed as an **MCP Server**, or integrated into IDE workflows:
- **Integrations**: Antigravity, Claude Code, Codex, Cursor, Hermes, OpenClaw, and Windsurf.
- **MCP Tools**: `protocol`, `verify`, `setup_workspace`, `verify_and_record`.

---

## Install

```bash
git clone https://github.com/JOHNNYMACONNY/mighty-mouse.git
cd mighty-mouse
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

The core library and MCP transport support CPython 3.10, 3.11, 3.12, and 3.13.

## Two-Stage Execution & Agent CLI

Run the agent in unified mode (default), planner mode, or coder mode:

```bash
# Stage 1: Generate architectural plan blueprint
python3 src/mighty_mouse/orchestrator/mighty_mouse_agent.py \
  configs/mighty_mouse_v1.yaml \
  tasks/benchmark/task_1001.json \
  --stage planner \
  --plan-file logs/blueprint.md

# Stage 2: Execute surgical code edits using generated blueprint
python3 src/mighty_mouse/orchestrator/mighty_mouse_agent.py \
  configs/mighty_mouse_v1.yaml \
  tasks/benchmark/task_1001.json \
  --stage coder \
  --plan-file logs/blueprint.md
```

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
- `setup_workspace(workspace, repository, ...)`: creates a pinned local MCP identity from either an Ollama manifest or an exact host-supplied model digest; no hand-written JSON is needed.
- `verify_and_record(workspace, ...)`: verifies a task and writes a content-free v2 Signal receipt for learning aggregates using the pinned `.mighty-mouse/mcp-adapter.json` identity. It records no prompt, source, path, command, or verifier output.
- `recording_audit(workspace, receipt_hash, after)`: supports optional host hooks that fail closed unless that task's returned receipt was recorded.

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

Platform-specific rule files and MCP configuration shapes are documented in [`skills/README.md`](skills/README.md) and [`skills/mcp-configs/`](skills/mcp-configs/).

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
- `skills/`: platform rules (`antigravity`, `claude-code`, `codex`, `cursor`, `windsurf`) and MCP configurations (`hermes.yaml`, `openclaw.yaml`, `codex.json`).
- `src/mighty_mouse/orchestrator/`: original local-model agent loop and scaling engine.
- `src/mighty_mouse/services/`: synthetic benchmark and legacy verification services.
- `data/evidence/`: frozen historical, bare-control, and real-project study artifacts.
- `eval/`: evidence runners, scaling suite, and automated tests.

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
