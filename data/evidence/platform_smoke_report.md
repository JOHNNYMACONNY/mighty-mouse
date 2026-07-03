# Platform MCP Smoke Report

Date: 2026-07-03  
Scope: manual configuration-to-tool transport smoke

## Result

Mighty Mouse was registered through the real platform CLI for Antigravity IDE and Codex using isolated profiles. Each registered stdio definition was then initialized through an MCP client, listed both expected tools, and successfully called `protocol` and `verify`.

| Platform | Registration evidence | Tools discovered | Protocol | Verification |
| --- | --- | --- | --- | --- |
| Antigravity IDE 1.107.0 | `antigravity-ide --add-mcp` wrote the documented `servers` definition | `protocol`, `verify` | `v9.1` | passed |
| Codex CLI 0.120.0 | `codex mcp add` and `codex mcp get` accepted the documented stdio definition | `protocol`, `verify` | `v9.1` | passed |

The verification call used a disposable workspace and `/usr/bin/true`; neither platform smoke modified a project workspace. Temporary platform profiles kept the test isolated from the user's normal configuration.

## Boundary

This proves platform configuration compatibility, stdio server startup, tool discovery, and both tool-call paths. It does not claim a model-quality result. A model-driven headless UI run was not used: the installed legacy Gemini CLI is no longer eligible for this account, and the installed Codex CLI does not support the account's configured model version.
