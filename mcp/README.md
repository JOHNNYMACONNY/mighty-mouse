# Mighty Mouse MCP

The MCP server exposes tools through the `mighty-mouse` server namespace:

- `verify`: run tests, lint, build, and optional Git scope checks.
- `protocol`: return the versioned low, medium, or high Mighty Mouse protocol.
- `verify_and_record`: run verification and persist a content-free v2 Signal receipt.
- `setup_workspace`: pin an exact local Ollama or host-supplied model identity and MCP execution profile without hand-writing config.
- `recording_audit`: check that one exact host task receipt was recorded after it began.
- `run`: adaptive routing and policy selection for a workspace task.
- `agent_execute`: canonical coding execution with compute scaling support via `HostAdapter.solve` (recommended/default production coding topology: `MM_SINGLE_ALWAYS`).
- `swarm_execute`: execute Multi-Agent Swarm with canonical host provenance and isolated verification via `HostAdapter.solve_swarm` (explicit opt-in compatibility interface).
- `policy_status`: inspect the active Champion policy and promotion status.
- `policy_preview`: preview candidate policy selection without mutation.
- `policy_pin`: pin an explicit policy for the workspace.
- `policy_rollback`: roll back to the baseline Champion.
- `compute_scaling_status`: inspect active compute scaling parameters.
- `compute_scaling_preview`: preview compute scaling parameters without mutation.
- `compute_scaling_pin`: pin exact compute scaling configuration for the workspace.

Install both packages from a repository checkout:

```bash
pip install . ./mcp
```

Run the stdio server:

```bash
python -m mighty_mouse_mcp.server
```

Generic MCP configuration:

```json
{
  "mcpServers": {
    "mighty-mouse": {
      "command": "python",
      "args": ["-m", "mighty_mouse_mcp.server"]
    }
  }
}
```

The client presents these as `mighty-mouse/verify`, `mighty-mouse/protocol`,
`mighty-mouse/setup_workspace`, `mighty-mouse/verify_and_record`, and
`mighty-mouse/recording_audit` or equivalent namespaced forms.

## Cline learning adapter

Use `setup_workspace` once per workspace, then use `verify_and_record` after
every agent edit. Setup resolves the exact local Ollama model-layer digest from
its manifest and derives a profile from the host, context limit, and Mighty
Mouse tool contract. It writes `.mighty-mouse/mcp-adapter.json` locally.

```text
setup_workspace(workspace, repository, ollama_model | model_digest, model_class,
                effective_context_limit, runtime_kind, runtime_version)
```

The setup call is shared by every MCP-capable host. Use `ollama_model` for a
local Ollama resolver, or pass exactly one exact `model_digest` when a host has
its own model-identity resolver. Cline is just the reference integration:
provide `runtime_kind="cline"` and its exact runtime version; Claude Code,
Codex, Cursor, and other hosts use their own controlled runtime facts. The
adapter refuses routine collection until this exact identity exists, and task
calls cannot override it. For Ollama-backed identities it rechecks the pinned
model alias before every recorded task and requires re-onboarding if the model
digest changes; non-Ollama host adapters must re-run setup whenever their active
model changes.

The durable receipt contains only controlled metadata: scope, model digest,
verification category/result, duration, and retry count. It never persists
prompts, source files, paths, commands, or verifier output. A failed check is
also recorded as a failed Signal, so repeated use produces honest aggregate
evidence rather than success-only telemetry.

`verify_and_record` provides the observation bridge for the v2 research loop.
It does not give Cline permission to edit autonomously or promote a policy;
those continue to require the separate, machine-gated research and evaluation
workflow.

## Multi-Agent Swarm execution (`swarm_execute`)

> **Production Topology Note (`MM_SINGLE_ALWAYS`)**:
> `swarm_execute` is an explicit opt-in compatibility tool. Following Milestone 12 reliability qualification, canonical single-agent execution (`agent_execute` / `HostAdapter.solve`) is the recommended default production coding topology. `swarm_execute` is not the recommended default based on bounded empirical reliability evaluation on `gemma4:e4b` (this finding is bounded to the evaluated model and setup, not a universal model-independent claim).

`swarm_execute` provides canonical Multi-Agent Swarm execution through MCP:

- Requires an existing Ollama-backed workspace identity (`setup_workspace` with `ollama_model`). Non-Ollama host models fail closed.
- Requires a separate, pristine `verification_workspace` directory that does not overlap with the target `workspace`. The verification workspace serves as a template; verification commands run in temporary isolation.
- Only the verified winner candidate is applied to the target `workspace`, exactly once, upon reviewer `PASS`. Failed verification or rejected candidates produce zero workspace mutations.
- The returned result is a minimized projection containing execution status, review verdict, verification summary, and applied output paths. It strictly excludes generated file contents and raw model responses.

## Tool contract v6 and re-onboarding

Adding `swarm_execute` advances the MCP tool contract version from `v5` to `v6` (15 total tools). Existing workspaces onboarded under `v5` must be re-onboarded explicitly using `setup_workspace(..., replace=True)` to derive a new execution profile. Existing profile-bound policy or compute-scaling pins do not automatically migrate and must be explicitly re-pinned under the `v6` profile if desired.

## Host hooks

### Post-task completion audit hook

MCP is the primary task-completion path. A host that supports completion hooks
can add a fail-closed guard without duplicating collection logic:

```bash
mighty-mouse-signal-audit /path/to/workspace \
  --receipt-hash <hash-returned-by-verify_and_record> \
  --after 2026-07-15T00:00:00+00:00
```

It exits `0` only when that exact returned Signal receipt was recorded after the
supplied task start time; otherwise it exits `1`. It stores nothing and is
appropriate as a post-task check, not a replacement for `verify_and_record`.

### Antigravity real-time lifecycle hooks

For Antigravity workspaces (`.agents/hooks.json`), real-time lifecycle integration is established via:

- **Composite PreToolUse wrapper**: Production registration invokes `.agents/scripts/composite_pretooluse.py`, which delegates composition to canonical `run_antigravity_composite_pre_tool_use`. It enforces Delivery Guard first evaluation with immediate denial short-circuit; canonical PreToolUse runs only after Delivery Guard explicitly allows.
- **File-write-only PostToolUse (`mighty-mouse-antigravity-posttooluse`)**: Console executable invoked exclusively on file-write tools (`write_to_file`, `replace_file_content`, `multi_replace_file_content`; excluding `run_command`).
  - Opt-in verification via `MIGHTY_MOUSE_POST_ACTION_VERIFY=1`: runs canonical project verification on write completion and records content-free v2 Signal (`retry_count=0`).
  - Opt-in self-healing recovery via `MIGHTY_MOUSE_POST_ACTION_RECOVERY=1` and `MIGHTY_MOUSE_POST_ACTION_RECOVERY_CONFIG=<path>`: on verification failure, runs at most 1 bounded recovery attempt restricted strictly to canonical target paths with zero deletions and disabled hygiene cleanup. Re-verification determines final outcome and records retry Signal (`retry_count=1`).
  - Public projection returned to Antigravity host is strictly `{}`.

## Trust boundary

`verify` and execution tools run local commands with the permissions of the MCP server process. Only enable this local server for trusted workspaces and review tool-call approvals. Commands are executed as argument vectors without a shell, but an explicitly selected executable can still modify files.
