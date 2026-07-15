# Mighty Mouse Agent Setup

Clone the repository and install Mighty Mouse and its MCP transport into one virtual environment:

```bash
git clone https://github.com/JOHNNYMACONNY/mighty-mouse.git
cd mighty-mouse
python -m venv ~/.venvs/mighty-mouse
~/.venvs/mighty-mouse/bin/pip install . ./mcp
```

Replace `/path/to/venv/bin/python` in the examples with `~/.venvs/mighty-mouse/bin/python`.

## Antigravity

Copy `skills/antigravity/SKILL.md` to `.agents/skills/mighty-mouse/SKILL.md`. Merge `skills/mcp-configs/antigravity.json` into `~/.gemini/config/mcp_config.json` for Antigravity. The VS Code-style Antigravity IDE uses the separate `servers` shape in `skills/mcp-configs/antigravity-ide.json`; its bundled CLI accepts that definition through `--add-mcp`.

## Claude Code

Copy or merge `skills/claude-code/CLAUDE.md` into the project root. Either merge `skills/mcp-configs/claude-code.json` into `.mcp.json`, or register it directly:

```bash
claude mcp add mighty-mouse --scope project -- /path/to/venv/bin/python -m mighty_mouse_mcp.server
```

## Cursor

Copy `skills/cursor/.cursorrules` into the project, or adapt it to `.cursor/rules/mighty-mouse.mdc`. Copy `skills/mcp-configs/cursor.json` to `.cursor/mcp.json` for project scope.

## Codex

Merge `skills/codex/AGENTS.md` into the project's `AGENTS.md`. Merge `skills/mcp-configs/codex.toml` into `~/.codex/config.toml`, or run:

```bash
codex mcp add mighty_mouse -- /path/to/venv/bin/python -m mighty_mouse_mcp.server
```

## Hermes

Install or copy `skills/hermes/SKILL.md` through Hermes' skill manager. Merge `skills/mcp-configs/hermes.yaml` under `mcp_servers` in `~/.hermes/config.yaml`, then run `/reload-mcp`.

## Windsurf

Copy `skills/windsurf/.windsurfrules` into the project. Merge `skills/mcp-configs/windsurf.json` into `~/.codeium/windsurf/mcp_config.json`, then refresh MCP servers in Cascade.

## Activation

Invoke `/mighty` or say “use the Mighty Mouse protocol.” On first use in a
workspace, the agent should call `setup_workspace` with the active local model
and host profile. It should then request a complexity-scaled protocol, make the
change, and call `verify_and_record` for no more than three rounds. This is the
same MCP path for every MCP-capable host; only the thin rule/config adapter is
host-specific.

## Platform references

- [Antigravity skills](https://antigravity.google/docs/skills)
- [Claude Code MCP](https://docs.anthropic.com/en/docs/claude-code/mcp)
- [Cursor MCP](https://docs.cursor.com/context/model-context-protocol)
- [Codex MCP](https://platform.openai.com/docs/docs-mcp)
- [Hermes MCP](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/mcp.md)
- [Windsurf MCP](https://docs.windsurf.com/windsurf/cascade/mcp)
