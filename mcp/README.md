# Mighty Mouse MCP

The MCP server exposes three tools through the `mighty-mouse` server namespace:

- `verify`: run tests, lint, build, and optional Git scope checks.
- `protocol`: return the versioned low, medium, or high Mighty Mouse protocol.
- `verify_and_record`: run verification and persist a content-free v2 Signal receipt.

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

The client presents these as `mighty-mouse/verify`, `mighty-mouse/protocol`, and
`mighty-mouse/verify_and_record` or equivalent namespaced forms.

## Cline learning adapter

Use `verify_and_record` after a Cline edit instead of `verify` when the task
should contribute to v2 learning. Before first use, pin the workspace identity
in `<workspace>/.mighty-mouse/cline-adapter.json`:

```json
{
  "repository": "owner/repository",
  "model_digest": "sha256:<exact Ollama model-layer digest>",
  "model_class": "local-large",
  "execution_profile_id": "sha256:<exact Cline execution-profile digest>"
}
```

The adapter refuses collection without this exact configuration. Cline cannot
supply or override model/profile identity per task. For an Ollama model, obtain
the model-layer digest from its local manifest under
`~/.ollama/models/manifests`; update the configuration whenever its model,
context, tool contract, or runtime profile changes.

The durable receipt contains only controlled metadata: scope, model digest,
verification category/result, duration, and retry count. It never persists
prompts, source files, paths, commands, or verifier output. A failed check is
also recorded as a failed Signal, so repeated use produces honest aggregate
evidence rather than success-only telemetry.

`verify_and_record` provides the observation bridge for the v2 research loop.
It does not give Cline permission to edit autonomously or promote a policy;
those continue to require the separate, machine-gated research and evaluation
workflow.

## Trust boundary

`verify` runs local commands with the permissions of the MCP server process. Only enable this local server for trusted workspaces and review tool-call approvals. Commands are executed as argument vectors without a shell, but an explicitly selected executable can still modify files.
