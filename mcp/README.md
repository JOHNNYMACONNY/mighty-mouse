# Mighty Mouse MCP

The MCP server exposes five tools through the `mighty-mouse` server namespace:

- `verify`: run tests, lint, build, and optional Git scope checks.
- `protocol`: return the versioned low, medium, or high Mighty Mouse protocol.
- `verify_and_record`: run verification and persist a content-free v2 Signal receipt.
- `setup_workspace`: pin a local Ollama model and MCP execution profile without hand-writing config.
- `recording_audit`: check that a host task recorded a Signal after it began.

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
setup_workspace(workspace, repository, ollama_model, model_class,
                effective_context_limit, runtime_kind, runtime_version)
```

The setup call is shared by every MCP-capable host. Cline is just the reference
integration: provide `runtime_kind="cline"`; Claude Code, Codex, Cursor, and
other hosts use their own controlled runtime name. The adapter refuses routine
collection until this exact identity exists, and task calls cannot override it.

The durable receipt contains only controlled metadata: scope, model digest,
verification category/result, duration, and retry count. It never persists
prompts, source files, paths, commands, or verifier output. A failed check is
also recorded as a failed Signal, so repeated use produces honest aggregate
evidence rather than success-only telemetry.

`verify_and_record` provides the observation bridge for the v2 research loop.
It does not give Cline permission to edit autonomously or promote a policy;
those continue to require the separate, machine-gated research and evaluation
workflow.

## Optional host hook

MCP is the primary task-completion path. A host that supports completion hooks
can add a fail-closed guard without duplicating collection logic:

```bash
mighty-mouse-signal-audit /path/to/workspace --after 2026-07-15T00:00:00+00:00
```

It exits `0` only when a Signal receipt was recorded after the supplied task
start time; otherwise it exits `1`. It stores nothing and is appropriate as a
post-task check, not a replacement for `verify_and_record`.

## Trust boundary

`verify` runs local commands with the permissions of the MCP server process. Only enable this local server for trusted workspaces and review tool-call approvals. Commands are executed as argument vectors without a shell, but an explicitly selected executable can still modify files.
