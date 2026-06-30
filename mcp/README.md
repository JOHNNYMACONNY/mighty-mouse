# Mighty Mouse MCP

The MCP server exposes two tools through the `mighty-mouse` server namespace:

- `verify`: run tests, lint, build, and optional Git scope checks.
- `protocol`: return the versioned low, medium, or high Mighty Mouse protocol.

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

The client presents these as `mighty-mouse/verify` and `mighty-mouse/protocol` or an equivalent namespaced form.

## Trust boundary

`verify` runs local commands with the permissions of the MCP server process. Only enable this local server for trusted workspaces and review tool-call approvals. Commands are executed as argument vectors without a shell, but an explicitly selected executable can still modify files.
